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


API_SERVER_PORT = 812
UNIX_ADDR = '/tmp/sliver_mgr.api'

deliver_ticket = None  # set in sm.py:start()

api_method_dict = {}
nargs_dict = {}

def export_to_api(nargs):
    def export(method):
        nargs_dict[method.__name__] = nargs
        api_method_dict[method.__name__] = method
        return method
    return export


@export_to_api(0)
def Help():
    """Help(): get help"""
    return ''.join([method.__doc__ + '\n' for method in api_method_dict.itervalues()])

@export_to_api(1)
def Ticket(tkt):
    """Ticket(tkt): deliver a ticket"""
    try:
        data = ticket.verify(tkt)
        if data != None:
            deliver_ticket(data)
    except Exception, err:
        raise xmlrpclib.Fault(102, 'Ticket error: ' + str(err))

@export_to_api(0)
def GetXIDs():
    """GetXIDs(): return an dictionary mapping slice names to XIDs"""
    return dict([(pwent[0], pwent[2]) for pwent in pwd.getpwall() if pwent[6] == sliver_vs.Sliver_VS.SHELL])

@export_to_api(0)
def GetSSHKeys():
    """GetSSHKeys(): return an dictionary mapping slice names to SSH keys"""
    keydict = {}
    for rec in database.db.itervalues():
        if 'keys' in rec:
            keydict[rec['name']] = rec['keys']
    return keydict

@export_to_api(1)
def Create(rec):
    """Create(sliver_name): create a non-PLC-instantiated sliver"""
    if rec['instantiation'] == 'delegated': accounts.get(rec['name']).ensure_created(rec)

@export_to_api(1)
def Destroy(rec):
    """Destroy(sliver_name): destroy a non-PLC-instantiated sliver"""
    if rec['instantiation'] == 'delegated': accounts.get(rec['name']).ensure_destroyed()

@export_to_api(1)
def Start(rec):
    """Start(sliver_name): run start scripts belonging to the specified sliver"""
    accounts.get(rec['name']).start()

@export_to_api(1)
def Stop(rec):
    """Stop(sliver_name): kill all processes belonging to the specified sliver"""
    accounts.get(rec['name']).stop()

@export_to_api(1)
def GetEffectiveRSpec(rec):
    """GetEffectiveRSpec(sliver_name): return the RSpec allocated to the specified sliver, including loans"""
    return rec.get('_rspec', {}).copy()

@export_to_api(1)
def GetRSpec(rec):
    """GetRSpec(sliver_name): return the RSpec allocated to the specified sliver, excluding loans"""
    return rec.get('rspec', {}).copy()

@export_to_api(1)
def GetLoans(rec):
    """GetLoans(sliver_name): return the list of loans made by the specified sliver"""
    return rec.get('_loans', [])[:]

def validate_loans(obj):
    """Check that <obj> is a valid loan specification."""
    def validate_loan(obj): return (type(obj)==list or type(obj)==tuple) and len(obj)==3 and type(obj[0])==str and type(obj[1])==str and obj[1] in database.LOANABLE_RESOURCES and type(obj[2])==int and obj[2]>=0
    return type(obj)==list and False not in map(validate_loan, obj)

@export_to_api(2)
def SetLoans(rec, loans):
    """SetLoans(sliver_name, loans): overwrite the list of loans made by the specified sliver"""
    if not validate_loans(loans): raise xmlrpclib.Fault(102, 'Invalid argument: the second argument must be a well-formed loan specification')
    rec['_loans'] = loans
    database.db.sync()


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
            raise xmlrpclib.Fault(100, 'Invalid API method %s.  Valid choices are %s' % (method_name, ', '.join(api_method_list)))
        expected_nargs = nargs_dict[method_name]
        if len(args) != expected_nargs: raise xmlrpclib.Fault(101, 'Invalid argument count: got %d, expecting %d.' % (len(args), expected_nargs))
        else:
            # Figure out who's calling.
            # XXX - these ought to be imported directly from some .h file
            SO_PEERCRED = 17
            sizeof_struct_ucred = 12
            ucred = self.request.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, sizeof_struct_ucred)
            xid = struct.unpack('3i', ucred)[2]
            caller_name = pwd.getpwuid(xid)[0]
            if method_name not in ('Help', 'Ticket', 'GetXIDs', 'GetSSHKeys'):
                target_name = args[0]
                target_rec = database.db.get(target_name)
                if not (target_rec and target_rec['type'].startswith('sliver.')): raise xmlrpclib.Fault(102, 'Invalid argument: the first argument must be a sliver name.')
                if not (caller_name in (args[0], 'root') or (caller_name, method_name) in target_rec['delegations'] or (caller_name == 'utah_elab_delegate' and target_name.startswith('utah_elab_'))): raise xmlrpclib.Fault(108, 'Permission denied.')
                result = method(target_rec, *args[1:])
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
