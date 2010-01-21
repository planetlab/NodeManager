# $Id$
# $URL$

"""VServer slivers.

There are a couple of tricky things going on here.  First, the kernel
needs disk usage information in order to enforce the quota.  However,
determining disk usage redundantly strains the disks.  Thus, the
Sliver_VS.disk_usage_initialized flag is used to determine whether
this initialization has been made.

Second, it's not currently possible to set the scheduler parameters
for a sliver unless that sliver has a running process.  /bin/vsh helps
us out by reading the configuration file so that it can set the
appropriate limits after entering the sliver context.  Making the
syscall that actually sets the parameters gives a harmless error if no
process is running.  Thus we keep vm_running on when setting scheduler
parameters so that set_sched_params() always makes the syscall, and we
don't have to guess if there is a running process or not.
"""

import errno
import traceback
import os, os.path
import time

import vserver

import accounts
import logger
import tools
from threading import BoundedSemaphore

globalsem = BoundedSemaphore()

# special constant that tells vserver to keep its existing settings
KEEP_LIMIT = vserver.VC_LIM_KEEP

# populate the sliver/vserver specific default allocations table,
# which is used to look for slice attributes
DEFAULT_ALLOCATION = {}
for rlimit in vserver.RLIMITS.keys():
    rlim = rlimit.lower()
    DEFAULT_ALLOCATION["%s_min"%rlim]=KEEP_LIMIT
    DEFAULT_ALLOCATION["%s_soft"%rlim]=KEEP_LIMIT
    DEFAULT_ALLOCATION["%s_hard"%rlim]=KEEP_LIMIT

