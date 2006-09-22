import SocketServer
import os
import subprocess

from config import KEY_FILE, TICKET_SERVER_PORT
import tools


class TicketServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True


class TicketRequestHandler(SocketServer.StreamRequestHandler):
    def handle(self):
        data = self.rfile.read()
        filename = tools.write_temp_file(lambda thefile:
                                         thefile.write(TEMPLATE % data))
        result = subprocess.Popen([XMLSEC1, '--sign',
                                   '--privkey-pem', KEY_FILE, filename],
                                  stdout=subprocess.PIPE).stdout
        self.wfile.write(result.read())
        result.close()
#         os.unlink(filename)


def start():
    tools.as_daemon_thread(TicketServer(('', TICKET_SERVER_PORT),
                                        TicketRequestHandler).serve_forever)


XMLSEC1 = '/usr/bin/xmlsec1'

TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<Envelope xmlns="urn:envelope">
  <Data>%s</Data>
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <SignedInfo>
      <CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315" />
      <SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1" />
      <Reference URI="">
        <Transforms>
          <Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature" />
        </Transforms>
        <DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1" />
        <DigestValue></DigestValue>
      </Reference>
    </SignedInfo>
    <SignatureValue/>
    <KeyInfo>
	<KeyName/>
    </KeyInfo>
  </Signature>
</Envelope>
'''

