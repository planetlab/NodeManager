# $Id$
# $URL$

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
    log('(v) '+msg,LOG_VERBOSE)

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
    except: log_exc('failed to run command %s' % ' '.join(args))

def log_exc(msg="",name=None):
    """Log the traceback resulting from an exception."""
    if name: 
        log("%s: EXCEPTION caught <%s> \n %s" %(name, msg, traceback.format_exc()))
    else:
        log("EXCEPTION caught <%s> \n %s" %(msg, traceback.format_exc()))

# for some reason the various modules are still triggered even when the
# data from PLC cannot be reached
# we show this message instead of the exception stack instead in this case
def log_missing_data (msg,key):
    log("%s: could not find the %s key in data (PLC connection down?) - IGNORED"%(msg,key))

def log_data_in_file (data, file, message=""):
    import pprint, time
    try:
        f=open(file,'w')
        now=time.strftime("Last update: %Y.%m.%d at %H:%M:%S %Z", time.localtime())
        f.write(now+'\n')
        if message: f.write('Message:'+message+'\n')
        pp=pprint.PrettyPrinter(stream=f,indent=2)
        pp.pprint(data)
        f.close()
    except:
        log_verbose('log_data_in_file failed - file=%s - message=%r'%(file,message))

def log_slivers (data):
    log_data_in_file (data, LOG_SLIVERS, "raw GetSlivers")
