# Note
# in spring 2010, an attempt was made to use pycurl instead of forking curl
# it turned out, however, that after around 10 cycles of the nodemanager,
# attempts to call GetSlivers were failing with a curl error 60
# we are thus reverting to the version from tag curlwrapper.py-NodeManager-2.0-8
# the (broken) pycurl version can be found in tags 2.0-9 and 2.0-10

from subprocess import PIPE, Popen
from select import select
import xmlrpclib
import signal
import os

import logger

verbose=False
#verbose=True

class Sopen(Popen):
    def kill(self, signal = signal.SIGTERM):
        os.kill(self.pid, signal)

def retrieve(url, cacert=None, postdata=None, timeout=90):
#    command = ('/usr/bin/curl', '--fail', '--silent')
    command = ('/usr/bin/curl', '--fail', )
    if cacert: command += ('--cacert', cacert)
    if postdata: command += ('--data', '@-')
    if timeout: 
        command += ('--max-time', str(timeout))
        command += ('--connect-timeout', str(timeout))
    command += (url,)
    if verbose:
        print 'Invoking ',command
        if postdata: print 'with postdata=',postdata
    p = Sopen(command , stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
    if postdata: p.stdin.write(postdata)
    p.stdin.close()
    sout, sin, serr = select([p.stdout,p.stderr],[],[], timeout)
    if len(sout) == 0 and len(sin) == 0 and len(serr) == 0: 
        logger.verbose("curlwrapper: timed out after %s" % timeout)
        p.kill(signal.SIGKILL) 
    data = p.stdout.read()
    err = p.stderr.read()
    rc = p.wait()
    if rc != 0: 
        # when this triggers, the error sometimes doesn't get printed
        logger.log ("curlwrapper: retrieve, got stderr <%s>"%err)
        raise xmlrpclib.ProtocolError(url, rc, err, postdata)
    else: 
        return data
