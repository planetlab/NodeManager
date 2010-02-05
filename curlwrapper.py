# $Id$
# $URL$

from subprocess import PIPE, Popen
from select import select
# raise xmplrpclib.ProtocolError
import xmlrpclib
import signal
import os
import logger

class Sopen(Popen):
    def kill(self, signal = signal.SIGTERM):
        os.kill(self.pid, signal)

def retrieve(url, cacert=None, postdata=None, timeout=90):
#    options = ('/usr/bin/curl', '--fail', '--silent')
    options = ('/usr/bin/curl', '--fail', )
    if cacert: options += ('--cacert', cacert)
    if postdata: options += ('--data', '@-')
    if timeout: 
        options += ('--max-time', str(timeout))
        options += ('--connect-timeout', str(timeout))
    p = Sopen(options + (url,), stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
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
