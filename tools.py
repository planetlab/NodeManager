import cPickle
import errno
import os
import pwd
import tempfile
import threading

import logger


PID_FILE = '/var/run/node_mgr.pid'

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
    for fd in range(3): os.dup2(devnull, fd)

def deepcopy(obj):
    """Return a deep copy of obj."""
    return cPickle.loads(cPickle.dumps(obj, -1))

def fork_as(su, function, *args):
    """fork(), cd / to avoid keeping unused directories open, close all nonstandard file descriptors (to avoid capturing open sockets), fork() again (to avoid zombies) and call <function> with arguments <args> in the grandchild process.  If <su> is not None, set our group and user ids appropriately in the child process."""
    child_pid = os.fork()
    if child_pid == 0:
        try:
            os.chdir('/')
            close_nonstandard_fds()
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

def write_file(filename, do_write):
    """Write file <filename> atomically by opening a temporary file, using <do_write> to write that file, and then renaming the temporary file."""
    os.rename(write_temp_file(do_write), filename)

def write_temp_file(do_write):
    fd, temporary_filename = tempfile.mkstemp()
    f = os.fdopen(fd, 'w')
    try: do_write(f)
    finally: f.close()
    return temporary_filename
