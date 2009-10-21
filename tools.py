"""A few things that didn't seem to fit anywhere else."""

import cPickle
import errno
import os
import pwd
import tempfile
import threading
import fcntl
import commands
import logger

PID_FILE = '/var/run/nm.pid'

def get_default_if():
    interface = get_if_from_hwaddr(get_hwaddr_from_plnode())
    if not interface: interface = "eth0"
    return interface

def get_hwaddr_from_plnode():
    for line in open("/usr/boot/plnode.txt", 'r').readlines():
        if line.startswith("NET_DEVICE"):
            return line.split("=")[1].strip().strip('"')
    return None

def get_if_from_hwaddr(hwaddr):
   import sioc
   devs = sioc.gifconf()
   for dev in devs:
      dev_hwaddr = sioc.gifhwaddr(dev)
      if dev_hwaddr == hwaddr: return dev
   return None

def as_daemon_thread(run):
    """Call function <run> with no arguments in its own thread."""
    thr = threading.Thread(target=run)
    thr.setDaemon(True)
    thr.start()

def close_nonstandard_fds():
    """Close all open file descriptors other than 0, 1, and 2."""
    _SC_OPEN_MAX = 4
    for fd in range(3, os.sysconf(_SC_OPEN_MAX)):
        try: os.close(fd)
        except OSError: pass  # most likely an fd that isn't open

# after http://www.erlenstar.demon.co.uk/unix/faq_2.html
def daemon():
    """Daemonize the current process."""
    if os.fork() != 0: os._exit(0)
    os.setsid()
    if os.fork() != 0: os._exit(0)
    os.chdir('/')
    os.umask(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    # xxx fixme - this is just to make sure that nothing gets stupidly lost - should use devnull
    crashlog = os.open('/var/log/nm.daemon', os.O_RDWR | os.O_APPEND | os.O_CREAT, 0644)
    os.dup2(crashlog, 1)
    os.dup2(crashlog, 2)

def fork_as(su, function, *args):
    """fork(), cd / to avoid keeping unused directories open, close all nonstandard file descriptors (to avoid capturing open sockets), fork() again (to avoid zombies) and call <function> with arguments <args> in the grandchild process.  If <su> is not None, set our group and user ids appropriately in the child process."""
    child_pid = os.fork()
    if child_pid == 0:
        try:
            os.chdir('/')
            close_nonstandard_fds()
            if su:
                pw_ent = pwd.getpwnam(su)
                os.setegid(pw_ent[3])
                os.seteuid(pw_ent[2])
            child_pid = os.fork()
            if child_pid == 0: function(*args)
        except:
            os.seteuid(os.getuid())  # undo su so we can write the log file
            os.setegid(os.getgid())
            logger.log_exc()
        os._exit(0)
    else: os.waitpid(child_pid, 0)

def pid_file():
    """We use a pid file to ensure that only one copy of NM is running at a given time.  If successful, this function will write a pid file containing the pid of the current process.  The return value is the pid of the other running process, or None otherwise."""
    other_pid = None
    if os.access(PID_FILE, os.F_OK):  # check for a pid file
        handle = open(PID_FILE)  # pid file exists, read it
        other_pid = int(handle.read())
        handle.close()
        # check for a process with that pid by sending signal 0
        try: os.kill(other_pid, 0)
        except OSError, e:
            if e.errno == errno.ESRCH: other_pid = None  # doesn't exist
            else: raise  # who knows
    if other_pid == None:
        # write a new pid file
        write_file(PID_FILE, lambda f: f.write(str(os.getpid())))
    return other_pid

def write_file(filename, do_write, **kw_args):
    """Write file <filename> atomically by opening a temporary file, using <do_write> to write that file, and then renaming the temporary file."""
    os.rename(write_temp_file(do_write, **kw_args), filename)

def write_temp_file(do_write, mode=None, uidgid=None):
    fd, temporary_filename = tempfile.mkstemp()
    if mode: os.chmod(temporary_filename, mode)
    if uidgid: os.chown(temporary_filename, *uidgid)
    f = os.fdopen(fd, 'w')
    try: do_write(f)
    finally: f.close()
    return temporary_filename

# utilities functions to get (cached) information from the node

# get node_id from /etc/planetlab/node_id and cache it
_node_id=None
def node_id():
    global _node_id
    if _node_id is None:
        try:
            _node_id=int(file("/etc/planetlab/node_id").read())
        except:
            _node_id=""
    return _node_id

# get slicefamily from /etc/planetlab/slicefamily and cache it
# http://svn.planet-lab.org/wiki/SliceFamily
_slicefamily=None
def slicefamily():
    global _slicefamily
    if _slicefamily is None:
        try:
            _slicefamily=file("/etc/planetlab/slicefamily").read().strip()
        except:
            _slicefamily=""
    return _slicefamily

_root_context_arch=None
def root_context_arch():
    global _root_context_arch
    if not _root_context_arch:
        _root_context_arch=commands.getoutput("uname -i")
    return _root_context_arch


class NMLock:
    def __init__(self, file):
        logger.log("Lock %s initialized." % file, 2)
        self.fd = os.open(file, os.O_RDWR|os.O_CREAT, 0600)
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFD)
        flags |= fcntl.FD_CLOEXEC
        fcntl.fcntl(self.fd, fcntl.F_SETFD, flags)
    def __del__(self):
        os.close(self.fd)
    def acquire(self):
        logger.log("Lock acquired.", 2)
        fcntl.lockf(self.fd, fcntl.LOCK_SH)
    def release(self):
        logger.log("Lock released.", 2)
        fcntl.lockf(self.fd, fcntl.LOCK_UN)
