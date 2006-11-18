"""Leverage curl to make XMLRPC requests that check the server's credentials."""

import curlwrapper
import xmlrpclib


class CertificateCheckingSafeTransport(xmlrpclib.Transport):
    def __init__(self, cacert, timeout):
        self.cacert = cacert
        self.timeout = timeout

    def request(self, host, handler, request_body, verbose=0):
        self.verbose = verbose
        try:
            contents = curlwrapper.retrieve('https://%s%s' % (host, handler),
                                            cacert = self.cacert,
                                            postdata = request_body,
                                            timeout = self.timeout)
            return xmlrpclib.loads(contents)[0]
        except curlwrapper.CurlException, e:
            raise xmlrpclib.ProtocolError(host + handler, -1, str(e), '')

class ServerProxy(xmlrpclib.ServerProxy):
    def __init__(self, uri, cacert, timeout = 300, **kwds):
        xmlrpclib.ServerProxy.__init__(self, uri,
                                       CertificateCheckingSafeTransport(cacert, timeout),
                                       **kwds)
