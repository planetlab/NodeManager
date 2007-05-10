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
import os
import threading
import time
import vserver

import accounts
import logger
import tools

# special constant that tells vserver to keep its existing settings
KEEP_LIMIT = vserver.VC_LIM_KEEP

class Sliver_VS(accounts.Account, vserver.VServer):
    """This class wraps vserver.VServer to make its interface closer to what we need."""

    SHELL = '/bin/vsh'
    TYPE = 'sliver.VServer'
    _init_disk_info_sem = threading.Semaphore(1)

    def __init__(self, rec):
        try:
            vserver.VServer.__init__(self, rec['name'])
        except Exception, err:
            if not isinstance(err, vserver.NoSuchVServer):
                # Probably a bad vserver or vserver configuration file
                logger.log_exc()
                logger.log('%s: recreating bad vserver' % rec['name'])
                self.destroy(rec['name'])
            self.create(rec['name'], rec['vref'])
            vserver.VServer.__init__(self, rec['name'])

        self.keys = ''
        self.rspec = {}
        self.initscript = ''
        self.disk_usage_initialized = False
        self.configure(rec)

    @staticmethod
    def create(name, vref = None):
        if vref is not None:
            logger.log_call('/usr/sbin/vuseradd', '-t', vref, name)
        else:
            logger.log_call('/usr/sbin/vuseradd', name)
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
            try: self.chroot_call(install_initscript)
            except: logger.log_exc()

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
            vserver.VServer.set_disklimit(self, disk_max)
        except OSError:
            logger.log('%s: failed to set max disk usage' % self.name)
            logger.log_exc()

        # set min/soft/hard values for 'as', 'rss', 'nproc' and openfd
        # Note that vserver currently only implements support for hard limits

        as_min  = self.rspec['as_min']
        as_soft = self.rspec['as_soft']
        as_hard = self.rspec['as_hard']
        self.set_AS_config(as_hard, as_soft, as_min)

        rss_min  = self.rspec['rss_min']
        rss_soft = self.rspec['rss_soft']
        rss_hard = self.rspec['rss_hard']
        self.set_RSS_config(rss_hard, rss_soft, rss_min)

        nproc_min  = self.rspec['nproc_min']
        nproc_soft = self.rspec['nproc_soft']
        nproc_hard = self.rspec['nproc_hard']
        self.set_NPROC_config(nproc_hard, nproc_soft, nproc_min)

        openfd_min  = self.rspec['openfd_min']
        openfd_soft = self.rspec['openfd_soft']
        openfd_hard = self.rspec['openfd_hard']
        self.set_OPENFD_config(openfd_hard, openfd_soft, openfd_min)

        self.set_WHITELISTED_config(self.rspec['whitelist'])

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

        cpu_min = self.rspec['cpu_min']
        cpu_share = self.rspec['cpu_share']

        if self.rspec['enabled'] > 0 and self.rspec['whitelist'] == 1:
            if cpu_min >= 50:  # at least 5%: keep people from shooting themselves in the foot
                logger.log('%s: setting cpu share to %d%% guaranteed' % (self.name, cpu_min/10.0))
                self.set_sched_config(cpu_min, vserver.SCHED_CPU_GUARANTEED)
            else:
                logger.log('%s: setting cpu share to %d' % (self.name, cpu_share))
                self.set_sched_config(cpu_share, 0)

            if self.have_limits_changed():
                logger.log('%s: limits have changed --- restarting' % self.name)
                stopcount = 10
                while self.isrunning() and stopcount > 0:
                    self.stop()
                    delay = 1
                    time.sleep(delay)
                    stopcount = stopcount - 1
                self.start()

        else:  # tell vsh to disable remote login by setting CPULIMIT to 0
            logger.log('%s: disabling remote login' % self.name)
            self.set_sched_config(0, 0)
            self.stop()
