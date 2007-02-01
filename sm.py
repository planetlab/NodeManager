"""Sliver manager.

The sliver manager has several functions.  It is responsible for
creating, resource limiting, starting, stopping, and destroying
slivers.  It provides an API for users to access these functions and
also to make inter-sliver resource loans.  The sliver manager is also
responsible for handling delegation accounts.
"""

try: from bwlimit import bwmin, bwmax
except ImportError: bwmin, bwmax = 8, 1000*1000*1000
import accounts
import api
import database
import delegate
import logger
import sliver_vs


DEFAULT_ALLOCATION = {
    'enabled': 1,
    # CPU parameters
    'cpu_min': 0, # ms/s
    'cpu_share': 32, # proportional share
    # bandwidth parameters
    'net_min': bwmin, # bps
    'net_max': bwmax, # bps
    'net_share': 1, # proportional share
    # bandwidth parameters over routes exempt from node bandwidth limits
    'net2_min': bwmin, # bps
    'net2_max': bwmax, # bps
    'net2_share': 1, # proportional share
    'disk_max': 5000000 # bytes
    }

start_requested = False  # set to True in order to request that all slivers be started


@database.synchronized
def GetSlivers(data, fullupdate=True):
    """This function has two purposes.  One, convert GetSlivers() data
    into a more convenient format.  Two, even if no updates are coming
    in, use the GetSlivers() heartbeat as a cue to scan for expired
    slivers."""

    node_id = None
    try:
        f = open('/etc/planetlab/node_id')
        try: node_id = int(f.read())
        finally: f.close()
    except: logger.log_exc()

    if data.has_key('node_id') and data['node_id'] != node_id: return
    for sliver in data['slivers']:
        rec = sliver.copy()
        rec.setdefault('timestamp', data['timestamp'])

        # convert attributes field to a proper dict
        attr_dict = {}
        for attr in rec.pop('attributes'): attr_dict[attr['name']] = attr['value']

        # squash keys
        keys = rec.pop('keys')
        rec.setdefault('keys', '\n'.join([key_struct['key'] for key_struct in keys]))

        rec.setdefault('type', attr_dict.get('type', 'sliver.VServer'))
        rec.setdefault('vref', attr_dict.get('vref', 'default'))
        rec.setdefault('initscript', attr_dict.get('initscript', ''))
        rec.setdefault('delegations', [])  # XXX - delegation not yet supported

        # extract the implied rspec
        rspec = {}
        rec['rspec'] = rspec
        for resname, default_amt in DEFAULT_ALLOCATION.iteritems():
            try: amt = int(attr_dict[resname])
            except (KeyError, ValueError): amt = default_amt
            rspec[resname] = amt
        database.db.deliver_record(rec)
    if fullupdate: database.db.set_min_timestamp(data['timestamp'])
    database.db.sync()

    # handle requested startup
    global start_requested
    if start_requested:
        start_requested = False
        cumulative_delay = 0
        for name in database.db.iterkeys():
            accounts.get(name).start(delay=cumulative_delay)
            cumulative_delay += 3

def deliver_ticket(data): return GetSlivers(data, fullupdate=False)


def start(options, config):
    accounts.register_class(sliver_vs.Sliver_VS)
    accounts.register_class(delegate.Delegate)
    global start_requested
    start_requested = options.startup
    database.start()
    api.deliver_ticket = deliver_ticket
    api.start()
