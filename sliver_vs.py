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
            vref='default'
        try:
            ### locating the right slicefamily
            # this is a first draft, and more a proof of concept thing
            # the idea is to parse vref for dash-separated wishes,
            # and to project these against the defaults
            # so e.g. if the default slice family (as found in /etc/planetlab/slicefamily)
            # is planetlab-f8-i386, then here is what we get
            # vref=x86_64             -> vuseradd -t planetlab-f8-x86_64 
            # vref=centos5            -> vuseradd -t planetlab-centos5-i386 
            # vref=centos5-onelab     -> vuseradd -t onelab-centos5-i386 
            # vref=planetflow         -> vuseradd -t planetflow-f8-i386
            # vref=x86_64-planetflow  -> vuseradd -t planetflow-f8-x86_64

            # default
            default=file("/etc/planetlab/slicefamily").read().strip()
            (pldistro,fcdistro,arch) = default.split("-")

            known_archs = [ 'i386', 'x86_64' ]
            known_fcdistros = [ 'centos5', 'f8', 'f9', 'f10', 'f11', 'f12' ]
            # from the slice attribute: cut dashes and try to figure the meaning
            slice_wishes = vref.split("-")
            for wish in slice_wishes:
                if wish in known_archs:
                    arch=wish
                elif wish in known_fcdistros:
                    fcdistro=wish
                else:
                    pldistro=wish

            # rejoin the parts
            refname="-".join( (pldistro,fcdistro,arch) )

            # check the template exists -- there's probably a better way..
            if not os.path.isdir ("/vservers/.vref/%s"%refname):
                logger.log("%s (%s) : vref %s not found, using default %s"%(
                        name,vref,refname,default))
                refname=default
                # reset so arch is right
                (pldistro,fcdistro,arch) = default.split("-")
                # could check again, but as we have /etc/slicefamily 
                # there's probably no /vservers/.vref/default

        except IOError:
            # have not found slicefamily
            logger.log("%s (%s): legacy node - using fallback vrefname 'default'"%(name,vref))
            # for legacy nodes
            refname="default"
            arch="i386"
        except:
            logger.log("%s (%s) : unexpected error follows - using 'default'"%(name,vref))
            logger.log(traceback.format_exc())
            refname="default"
            arch="i386"
            
        def personality (arch):
            personality="linux32"
            if arch.find("64")>=0:
                personality="linux64"
            return personality

        logger.log_call('/usr/sbin/vuseradd', '-t', refname, name)
        # export slicename to the slice in /etc/slicename
        file('/vservers/%s/etc/slicename' % name, 'w').write(name)
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
            # not used anymore, we always check against the installed script
            #self.initscriptchanged = True
            self.refresh_slice_vinit()

        accounts.Account.configure(self, rec)  # install ssh keys

    # unconditionnally install and enable the generic vinit script
    # mimicking chkconfig for enabling the generic vinit script
    # this is hardwired for runlevel 3
    def install_and_enable_vinit (self):
        vinit_source="/usr/share/NodeManager/sliver-initscripts/vinit"
        vinit_script="/vservers/%s/etc/rc.d/init.d/vinit"%self.name
        rc3_link="/vservers/%s/etc/rc.d/rc3.d/S99vinit"%self.name
        rc3_target="../init.d/vinit"
        # install in sliver
        body=file(vinit_source).read()
        if tools.replace_file_with_string(vinit_script,body,chmod=0755):
            logger.log("vsliver_vs: %s: installed generic vinit rc script"%self.name)
        # create symlink for runlevel 3
        if not os.path.islink(rc3_link):
            try:
                logger.log("vsliver_vs: %s: creating runlevel3 symlink %s"%(self.name,rc3_link))
                os.symlink(rc3_target,rc3_link)
            except:
                logger.log_exc("vsliver_vs: %s: failed to create runlevel3 symlink %s"%rc3_link)

    # this one checks for the existence of the slice initscript
    # install or remove the slice inistscript, as instructed by the initscript tag
    def refresh_slice_vinit(self):
        body=self.initscript
        sliver_initscript="/vservers/%s/etc/rc.d/init.d/vinit.slice"%self.name
        if tools.replace_file_with_string(sliver_initscript,body,remove_if_empty=True,chmod=0755):
            if body:
                logger.log("vsliver_vs: %s: Installed new initscript in %s"%(self.name,sliver_initscript))
            else:
                logger.log("vsliver_vs: %s: Removed obsolete initscript %s"%(self.name,sliver_initscript))

    def start(self, delay=0):
        if self.rspec['enabled'] <= 0:
            logger.log('sliver_vs: not starting %s, is not enabled'%self.name)
        else:
            logger.log('sliver_vs: %s: starting in %d seconds' % (self.name, delay))
            time.sleep(delay)
            # the generic /etc/init.d/vinit script is permanently refreshed, and enabled
            self.install_and_enable_vinit()
            # if a change has occured in the slice initscript, reflect this in /etc/init.d/vinit.slice
            self.refresh_slice_vinit()
            child_pid = os.fork()
            if child_pid == 0:
                # VServer.start calls fork() internally,
                # so just close the nonstandard fds and fork once to avoid creating zombies
                tools.close_nonstandard_fds()
                vserver.VServer.start(self)
                os._exit(0)
            else:
                os.waitpid(child_pid, 0)

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

            try:
                vserver_config_path = '/etc/vservers/%s'%self.name
                if not os.path.exists (vserver_config_path):
                    os.makedirs (vserver_config_path)
                file('%s/slice_id'%vserver_config_path, 'w').write("%d"%self.slice_id)
                logger.log("sliver_vs: Recorded slice id %d for slice %s"%(self.slice_id,self.name))
            except IOError,e:
                logger.log("sliver_vs: Could not record slice_id for slice %s. Error: %s"%(self.name,str(e)))
            except Exception,e:
                logger.log_exc("sliver_vs: Error recording slice id: %s"%str(e),name=self.name)

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
