# $Id$

from subprocess import PIPE, Popen
# raise xmplrpclib.ProtocolError
import xmlrpclib

def retrieve(url, cacert=None, postdata=None, timeout=300):
    options = ('/usr/bin/curl', '--fail', '--silent')
    if cacert: options += ('--cacert', cacert)
    if postdata: options += ('--data', '@-')
    if timeout: options += ('--max-time', str(timeout))
    p = Popen(options + (url,), stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
    if postdata: p.stdin.write(postdata)
    p.stdin.close()
    data = p.stdout.read()
    err = p.stderr.read()
    rc = p.wait()
    if rc != 0: 
        # when this triggers, the error sometimes doesn't get printed
        print 'curlwrapper.retrieve: raising xmlrpclib.ProtocolError\n  (url=%s,code=%d,stderr=%s,post=%r)'\
            %(url,rc,err,postdata)
        if cacert: print "Using cacert file %s"%cacert
        raise xmlrpclib.ProtocolError(url, rc, err, postdata)
    else: 
        return data
