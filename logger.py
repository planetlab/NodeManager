import fcntl
import os
import subprocess
import time
import traceback

from config import LOG_FILE


def log(msg):
    """Write <msg> to the log file."""
    # the next three lines ought to be an atomic operation but aren't
    fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0600)
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
    if not msg.endswith('\n'): msg += '\n'
    os.write(fd, '%s: %s' % (time.asctime(time.gmtime()), msg))
    os.close(fd)

def log_call(*args):
    log('running command %s' % ' '.join(args))
    try: subprocess.call(args)
    except: log_exc()

def log_exc():
    """Log the traceback resulting from an exception."""
    log(traceback.format_exc())
