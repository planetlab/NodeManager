#
# Something relevant
#
"""A very simple logger that tries to be concurrency-safe."""

import os, sys
import subprocess
import time
import traceback


LOG_FILE = '/var/log/nm'
LOG_SLIVERS = '/var/log/getslivers.txt'

# Thierry - trying to debug this for 4.2
# basically define 3 levels
LOG_NONE=0
LOG_NODE=1
LOG_VERBOSE=2
# default is to log a reasonable amount of stuff for when running on operational nodes
LOG_LEVEL=1

def set_level(level):
    global LOG_LEVEL
    assert level in [LOG_NONE,LOG_NODE,LOG_VERBOSE]
    LOG_LEVEL=level

def verbose(msg):
    log(msg,LOG_VERBOSE)

def log(msg,level=LOG_NODE):
    """Write <msg> to the log file if level >= current log level (default LOG_NODE)."""
    if (level > LOG_LEVEL):
        return
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
    try: 
        child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        child.wait() # wait for proc to hang up
        if child.returncode:
                raise Exception("command failed:\n stdout - %s\n stderr - %s" % \
                        (child.stdout.readlines(), child.stderr.readlines()))
    except: log_exc()

def log_exc(name = None):
    """Log the traceback resulting from an exception."""
    if name:  
        log("operation on %s failed.  \n %s" %(name, traceback.format_exc()))
    else:
        log(traceback.format_exc())

def log_slivers (data):
    import pprint, time
    try:
        f=open(LOG_SLIVERS,'w')
        now=time.strftime("GetSlivers stored on %Y.%m.%d at %H:%M:%S", time.localtime())
        f.write(now+'\n')
        pp=pprint.PrettyPrinter(stream=f,indent=2)
        pp.pprint(data)
        f.close()
    except:
        log_verbose('Cannot save GetSlivers in %s'%LOG_SLIVERS)
