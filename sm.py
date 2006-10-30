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
import sliver_vs


DEFAULT_ALLOCATION = {'enabled': 1, 'cpu_min': 0, 'cpu_share': 32, 'net_min': bwmin, 'net_max': bwmax, 'net2_min': bwmin, 'net2_max': bwmax, 'net_share': 1, 'disk_max': 5000000}

start_requested = False  # set to True in order to request that all slivers be started


@database.synchronized
def GetSlivers_callback(data):
    """This function has two purposes.  One, convert GetSlivers() data into a more convenient format.  Two, even if no updates are coming in, use the GetSlivers() heartbeat as a cue to scan for expired slivers."""
    for d in data:
        for sliver in d['slivers']:
            rec = sliver.copy()
            rec.setdefault('timestamp', d['timestamp'])
            rec.setdefault('type', 'sliver.VServer')

            # convert attributes field to a proper dict
            attr_dict = {}
            for attr in rec.pop('attributes'): attr_dict[attr['name']] = attr['value']

            # squash keys
            keys = rec.pop('keys')
            rec.setdefault('keys', '\n'.join([key_struct['key'] for key_struct in keys]))

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
        database.db.set_min_timestamp(d['timestamp'])
    database.db.sync()

    # handle requested startup
    global start_requested
    if start_requested:
        start_requested = False
        cumulative_delay = 0
        for name in database.db.iterkeys():
            accounts.get(name).start(delay=cumulative_delay)
            cumulative_delay += 3


def start(options):
    accounts.register_class(sliver_vs.Sliver_VS)
    accounts.register_class(delegate.Delegate)
    global start_requested
    start_requested = options.startup
    database.start()
    api.start()
