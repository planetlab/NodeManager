"""Parse slices.xml.  This file will become obsolete when the new API comes online."""

import base64
import sys
sys.path.append('/usr/local/planetlab/bin')
import SslFetch
import time
import xml.parsers.expat

from config import *
import database
import logger


_worker = SslFetch.Worker(SA_HOSTNAME, cacert_file='/usr/boot/cacert.pem')

def fetch(filename):
    logger.log('fetching %s' % filename)
    (rc, data) = _worker.fetch(filename)
    if rc == 0:
        logger.log('fetch succeeded')
        return data
    else:
        # XXX - should get a better error message from SslFetch/libcurl
        curl_doc = 'http://curl.haxx.se/libcurl/c/libcurl-errors.html'
        raise 'fetch failed, rc=%d (see %s)' % (rc, curl_doc)


delegate_key = 'ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAIEAzNQIrVC9ZV9iDgu5/WXxcH/SyGdLG45CWXoWWh37UNA4dCVVlxtQ96xF7poolnxnM1irKUiXx85FsjA37z6m7IWl1h9uMYEJEvYkkxApsCmwm8C02m/BsOWK4Zjh4sv7QTeDgDnqhwnBw/U4jnkt8yKfVTBTNUY01dESzOgBfBc= root@yankee.cs.princeton.edu'

def fetch_and_update():
    sx = slices_xml(fetch('/xml/slices-0.5.xml'))
    # sx = slices_xml(open('/root/slices-0.5.xml').read())
    recs = [{'record_key': 'timestamp', 'type': 'timestamp', 'timestamp': time.time()}]
    recs.append({'record_key': 'delegate_del_snoop', 'timestamp': time.time(), 'account_type': 'delegate', 'name': 'del_snoop', 'ssh_keys': delegate_key, 'plc_instantiated': True})
    recs.append({'record_key': 'bwcap', 'timestamp': time.time(), 'cap': 5000000000, 'exempt_ips': ['127.0.0.1']})
    for id, name in sx.id_name.iteritems():
        rec = {}
        rec['record_key'] = 'sliver_' + name
        rec['account_type'] = 'sliver'
        rec['name'] = name
        rec['expiry'] = sx.id_expiry[id]
        rec['timestamp'] = sx.id_ts.get(id) or time.time()
        rec['delegations'] = [('del_snoop', 'GetRSpec')]
        rec['id'] = id
        rec['rspec'] = sx.get_rspec(id)
        ssh_keys = []
        for uid in sx.id_uids[id]: ssh_keys.extend(sx.uid_keys[uid])
        rec['ssh_keys'] = '\n'.join(ssh_keys)
        rec['plc_instantiated'] = True
        rec['initscript'] = base64.b64encode('#!/bin/sh\n/bin/echo hello >/world.txt')
        recs.append(rec)
    database.deliver_records(recs)


node_id = None

def get_node_id():
    global node_id
    if node_id == None:
        filename = '/etc/planetlab/node_id'
        logger.log('reading node id from %s' % filename)
        id_file = open(filename)
        node_id = int(id_file.readline())
        id_file.close()
    return node_id


class slices_xml:
    def __init__(self, data):
        self.node_id = get_node_id()
        self.id_name = {}
        self.id_expiry = {}
        self.id_uids = {}
        self.uid_keys = {}
        self.id_rspec = {}
        self.id_ts = {}
        parser = xml.parsers.expat.ParserCreate()
        parser.StartElementHandler = self._start_element
        parser.CharacterDataHandler = self._char_data
        isfinal = True
        parser.Parse(data, isfinal)

    def get_rspec(self, id):
        rspec = DEFAULT_RSPEC.copy()
        rspec.update(self.id_rspec[id])
        return rspec

    def _start_element(self, name, attrs):
        self.last_tag = name
        if   name == u'slice':
            self.id = int(attrs[u'id'])
            self.name = str(attrs[u'name'])
            self.expiry = int(attrs[u'expiry'])
        elif name == u'timestamp':
            self.id_ts[self.id] = int(attrs[u'value'])
        elif name == u'node':
            # remember slices with slivers on us
            nid = int(attrs[u'id'])
            if nid == self.node_id:
                self.id_name[self.id] = self.name
                self.id_expiry[self.id] = self.expiry
                self.id_uids[self.id] = []
                self.id_rspec[self.id] = {}
        elif name == u'user':
            # remember users with slices with slivers on us
            if self.id in self.id_name:
                uid = int(attrs[u'person_id'])
                self.id_uids[self.id].append(uid)
                self.uid_keys[uid] = []
        elif name == u'resource':
            self.rname = str(attrs[u'name'])
        elif name == u'key':
            # remember keys of users with slices with slivers on us
            uid = int(attrs[u'person_id'])
            if uid in self.uid_keys:
                self.uid_keys[uid].append(str(attrs[u'value']))

    def _char_data(self, data):
        if self.last_tag == u'value' and self.id in self.id_name:
            try: self.id_rspec[self.id][self.rname] = int(data)
            except ValueError: pass
        self.last_tag = u''
