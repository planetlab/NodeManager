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
import os, os.path
import time
import vserver

import accounts
import logger
import tools

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
    _init_disk_info_sem = tools.NMLock("/var/run/nm-disk-info.lock")

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
        self.disk_usage_initialized = False
        self.initscriptchanged = False
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
            # however for cases like when vref is 'planetflow', if we do not understand
            # any of the wishes we take vref as is
            # this could be improved by having the vserver-reference init script be a bit smarter
            # so we could take planetflow as the pldistro part here
            as_is=None
            # defaults
            default=file("/etc/planetlab/defaultvref").read()
            (pldistro,fcdistro,arch) = default.split("-")
            # from the slice attribute: cut dashes and try to figure the meaning
            slice_wishes = vref.split("-")
            for wish in slice_wishes:
                if wish == "i386" or wish == "x86_64":
                    arch=wish
                elif wish == "planetlab" or wish == "onelab" or wish == "vini":
                    pldistro=wish
                elif wish == "f8" or wish == "centos5" :
                    fcdistro=wish
                else:
                    # if we find something like e.g. planetflow, use it as-is
                    as_is=vref
                    break
            if as_is:
                refname=as_is
            else:
                refname="-".join( (pldistro,fcdistro,arch) )
            # check the templates exists -- there's probably a better way..
            if not os.path.isdir ("/vservers/.vref/%s"%refname):
                log.verbose("%s (%s) : vref %s not found, using default %s"%(
                        name,vref,refname,default))
                refname=default
            except IOError:
                # have not found defaultvref
                logger.verbose("%s (%s): using fallback vrefname 'default'"%(name,vref))
                # for legacy nodes
                refname="default"
            except:
                import traceback
                logger.log("%s (%s) : unexpected error follows - using 'default'"%(
                        name,vref))
                logger.log(traceback.format_exc())
            
            logger.log_call('/usr/sbin/vuseradd', '-t', refname, name)
        open('/vservers/%s/etc/slicename' % name, 'w').write(name)

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
            logger.log('%s: installing initscript' % self.name)
            def install_initscript():
                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                fd = os.open('/etc/rc.vinit', flags, 0755)
                os.write(fd, new_initscript)
                os.close(fd)
            try:
                self.chroot_call(install_initscript)
                self.initscriptchanged = True
            except: logger.log_exc(self.name)

        accounts.Account.configure(self, rec)  # install ssh keys

    def start(self, delay=0):
        if self.rspec['enabled'] > 0:
            logger.log('%s: starting in %d seconds' % (self.name, delay))
            time.sleep(delay)
            child_pid = os.fork()
            if child_pid == 0:
                # VServer.start calls fork() internally, so just close the nonstandard fds and fork once to avoid creating zombies
                tools.close_nonstandard_fds()
                vserver.VServer.start(self, True)
                os._exit(0)
            else: os.waitpid(child_pid, 0)
        else: logger.log('%s: not starting, is not enabled' % self.name)
        self.initscriptchanged = False

    def stop(self):
        logger.log('%s: stopping' % self.name)
        vserver.VServer.stop(self)

    def set_resources(self):
        disk_max = self.rspec['disk_max']
        logger.log('%s: setting max disk usage to %d KiB' % (self.name, disk_max))
        try:  # if the sliver is over quota, .set_disk_limit will throw an exception
            if not self.disk_usage_initialized:
                self.vm_running = False
                logger.log('%s: computing disk usage: beginning' % self.name)
                Sliver_VS._init_disk_info_sem.acquire()
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

        if False: # this code was commented out before
            # N.B. net_*_rate are in kbps because of XML-RPC maxint
            # limitations, convert to bps which is what bwlimit.py expects.
            net_limits = (self.rspec['net_min_rate'] * 1000,
                          self.rspec['net_max_rate'] * 1000,
                          self.rspec['net_i2_min_rate'] * 1000,
                          self.rspec['net_i2_max_rate'] * 1000,
                          self.rspec['net_share'])
            logger.log('%s: setting net limits to %s bps' % (self.name, net_limits[:-1]))
            logger.log('%s: setting net share to %d' % (self.name, net_limits[-1]))
            self.set_bwlimit(*net_limits)

        cpu_pct = self.rspec['cpu_pct']
        cpu_share = self.rspec['cpu_share']

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
                logger.log('%s: setting IP address(es) to %s' % (self.name, self.rspec['ip_addresses']))
            self.set_ipaddresses_config(self.rspec['ip_addresses'])

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
            self.stop()
