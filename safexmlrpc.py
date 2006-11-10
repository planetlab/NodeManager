"""Leverage curl to make XMLRPC requests that check the server's credentials."""

import curlwrapper
import xmlrpclib


CURL = '/usr/bin/curl'

class CertificateCheckingSafeTransport(xmlrpclib.Transport):
    def request(self, host, handler, request_body, verbose=0):
        self.verbose = verbose
        try:
            contents = curlwrapper.retrieve('https://%s%s' % (host, handler), request_body)
            return xmlrpclib.loads(contents)[0]
        except curlwrapper.CurlException, e: raise xmlrpclib.ProtocolError(host + handler, -1, str(e), '')

class ServerProxy(xmlrpclib.ServerProxy):
    def __init__(self, handler, *args, **kw_args): xmlrpclib.ServerProxy.__init__(self, handler, CertificateCheckingSafeTransport())
