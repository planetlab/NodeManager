import SimpleXMLRPCServer
import SocketServer
import cPickle
import errno
import os
import pwd
import socket
import struct
import threading
import xmlrpclib

from config import *
import accounts
import database
import logger
import tools


api_method_dict = {}
nargs_dict = {}

def export_to_api(nargs):
    def export(method):
        nargs_dict[method.__name__] = nargs
        api_method_dict[method.__name__] = method
        return method
    return export

@export_to_api(0)
def DumpDatabase():
    """DumpDatabase(): return the entire node manager DB, pickled"""
    return cPickle.dumps(dict(database._db), 0)

@export_to_api(0)
def Help():
    """Help(): get help"""
    return ''.join([method.__doc__ + '\n' for method in api_method_dict.itervalues()])

@export_to_api(1)
def CreateSliver(rec):
    """CreateSliver(sliver_name): set up a non-PLC-instantiated sliver"""
    if not rec['plc_instantiated']:
        accounts.get(rec['name']).ensure_created(rec)

@export_to_api(1)
def DeleteSliver(rec):
    """DeleteSliver(sliver_name): tear down a non-PLC-instantiated sliver"""
    if not rec['plc_instantiated']:
        accounts.get(rec['name']).ensure_destroyed()

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
    return tools.deepcopy(rec.get('eff_rspec', {}))

@export_to_api(1)
def GetRSpec(rec):
    """GetRSpec(sliver_name): return the RSpec allocated to the specified sliver, excluding loans"""
    return tools.deepcopy(rec.get('rspec', {}))

@export_to_api(1)
def GetLoans(rec):
    """GetLoans(sliver_name): return the list of loans made by the specified sliver"""
    return tools.deepcopy(rec.get('loans', []))

def validate_loans(obj):
    """Check that <obj> is a valid loan specification."""
    def validate_loan(obj):
        return (type(obj)==list or type(obj)==tuple) and len(obj)==3 and \
               type(obj[0])==str and \
               type(obj[1])==str and obj[1] in LOANABLE_RESOURCES and \
               type(obj[2])==int and obj[2]>0
    return type(obj)==list and False not in map(validate_loan, obj)

@export_to_api(2)
def SetLoans(rec, loans):
    """SetLoans(sliver_name, loans): overwrite the list of loans made by the specified sliver"""
    if not validate_loans(loans):
        raise xmlrpclib.Fault(102, 'Invalid argument: the second argument must be a well-formed loan specification')
    rec['loans'] = loans
    database.deliver_records([rec])

api_method_list = api_method_dict.keys()
api_method_list.sort()


class APIRequestHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
    # overriding _dispatch to achieve this effect is officially deprecated,
    # but I can't figure out how to get access to .request
    # without duplicating SimpleXMLRPCServer code here,
    # which is more likely to change than the deprecated behavior
    # is to be broken

    @database.synchronized
    def _dispatch(self, method_name, args):
        method_name = str(method_name)
        try: method = api_method_dict[method_name]
        except KeyError:
            raise xmlrpclib.Fault(100, 'Invalid API method %s.  Valid choices are %s' % (method_name, ', '.join(api_method_list)))

        expected_nargs = nargs_dict[method_name]
        if len(args) != nargs_dict[method_name]:
            raise xmlrpclib.Fault(101, 'Invalid argument count: got %d, expecting %d.' % (len(args), expected_nargs))
        else:
            # Figure out who's calling.
            # XXX - these ought to be imported directly from some .h file
            SO_PEERCRED = 17
            sizeof_struct_ucred = 12
            ucred = self.request.getsockopt(socket.SOL_SOCKET, SO_PEERCRED,
                                            sizeof_struct_ucred)
            xid = struct.unpack('3i', ucred)[2]
            caller_name = pwd.getpwuid(xid)[0]

            if expected_nargs >= 1:
                target_name = args[0]
                target_rec = database.get_sliver(target_name)
                if not target_rec: raise xmlrpclib.Fault(102, 'Invalid argument: the first argument must be a sliver name.')

                if caller_name not in (args[0], 'root') and \
                       (caller_name, method_name) not in target_rec['delegations']:
                    raise xmlrpclib.Fault(108, 'Permission denied.')
                result = method(target_rec, *args[1:])
            else:
                if method_name == 'DumpDatabase' and caller_name != 'root':
                    raise xmlrpclib.Fault(108, 'Permission denied.')
                result = method()
            if result == None: result = 1
            return result

class APIServer_INET(SocketServer.ThreadingMixIn,
                     SimpleXMLRPCServer.SimpleXMLRPCServer):
    allow_reuse_address = True

class APIServer_UNIX(APIServer_INET): address_family = socket.AF_UNIX

def start():
    """Start two XMLRPC interfaces: one bound to localhost, the other bound to a Unix domain socket."""
    serv1 = APIServer_INET(('127.0.0.1', API_SERVER_PORT),
                           requestHandler=APIRequestHandler, logRequests=0)
    tools.as_daemon_thread(serv1.serve_forever)
    unix_addr = '/tmp/node_mgr_api'
    try: os.unlink(unix_addr)
    except OSError, e:
        if e.errno != errno.ENOENT: raise
    serv2 = APIServer_UNIX(unix_addr,
                           requestHandler=APIRequestHandler, logRequests=0)
    tools.as_daemon_thread(serv2.serve_forever)
    os.chmod(unix_addr, 0666)
