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

try:
	from PLC.Parameter import Parameter, Mixed
except:
    def Parameter(a = None, b = None): pass
    def Mixed(a = None, b = None, c = None): pass


import accounts
import logger

# TODO: These try/excepts are a hack to allow doc/DocBookLocal.py to 
# import this file in order to extrac the documentation from each 
# exported function.  A better approach will involve more extensive code
# splitting, I think.
try: import database
except: import logger as database
try: import sliver_vs
except: import logger as sliver_vs
import ticket as ticket_module
import tools


api_method_dict = {}
nargs_dict = {}

def export_to_api(nargs):
    def export(method):
        nargs_dict[method.__name__] = nargs
        api_method_dict[method.__name__] = method
        return method
    return export

def export_to_docbook(**kwargs):

    keywords = {
        "group" : "NMAPI",
        "status" : "current",
        "name": None,
        "args": None,
        "roles": [],
        "accepts": [],
        "returns": [],
    }
    def export(method):
        def args():
            # Inspect method. Remove self from the argument list.
            max_args = method.func_code.co_varnames[0:method.func_code.co_argcount]
            defaults = method.func_defaults
            if defaults is None:
                defaults = ()
            min_args = max_args[0:len(max_args) - len(defaults)]

            defaults = tuple([None for arg in min_args]) + defaults
            return (min_args, max_args, defaults)

        keywords['name'] = method.__name__
        keywords['args'] = args
        for arg in keywords:
            method.__setattr__(arg, keywords[arg])

        for arg in kwargs:
            method.__setattr__(arg, kwargs[arg])
        return method

    return export


# status
# roles,
# accepts,
# returns

@export_to_docbook(roles=['self'], 
				   accepts=[], 
				   returns=Parameter([], 'A list of supported functions'))
@export_to_api(0)
def Help():
    """Get a list of functions currently supported by the Node Manager API"""
    return ''.join([method.__doc__ + '\n' for method in api_method_dict.itervalues()])

@export_to_docbook(roles=['self'], 
				   accepts=[Parameter(str, 'A ticket returned from GetSliceTicket()')], 
				   returns=Parameter(int, '1 if successful'))
@export_to_api(1)
def Ticket(ticket):
    """The Node Manager periodically polls the PLC API for a list of all
    slices that are allowed to exist on the given node. Before 
    actions are performed on a delegated slice (such as creation),
    a controller slice must deliver a valid slice ticket to NM. 
    
    This ticket is the value retured by PLC's GetSliceTicket() API call,
    """
    try:
        data = ticket_module.verify(ticket)
        name = data['slivers'][0]['name']
        if data != None:
            deliver_ticket(data)
        logger.log('Ticket delivered for %s' % name)
        Create(database.db.get(name))
    except Exception, err:
        raise xmlrpclib.Fault(102, 'Ticket error: ' + str(err))

@export_to_docbook(roles=['self'],
				   accepts=[], 
				   returns={'sliver_name' : Parameter(int, 'the associated xid')})
@export_to_api(0)
def GetXIDs():
    """Return an dictionary mapping Slice names to XIDs"""
    return dict([(pwent[0], pwent[2]) for pwent in pwd.getpwall() if pwent[6] == sliver_vs.Sliver_VS.SHELL])

@export_to_docbook(roles=['self'],
                   accepts=[], 
 				   returns={ 'sliver_name' : Parameter(str, 'the associated SSHKey')})
@export_to_api(0)
def GetSSHKeys():
    """Return an dictionary mapping slice names to SSH keys"""
    keydict = {}
    for rec in database.db.itervalues():
        if 'keys' in rec:
            keydict[rec['name']] = rec['keys']
    return keydict

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
				   returns=Parameter(int, '1 if successful'))
@export_to_api(1)
def Create(sliver_name):
    """Create a non-PLC-instantiated sliver"""
    rec = sliver_name
    if rec['instantiation'] == 'delegated': accounts.get(rec['name']).ensure_created(rec)

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
				   returns=Parameter(int, '1 if successful'))
@export_to_api(1)
def Destroy(sliver_name):
    """Destroy a non-PLC-instantiated sliver"""
    rec = sliver_name 
    if rec['instantiation'] == 'delegated': accounts.get(rec['name']).ensure_destroyed()

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
				   returns=Parameter(int, '1 if successful'))
@export_to_api(1)
def Start(sliver_name):
    """Run start scripts belonging to the specified sliver"""
    rec = sliver_name
    accounts.get(rec['name']).start()

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
				   returns=Parameter(int, '1 if successful'))
@export_to_api(1)
def Stop(sliver_name):
    """Kill all processes belonging to the specified sliver"""
    rec = sliver_name
    accounts.get(rec['name']).stop()

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
				   returns=Parameter(int, '1 if successful'))

@export_to_api(1)
def ReCreate(sliver_name):
	"""Stop, Destroy, Create, Start sliver in order to reinstall it."""
	Stop(sliver_name)
	Destroy(sliver_name)
	Create(sliver_name)
	Start(sliver_name)

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
				   returns=Parameter(dict, "A resource specification"))
@export_to_api(1)
def GetEffectiveRSpec(sliver_name):
    """Return the RSpec allocated to the specified sliver, including loans"""
    rec = sliver_name
    return rec.get('_rspec', {}).copy()

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
				    returns={
							"resource name" : Parameter(int, "amount")
						}
				  )
@export_to_api(1)
def GetRSpec(sliver_name):
    """Return the RSpec allocated to the specified sliver, excluding loans"""
    rec = sliver_name
    return rec.get('rspec', {}).copy()

@export_to_docbook(roles=['nm-controller', 'self'], 
					accepts=[Parameter(str, 'A sliver/slice name.')], 
					returns=[Mixed(Parameter(str, 'recipient slice name'),
						     Parameter(str, 'resource name'),
						     Parameter(int, 'resource amount'))] 
				  )
@export_to_api(1)
def GetLoans(sliver_name):
    """Return the list of loans made by the specified sliver"""
    rec = sliver_name
    return rec.get('_loans', [])[:]

def validate_loans(obj):
    """Check that <obj> is a valid loan specification."""
    def validate_loan(obj): return (type(obj)==list or type(obj)==tuple) and len(obj)==3 and type(obj[0])==str and type(obj[1])==str and obj[1] in database.LOANABLE_RESOURCES and type(obj[2])==int and obj[2]>=0
    return type(obj)==list and False not in map(validate_loan, obj)

@export_to_docbook(roles=['nm-controller', 'self'], 
				accepts=[ Parameter(str, 'A sliver/slice name.'),
						  [Mixed(Parameter(str, 'recipient slice name'),
						   Parameter(str, 'resource name'),
						   Parameter(int, 'resource amount'))] ],
				returns=Parameter(int, '1 if successful'))
@export_to_api(2)
def SetLoans(sliver_name, loans):
    """Overwrite the list of loans made by the specified sliver.

	Also, note that SetLoans will not throw an error if more capacity than the
	RSpec is handed out, but it will silently discard those loans that would
	put it over capacity.  This behavior may be replaced with error semantics
	in the future.  As well, there is currently no asynchronous notification
	of loss of resources.
	"""
    rec = sliver_name
    if not validate_loans(loans): raise xmlrpclib.Fault(102, 'Invalid argument: the second argument must be a well-formed loan specification')
    rec['_loans'] = loans
    database.db.sync()
