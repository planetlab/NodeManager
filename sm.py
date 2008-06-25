"""Sliver manager.

The sliver manager has several functions.  It is responsible for
creating, resource limiting, starting, stopping, and destroying
slivers.  It provides an API for users to access these functions and
also to make inter-sliver resource loans.  The sliver manager is also
responsible for handling delegation accounts.
"""

# $Id$

try: from bwlimit import bwmin, bwmax
except ImportError: bwmin, bwmax = 8, 1000*1000*1000
import accounts
import api
import api_calls
import database
import delegate
import logger
import sliver_vs
import string,re


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
    'net_max_kbyte' : 5662310, #Kbyte
    'net_thresh_kbyte': 4529848, #Kbyte
    'net_i2_max_kbyte': 17196646,
    'net_i2_thresh_kbyte': 13757316,
    # disk space limit
    'disk_max': 5000000, # bytes
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
def GetSlivers(data, fullupdate=True):
    """This function has two purposes.  One, convert GetSlivers() data
    into a more convenient format.  Two, even if no updates are coming
    in, use the GetSlivers() heartbeat as a cue to scan for expired
    slivers."""

    logger.verbose("Entering sm:GetSlivers with fullupdate=%r"%fullupdate)
    for key in data.keys():
        logger.verbose('GetSlivers key : ' + key)

    node_id = None
    try:
        f = open('/etc/planetlab/node_id')
        try: node_id = int(f.read())
        finally: f.close()
    except: logger.log_exc()

    if data.has_key('node_id') and data['node_id'] != node_id: return

    if data.has_key('networks'):
        for network in data['networks']:
            if network['is_primary'] and network['bwlimit'] is not None:
                DEFAULT_ALLOCATION['net_max_rate'] = network['bwlimit'] / 1000

    # Take intscripts (global) returned by API, make dict
    initscripts = {}
    for is_rec in data['initscripts']:
        logger.verbose("initscript: %s" % is_rec['name'])
        initscripts[str(is_rec['name'])] = is_rec['script']

    for sliver in data['slivers']:
        logger.verbose("sm:GetSlivers in slivers loop")
        rec = sliver.copy()
        rec.setdefault('timestamp', data['timestamp'])

        # convert attributes field to a proper dict
        attr_dict = {}
        for attr in rec.pop('attributes'): attr_dict[attr['name']] = attr['value']

        # squash keys
        keys = rec.pop('keys')
        rec.setdefault('keys', '\n'.join([key_struct['key'] for key_struct in keys]))

        # Handle nm controller here
        rec.setdefault('type', attr_dict.get('type', 'sliver.VServer'))
        if rec['instantiation'] == 'nm-controller':
        # type isn't returned by GetSlivers() for whatever reason.  We're overloading
        # instantiation here, but i suppose its the ssame thing when you think about it. -FA
            rec['type'] = 'delegate'

        # set the vserver reference.  If none, set to default.
        rec.setdefault('vref', attr_dict.get('vref', 'default'))

        # set initscripts.  first check if exists, if not, leave empty.
        is_name = attr_dict.get('initscript')
        if is_name is not None and is_name in initscripts:
            rec['initscript'] = initscripts[is_name]
        else:
            rec['initscript'] = ''

        # set delegations, if none, set empty
        rec.setdefault('delegations', attr_dict.get("delegations", []))

        # extract the implied rspec
        rspec = {}
        rec['rspec'] = rspec
        for resname, default_amt in DEFAULT_ALLOCATION.iteritems():
            try:
                t = type(default_amt)
                amt = t.__new__(t, attr_dict[resname])
            except (KeyError, ValueError): amt = default_amt
            rspec[resname] = amt

        database.db.deliver_record(rec)
    if fullupdate: database.db.set_min_timestamp(data['timestamp'])
    database.db.sync()
    accounts.Startingup = False

def deliver_ticket(data): return GetSlivers(data, fullupdate=False)


def start(options, config):
    for resname, default_amt in sliver_vs.DEFAULT_ALLOCATION.iteritems():
        DEFAULT_ALLOCATION[resname]=default_amt
        
    accounts.register_class(sliver_vs.Sliver_VS)
    accounts.register_class(delegate.Delegate)
    accounts.Startingup = options.startup
    database.start()
    api_calls.deliver_ticket = deliver_ticket
    api.start()
