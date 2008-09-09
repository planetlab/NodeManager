"""Sliver manager API.

This module exposes an XMLRPC interface that allows PlanetLab users to
create/destroy slivers with delegated instantiation, start and stop
slivers, make resource loans, and examine resource allocations.  The
XMLRPC is provided on a localhost-only TCP port as well as via a Unix
domain socket that is accessible by ssh-ing into a delegate account
with the forward_api_calls shell.
"""

import SimpleXMLRPCServer
import SocketServer
import errno
import os
import pwd
import socket
import struct
import threading
import xmlrpclib

import accounts
import database
import logger
import sliver_vs
import ticket
import tools
from api_calls import *

API_SERVER_PORT = 812
UNIX_ADDR = '/tmp/sliver_mgr.api'

class APIRequestHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
    # overriding _dispatch to achieve this effect is officially deprecated,
    # but I can't figure out how to get access to .request without
    # duplicating SimpleXMLRPCServer code here, which is more likely to
    # change than the deprecated behavior is to be broken

    @database.synchronized
    def _dispatch(self, method_name_unicode, args):
        method_name = str(method_name_unicode)
        try: method = api_method_dict[method_name]
        except KeyError:
            api_method_list = api_method_dict.keys()
            api_method_list.sort()
            raise xmlrpclib.Fault(100, 'Invalid API method %s.  Valid choices are %s' % \
                (method_name, ', '.join(api_method_list)))
        expected_nargs = nargs_dict[method_name]
        if len(args) != expected_nargs: 
            raise xmlrpclib.Fault(101, 'Invalid argument count: got %d, expecting %d.' % \
                (len(args), expected_nargs))
        else:
            # Figure out who's calling.
            # XXX - these ought to be imported directly from some .h file
            SO_PEERCRED = 17
            sizeof_struct_ucred = 12
            ucred = self.request.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, sizeof_struct_ucred)
            xid = struct.unpack('3i', ucred)[2]
            caller_name = pwd.getpwuid(xid)[0]
            if method_name not in ('ReCreate', 'Help', 'Ticket', 'GetXIDs', 'GetSSHKeys'):
                target_name = args[0]
                target_rec = database.db.get(target_name)
                if not (target_rec and target_rec['type'].startswith('sliver.')): 
                    raise xmlrpclib.Fault(102, \
                        'Invalid argument: the first argument must be a sliver name.')
                if not caller_name in (target_name, target_rec['delegations']):
                    raise xmlrpclib.Fault(108, '%s: Permission denied.' % caller_name)
                try: result = method(target_rec, *args[1:])
                except Exception, err: raise xmlrpclib.Fault(104, 'Error in call: %s' %err)
            else: result = method(*args)
            if result == None: result = 1
            return result

class APIServer_INET(SocketServer.ThreadingMixIn, SimpleXMLRPCServer.SimpleXMLRPCServer): allow_reuse_address = True

class APIServer_UNIX(APIServer_INET): address_family = socket.AF_UNIX

def start():
    """Start two XMLRPC interfaces: one bound to localhost, the other bound to a Unix domain socket."""
    serv1 = APIServer_INET(('127.0.0.1', API_SERVER_PORT), requestHandler=APIRequestHandler, logRequests=0)
    tools.as_daemon_thread(serv1.serve_forever)
    try: os.unlink(UNIX_ADDR)
    except OSError, e:
        if e.errno != errno.ENOENT: raise
    serv2 = APIServer_UNIX(UNIX_ADDR, requestHandler=APIRequestHandler, logRequests=0)
    tools.as_daemon_thread(serv2.serve_forever)
    os.chmod(UNIX_ADDR, 0666)
