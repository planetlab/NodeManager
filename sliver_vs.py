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
import vserver

import accounts
import logger
import tools


class Sliver_VS(accounts.Account, vserver.VServer):
    """This class wraps vserver.VServer to make its interface closer to what we need for the Node Manager."""

    SHELL = '/bin/vsh'
    TYPE = 'sliver.VServer'

    def __init__(self, rec):
        vserver.VServer.__init__(self, rec['name'])
        self.keys = ''
        self.rspec = {}
        self.initscript = ''
        self.disk_usage_initialized = False
        self.configure(rec)

    @staticmethod
    def create(name): logger.log_call('/usr/sbin/vuseradd', name)

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

    def start(self):
        if self.rspec['enabled']:
            logger.log('%s: starting' % self.name)
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
                logger.log('%s: computing disk usage' % self.name)
                self.init_disk_info()
                self.disk_usage_initialized = True
            vserver.VServer.set_disklimit(self, disk_max)
        except OSError: logger.log_exc()

        net_limits = (self.rspec['net_min'], self.rspec['net_max'], self.rspec['net2_min'], self.rspec['net2_max'], self.rspec['net_share'])
        logger.log('%s: setting net limits to %s bps' % (self.name, net_limits[:-1]))
        logger.log('%s: setting net share to %d' % (self.name, net_limits[-1]))
        self.set_bwlimit(*net_limits)

        cpu_min = self.rspec['cpu_min']
        cpu_share = self.rspec['cpu_share']
        if self.rspec['enabled']:
            if cpu_min > 0:
                logger.log('%s: setting cpu share to %d%% guaranteed' % (self.name, cpu_min/10.0))
                self.set_sched_config(cpu_min, vserver.SCHED_CPU_GUARANTEED)
            else:
                logger.log('%s: setting cpu share to %d' % (self.name, cpu_share))
                self.set_sched_config(cpu_share, 0)
        else:  # tell vsh to disable remote login by setting CPULIMIT to 0
            logger.log('%s: disabling remote login' % self.name)
            self.set_sched_config(0, 0)
            self.stop()
