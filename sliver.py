import base64
import errno
import os
import vserver

from config import DEFAULT_RSPEC
import accounts
import logger
import tools


class Sliver(vserver.VServer):
    """This class wraps vserver.VServer to make its interface closer to what we need for the Node Manager."""

    SHELL = '/bin/vsh'
    TYPE = 'sliver'

    def __init__(self, name):
        vserver.VServer.__init__(self, name, vm_running=True)
        self.disk_limit_has_been_set = False
        self.rspec = DEFAULT_RSPEC.copy()
        self.ssh_keys = None
        self.initscript = ''

    @staticmethod
    def create(name): logger.log_call('/usr/sbin/vuseradd', name)

    @staticmethod
    def destroy(name): logger.log_call('/usr/sbin/vuserdel', name)

    def configure(self, rec):
        self.rspec.update(rec['eff_rspec'])
        self.set_resources()
        if rec['ssh_keys'] != self.ssh_keys:
            accounts.install_ssh_keys(rec)
            self.ssh_keys = rec['ssh_keys']
        if rec['initscript'] != self.initscript:
            logger.log('%s: installing initscript' % self.name)
            def install_initscript():
                flags = os.O_WRONLY|os.O_CREAT|os.O_TRUNC
                fd = os.open('/etc/rc.vinit', flags, 0755)
                os.write(fd, base64.b64decode(rec['initscript']))
                os.close(fd)
            try: self.chroot_call(install_initscript)
            except OSError, e:
                if e.errno != errno.EEXIST: logger.log_exc()
            self.initscript = rec['initscript']

    def start(self):
        if self.rspec['nm_enabled']:
            logger.log('%s: starting' % self.name)
            child_pid = os.fork()
            if child_pid == 0:
                # VServer.start calls fork() internally, so we don't need all of fork_as()
                tools.close_nonstandard_fds()
                vserver.VServer.start(self, True)
                os._exit(0)
            else: os.waitpid(child_pid, 0)
        else: logger.log('%s: not starting, is not enabled' % self.name)

    def stop(self):
        logger.log('%s: stopping' % self.name)
        vserver.VServer.stop(self)
        # make sure we always make the syscalls when setting resource limits
        self.vm_running = True

    def set_resources(self):
        """Set the resource limits of sliver <self.name>."""
        # disk limits
        disk_max_KiB = self.rspec['nm_disk_quota']
        logger.log('%s: setting max disk usage to %d KiB' %
                   (self.name, disk_max_KiB))
        try:  # don't let slivers over quota escape other limits
            if not self.disk_limit_has_been_set:
                self.vm_running = False
                logger.log('%s: computing disk usage' % self.name)
                self.init_disk_info()
                # even if set_disklimit() triggers an exception,
                # the kernel probably knows the disk usage
                self.disk_limit_has_been_set = True
            vserver.VServer.set_disklimit(self, disk_max_KiB)
            self.vm_running = True
        except OSError: logger.log_exc()

        # bw limits
        bw_fields = ['nm_net_min_rate', 'nm_net_max_rate',
                     'nm_net_exempt_min_rate', 'nm_net_exempt_max_rate',
                     'nm_net_share']
        args = tuple(map(self.rspec.__getitem__, bw_fields))
        logger.log('%s: setting bw share to %d' % (self.name, args[-1]))
        logger.log('%s: setting bw limits to %s bps' % (self.name, args[:-1]))
        self.set_bwlimit(*args)

        # cpu limits / remote login
        cpu_guaranteed_shares = self.rspec['nm_cpu_guaranteed_share']
        cpu_shares = self.rspec['nm_cpu_share']
        if self.rspec['nm_enabled']:
            if cpu_guaranteed_shares > 0:
                logger.log('%s: setting cpu share to %d%% guaranteed' %
                           (self.name, cpu_guaranteed_shares/10.0))
                self.set_sched_config(cpu_guaranteed_shares,
                                      vserver.SCHED_CPU_GUARANTEED)
            else:
                logger.log('%s: setting cpu share to %d' %
                           (self.name, cpu_shares))
                self.set_sched_config(cpu_shares, 0)
        else:
            # tell vsh to disable remote login by setting CPULIMIT to 0
            logger.log('%s: disabling remote login' % self.name)
            self.set_sched_config(0, 0)
            self.stop()
