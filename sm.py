"""Sliver manager.

The sliver manager has several functions.  It is responsible for
creating, resource limiting, starting, stopping, and destroying
slivers.  It provides an API for users to access these functions and
also to make inter-sliver resource loans.  The sliver manager is also
responsible for handling delegation accounts.
"""

# $Id: sm.py,v 1.12.2.5 2007/07/20 19:44:11 faiyaza Exp $

try: from bwlimit import bwmin, bwmax
except ImportError: bwmin, bwmax = 8, 1000*1000*1000
import accounts
import api
import database
import delegate
import logger
import sliver_vs
import string,re


DEFAULT_ALLOCATION = {
    'enabled': 1,
    # CPU parameters
    'cpu_min': 0, # ms/s
    'cpu_share': 32, # proportional share
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

### Emulab-specific hack begins here
#    emulabdelegate = {
#        'instantiation': 'plc-instantiated',
#        'keys': '''ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA5Rimz6osRvlAUcaxe0YNfGsLL4XYBN6H30V3l/0alZOSXbGOgWNdEEdohwbh9E8oYgnpdEs41215UFHpj7EiRudu8Nm9mBI51ARHA6qF6RN+hQxMCB/Pxy08jDDBOGPefINq3VI2DRzxL1QyiTX0jESovrJzHGLxFTB3Zs+Y6CgmXcnI9i9t/zVq6XUAeUWeeXA9ADrKJdav0SxcWSg+B6F1uUcfUd5AHg7RoaccTldy146iF8xvnZw0CfGRCq2+95AU9rbMYS6Vid8Sm+NS+VLaAyJaslzfW+CAVBcywCOlQNbLuvNmL82exzgtl6fVzutRFYLlFDwEM2D2yvg4BQ== root@boss.emulab.net''',
 #       'name': 'utah_elab_delegate',
 #       'timestamp': data['timestamp'],
 #       'type': 'delegate',
 #       'vref': None
 #       }
 #   database.db.deliver_record(emulabdelegate)
### Emulab-specific hack ends here


    initscripts_by_id = {}
    for is_rec in data['initscripts']:
        initscripts_by_id[str(is_rec['initscript_id'])] = is_rec['script']
   
    for sliver in data['slivers']:
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

        rec.setdefault('vref', attr_dict.get('vref', 'default'))
        is_id = attr_dict.get('plc_initscript_id')
        if is_id is not None and is_id in initscripts_by_id:
            rec['initscript'] = initscripts_by_id[is_id]
        else:
            rec['initscript'] = ''
        rec.setdefault('delegations', attr_dict.get("delegations", []))

        # extract the implied rspec
        rspec = {}
        rec['rspec'] = rspec
        for resname, default_amt in DEFAULT_ALLOCATION.iteritems():
            try: amt = int(attr_dict[resname])
            except KeyError: amt = default_amt
            except ValueError:
                if type(default_amt) is type('str'):
                    amt = attr_dict[resname]
                else:
                    amt = default_amt
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
    api.deliver_ticket = deliver_ticket
    api.start()
