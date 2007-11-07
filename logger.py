#
# Something relevant
#
"""A very simple logger that tries to be concurrency-safe."""

import os, sys
import subprocess
import time
import traceback


LOG_FILE = '/var/log/nm'

def log(msg):
    """Write <msg> to the log file."""
    try:
        fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0600)
        if not msg.endswith('\n'): msg += '\n'
        os.write(fd, '%s: %s' % (time.asctime(time.gmtime()), msg))
        os.close(fd)
    except OSError:
        sys.stderr.write(msg)
        sys.stderr.flush()

def log_call(*args):
    log('running command %s' % ' '.join(args))
    try: subprocess.call(args, close_fds=True)
    except: log_exc()

def log_exc(name = None):
    """Log the traceback resulting from an exception."""
    log("operation on %s failed.  \n %s" %(self.name, traceback.format_exc()))