class Sliver_VS(accounts.Account, vserver.VServer):
    """This class wraps vserver.VServer to make its interface closer to what we need."""

    SHELL = '/bin/vsh'
    TYPE = 'sliver.VServer'
    _init_disk_info_sem = globalsem

    def __init__(self, rec):
        logger.verbose ('initing Sliver_VS with name=%s'%rec['name'])
        try:
            vserver.VServer.__init__(self, rec['name'],logfile='/var/log/nm')
        except Exception, err:
            if not isinstance(err, vserver.NoSuchVServer):
                # Probably a bad vserver or vserver configuration file
                logger.log_exc(self.name)
                logger.log('%s: recreating bad vserver' % rec['name'])
                self.destroy(rec['name'])
            self.create(rec['name'], rec['vref'])
            vserver.VServer.__init__(self, rec['name'],logfile='/var/log/nm')

        self.keys = ''
        self.rspec = {}
        self.initscript = ''
        self.slice_id = rec['slice_id']
        self.disk_usage_initialized = False
        self.initscriptchanged = False
        self.enabled = True
        self.configure(rec)

    @staticmethod
    def create(name, vref = None):
        logger.verbose('Sliver_VS:create - name=%s'%name)
        if vref is None:
            logger.log("creating %s : no vref attached, this is unexpected"%name)
            vref='default'
        # used to look in /etc/planetlab/family, now relies on the 'family' extra attribute in GetSlivers()
        # which for legacy is still exposed here as the 'vref' key
        
        # check the template exists -- there's probably a better way..
        if not os.path.isdir ("/vservers/.vref/%s"%vref):
            # find a resonable default
            if os.path.isfile ("/etc/planetlab/slicefamily"):
                default=file("/etc/planetlab/slicefamily").read().strip()
            else:
                default='default'
                logger.log("creating %s : /etc/planetlab/slicefamily not found, this is unexpected"%name)
            logger.log("creating %s - vref %s not found, using default %s"%(name,vref,default))
            vref=default

        # guess arch
        try:
            (x,y,arch)=vref.split('-')
        except:
            arch='i386'
            
        def personality (arch):
            personality="linux32"
            if arch.find("64")>=0:
                personality="linux64"
            return personality

        logger.log_call('/usr/sbin/vuseradd', '-t', vref, name)
        # export slicename to the slice in /etc/slicename
        file('/vservers/%s/etc/slicename' % name, 'w').write(name)
        file('/vservers/%s/etc/slicefamily' % name, 'w').write(vref)
        # set personality: only if needed (if arch's differ)
        if tools.root_context_arch() != arch:
            file('/etc/vservers/%s/personality' % name, 'w').write(personality(arch))
            logger.log('%s: set personality to %s'%(name,personality(arch)))

    @staticmethod
    def destroy(name): logger.log_call('/usr/sbin/vuserdel', name)

    def configure(self, rec):
        new_rspec = rec['_rspec']
        if new_rspec != self.rspec:
            self.rspec = new_rspec
            self.set_resources()

        new_initscript = rec['initscript']
        if new_initscript != self.initscript:
            self.initscript = new_initscript
            self.initscriptchanged = True

        accounts.Account.configure(self, rec)  # install ssh keys

    def start(self, delay=0):
        if self.rspec['enabled'] > 0:
            logger.log('%s: starting in %d seconds' % (self.name, delay))
            time.sleep(delay)
            # VServer.start calls fork() internally, 
            # so just close the nonstandard fds and fork once to avoid creating zombies
            child_pid = os.fork()
            if child_pid == 0:
                if self.initscriptchanged:
                    logger.log('%s: installing initscript' % self.name)
                    def install_initscript():
                        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                        fd = os.open('/etc/rc.vinit', flags, 0755)
                        os.write(fd, self.initscript)
                        os.close(fd)
                    try:
                        self.chroot_call(install_initscript)
                    except: logger.log_exc(self.name)
                tools.close_nonstandard_fds()
                vserver.VServer.start(self)
                os._exit(0)
            else: 
                os.waitpid(child_pid, 0)
                self.initscriptchanged = False
        else: logger.log('%s: not starting, is not enabled' % self.name)

    def stop(self):
        logger.log('%s: stopping' % self.name)
        vserver.VServer.stop(self)

    def is_running(self): 
        return vserver.VServer.is_running(self)

    def set_resources(self,setup=False):
        disk_max = self.rspec['disk_max']
        logger.log('%s: setting max disk usage to %d KiB' % (self.name, disk_max))
        try:  # if the sliver is over quota, .set_disk_limit will throw an exception
            if not self.disk_usage_initialized:
                self.vm_running = False
                Sliver_VS._init_disk_info_sem.acquire()
                logger.log('%s: computing disk usage: beginning' % self.name)
                try: self.init_disk_info()
                finally: Sliver_VS._init_disk_info_sem.release()
                logger.log('%s: computing disk usage: ended' % self.name)
                self.disk_usage_initialized = True
            vserver.VServer.set_disklimit(self, max(disk_max, self.disk_blocks))
        except:
            logger.log('%s: failed to set max disk usage' % self.name)
            logger.log_exc(self.name)

        # get/set the min/soft/hard values for all of the vserver
        # related RLIMITS.  Note that vserver currently only
        # implements support for hard limits.
        for limit in vserver.RLIMITS.keys():
            type = limit.lower()
            minimum  = self.rspec['%s_min'%type]
            soft = self.rspec['%s_soft'%type]
            hard = self.rspec['%s_hard'%type]
            update = self.set_rlimit(limit, hard, soft, minimum)
            if update:
                logger.log('%s: setting rlimit %s to (%d, %d, %d)'
                           % (self.name, type, hard, soft, minimum))

        self.set_capabilities_config(self.rspec['capabilities'])
        if self.rspec['capabilities']:
            logger.log('%s: setting capabilities to %s' % (self.name, self.rspec['capabilities']))

        cpu_pct = self.rspec['cpu_pct']
        cpu_share = self.rspec['cpu_share']

        if setup:
            for key in self.rspec.keys():
                if key.find('sysctl.') == 0:
                    sysctl=key.split('.')
                    try:
                        path="/proc/sys/%s" % ("/".join(sysctl[1:]))
                        logger.log("%s: opening %s"%(self.name,path))
                        flags = os.O_WRONLY
                        fd = os.open(path, flags)
                        logger.log("%s: writing %s=%s"%(self.name,key,self.rspec[key]))
                        os.write(fd,self.rspec[key])
                        os.close(fd)
                    except IOError, e:
                        logger.log("%s: could not set %s=%s"%(self.name,key,self.rspec[key]))
                        logger.log("%s: error = %s"%(self.name,e))


        if self.rspec['enabled'] > 0:
            if cpu_pct > 0:
                logger.log('%s: setting cpu reservation to %d%%' % (self.name, cpu_pct))
            else:
                cpu_pct = 0

            if cpu_share > 0:
                logger.log('%s: setting cpu share to %d' % (self.name, cpu_share))
            else:
                cpu_share = 0

            self.set_sched_config(cpu_pct, cpu_share)
            # if IP address isn't set (even to 0.0.0.0), sliver won't be able to use network
            if self.rspec['ip_addresses'] != '0.0.0.0':
                logger.log('%s: setting IP address(es) to %s' % \
                (self.name, self.rspec['ip_addresses']))
            self.set_ipaddresses_config(self.rspec['ip_addresses'])

            if self.is_running():
                logger.log("%s: Setting name to %s" % (self.name, self.slice_id),2) 
                self.setname(self.slice_id) 
                ### Sapan's change needs more work - /etc/vservers not available here, we're in the chroot
                #logger.log("%s: Storing slice id of %s for PlanetFlow" % (self.name, self.slice_id),2)
                #file('/etc/vservers/%s/slice_id' % self.name, 'w').write(self.slice_id)

            if self.enabled == False:
                self.enabled = True
                self.start()
 
            if False: # Does not work properly yet.
                if self.have_limits_changed():
                    logger.log('%s: limits have changed --- restarting' % self.name)
                    stopcount = 10
                    while self.is_running() and stopcount > 0:
                        self.stop()
                        delay = 1
                        time.sleep(delay)
                        stopcount = stopcount - 1
                    self.start()

        else:  # tell vsh to disable remote login by setting CPULIMIT to 0
            logger.log('%s: disabling remote login' % self.name)
            self.set_sched_config(0, 0)
            self.enabled = False
            self.stop()
