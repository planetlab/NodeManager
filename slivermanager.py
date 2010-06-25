# $Id$
# $URL$

"""Sliver manager.

The sliver manager has several functions.  It is responsible for
creating, resource limiting, starting, stopping, and destroying
slivers.  It provides an API for users to access these functions and
also to make inter-sliver resource loans.  The sliver manager is also
responsible for handling delegation accounts.
"""

import string,re

import logger
import api, api_calls
import database
import accounts
import controller
import sliver_vs

try: from bwlimit import bwmin, bwmax
except ImportError: bwmin, bwmax = 8, 1000*1000*1000

priority=10


DEFAULT_ALLOCATION = {
    'enabled': 1,
    # CPU parameters
    'cpu_pct': 0, # percent CPU reserved
    'cpu_share': 1, # proportional share
    # bandwidth parameters
    'net_min_rate': bwmin / 1000, # kbps
    'net_max_rate': bwmax / 1000, # kbps
    'net_share': 1, # proportional share
    # bandwidth parameters over routes exempt from node bandwidth limits
    'net_i2_min_rate': bwmin / 1000, # kbps
    'net_i2_max_rate': bwmax / 1000, # kbps
    'net_i2_share': 1, # proportional share
    'net_max_kbyte' : 10546875, #Kbyte
    'net_thresh_kbyte': 9492187, #Kbyte
    'net_i2_max_kbyte': 31640625,
    'net_i2_thresh_kbyte': 28476562,
    # disk space limit
    'disk_max': 10000000, # bytes
    # capabilities
    'capabilities': '',
    # IP addresses
    'ip_addresses': '0.0.0.0',

    # NOTE: this table is further populated with resource names and
    # default amounts via the start() function below.  This probably
    # should be changeg and these values should be obtained via the
    # API to myplc.
    }

start_requested = False  # set to True in order to request that all slivers be started

@database.synchronized
def GetSlivers(data, config = None, plc=None, fullupdate=True):
    """This function has two purposes.  One, convert GetSlivers() data
    into a more convenient format.  Two, even if no updates are coming
    in, use the GetSlivers() heartbeat as a cue to scan for expired
    slivers."""

    logger.verbose("slivermanager: Entering GetSlivers with fullupdate=%r"%fullupdate)
    for key in data.keys():
        logger.verbose('slivermanager: GetSlivers key : ' + key)

    node_id = None
    try:
        f = open('/etc/planetlab/node_id')
        try: node_id = int(f.read())
        finally: f.close()
    except: logger.log_exc("slivermanager: GetSlivers failed to read /etc/planetlab/node_id")

    if data.has_key('node_id') and data['node_id'] != node_id: return

    if data.has_key('networks'):
        for network in data['networks']:
            if network['is_primary'] and network['bwlimit'] is not None:
                DEFAULT_ALLOCATION['net_max_rate'] = network['bwlimit'] / 1000

    # Take initscripts (global) returned by API, make dict
    if 'initscripts' not in data:
        logger.log_missing_data("slivermanager.GetSlivers",'initscripts')
        return
    initscripts = {}
    for is_rec in data['initscripts']:
        logger.verbose("slivermanager: initscript: %s" % is_rec['name'])
        initscripts[str(is_rec['name'])] = is_rec['script']

    for sliver in data['slivers']:
        logger.verbose("slivermanager: %s: slivermanager.GetSlivers in slivers loop"%sliver['name'])
        rec = sliver.copy()
        rec.setdefault('timestamp', data['timestamp'])

        # convert attributes field to a proper dict
        attributes = {}
        for attr in rec.pop('attributes'): attributes[attr['tagname']] = attr['value']
        rec.setdefault("attributes", attributes)

        # squash keys
        keys = rec.pop('keys')
        rec.setdefault('keys', '\n'.join([key_struct['key'] for key_struct in keys]))

        ## 'Type' isn't returned by GetSlivers() for whatever reason.  We're overloading
        ## instantiation here, but i suppose its the same thing when you think about it. -FA
        # Handle nm-controller here
        if rec['instantiation'].lower() == 'nm-controller':
            rec.setdefault('type', attributes.get('type', 'controller.Controller'))
        else:
            rec.setdefault('type', attributes.get('type', 'sliver.VServer'))

        # set the vserver reference.  If none, set to default.
        rec.setdefault('vref', attributes.get('vref', 'default'))

        # set initscripts.  first check if exists, if not, leave empty.
        is_name = attributes.get('initscript')
        if is_name is not None and is_name in initscripts:
            rec['initscript'] = initscripts[is_name]
        else:
            rec['initscript'] = ''

        # set delegations, if none, set empty
        rec.setdefault('delegations', attributes.get("delegations", []))

        # extract the implied rspec
        rspec = {}
        rec['rspec'] = rspec
        for resname, default_amount in DEFAULT_ALLOCATION.iteritems():
            try:
                t = type(default_amount)
                amt = t.__new__(t, attributes[resname])
            except (KeyError, ValueError): amt = default_amount
            rspec[resname] = amt

        # add in sysctl attributes into the rspec
        for key in attributes.keys():
            if key.find("sysctl.") == 0:
                rspec[key] = attributes[key]

        database.db.deliver_record(rec)
    if fullupdate: database.db.set_min_timestamp(data['timestamp'])
    # slivers are created here.
    database.db.sync()

def deliver_ticket(data):
    return GetSlivers(data, fullupdate=False)

def start(options, config):
    for resname, default_amount in sliver_vs.DEFAULT_ALLOCATION.iteritems():
        DEFAULT_ALLOCATION[resname]=default_amount

    accounts.register_class(sliver_vs.Sliver_VS)
    accounts.register_class(controller.Controller)
    database.start()
    api_calls.deliver_ticket = deliver_ticket
    api.start()
