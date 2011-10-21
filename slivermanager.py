#
"""Sliver manager.

The sliver manager has several functions.  It is responsible for
creating, resource limiting, starting, stopping, and destroying
slivers.  It provides an API for users to access these functions and
also to make inter-sliver resource loans.  The sliver manager is also
responsible for handling delegation accounts.
"""

import string,re
import time

import logger
import api, api_calls
import database
import accounts
import controller
import sliver_vs
import sliver_lxc

try: from bwlimit import bwmin, bwmax
except ImportError: bwmin, bwmax = 8, 1000*1000*1000

priority=10


DEFAULT_ALLOCATION = {
    'enabled': 1,
    # CPU parameters
    'cpu_pct': 0, # percent CPU reserved
    'cpu_share': 1, # proportional share
    'cpu_cores': "0b", # reserved cpu cores <num_cores>[b]
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

# check leases and adjust the 'reservation_alive' field in slivers
# this is not expected to be saved as it will change for the next round
def adjustReservedSlivers (data):
    """
    On reservable nodes, tweak the 'reservation_alive' field to instruct cyclic loop
    about what to do with slivers.
    """
    # only impacts reservable nodes
    if 'reservation_policy' not in data: return
    policy=data['reservation_policy'] 
    if policy not in ['lease_or_idle', 'lease_or_shared']:
        logger.log ("unexpected reservation_policy %(policy)s"%locals())
        return

    logger.log("slivermanager.adjustReservedSlivers")
    now=int(time.time())
    # scan leases that are expected to show in ascending order
    active_lease=None
    for lease in data['leases']:
        if lease['t_from'] <= now and now <= lease['t_until']:
            active_lease=lease
            break

    def is_system_sliver (sliver):
        for d in sliver['attributes']:
            if d['tagname']=='system' and d['value']:
                return True
        return False

    # mark slivers as appropriate
    for sliver in data['slivers']:
        # system slivers must be kept alive
        if is_system_sliver(sliver):
            sliver['reservation_alive']=True
            continue
        
        # regular slivers
        if not active_lease:
            # with 'idle_or_shared', just let the field out, behave like a shared node
            # otherwise, mark all slivers as being turned down
            if policy == 'lease_or_idle':
                sliver['reservation_alive']=False
        else:
            # there is an active lease, mark it alive and the other not
            sliver['reservation_alive'] = sliver['name']==active_lease['name']

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

    # Take initscripts (global) returned by API, build a hash scriptname->code
    iscripts_hash = {}
    if 'initscripts' not in data:
        logger.log_missing_data("slivermanager.GetSlivers",'initscripts')
        return
    for initscript_rec in data['initscripts']:
        logger.verbose("slivermanager: initscript: %s" % initscript_rec['name'])
        iscripts_hash[str(initscript_rec['name'])] = initscript_rec['script']

    adjustReservedSlivers (data)
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

        ### set initscripts; set empty rec['initscript'] if not
        # if tag 'initscript_code' is set, that's what we use
        iscode = attributes.get('initscript_code','')
        if iscode:
            rec['initscript']=iscode
        else:
            isname = attributes.get('initscript')
            if isname is not None and isname in iscripts_hash:
                rec['initscript'] = iscripts_hash[isname]
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
                amount = t.__new__(t, attributes[resname])
            except (KeyError, ValueError): amount = default_amount
            rspec[resname] = amount

        # add in sysctl attributes into the rspec
        for key in attributes.keys():
            if key.find("sysctl.") == 0:
                rspec[key] = attributes[key]

        # also export tags in rspec so they make it to the sliver_vs.start call
        rspec['tags']=attributes

        database.db.deliver_record(rec)
    if fullupdate: database.db.set_min_timestamp(data['timestamp'])
    # slivers are created here.
    database.db.sync()

def deliver_ticket(data):
    return GetSlivers(data, fullupdate=False)

def start():
    for resname, default_amount in sliver_vs.DEFAULT_ALLOCATION.iteritems():
        DEFAULT_ALLOCATION[resname]=default_amount

    accounts.register_class(sliver_vs.Sliver_VS)
    accounts.register_class(sliver_lxc.Sliver_LXC)
    accounts.register_class(controller.Controller)
    database.start()
    api_calls.deliver_ticket = deliver_ticket
    api.start()
