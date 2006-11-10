"""Leverage curl to make XMLRPC requests that check the server's credentials."""

from subprocess import PIPE, Popen
import xmlrpclib


CURL = '/usr/bin/curl'

class CertificateCheckingSafeTransport(xmlrpclib.Transport):
    def request(self, host, handler, request_body, verbose=0):
        self.verbose = verbose
        p = Popen((CURL, '--cacert', '/usr/boot/cacert.pem', '--data', '@-', 'https://%s%s' % (host, handler)), stdin=PIPE, stdout=PIPE, stderr=PIPE)
        p.stdin.write(request_body)
        p.stdin.close()
        contents = p.stdout.read()
        p.stdout.close()
        error = p.stderr.read()
        p.stderr.close()
        rc = p.wait()
        if rc != 0: raise xmlrpclib.ProtocolError(host + handler, rc, error, '')
        return xmlrpclib.loads(contents)[0]

class ServerProxy(xmlrpclib.ServerProxy):
    def __init__(self, handler, *args, **kw_args): xmlrpclib.ServerProxy.__init__(self, handler, CertificateCheckingSafeTransport())
