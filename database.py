"""The database houses information on slivers.  This information
reaches the sliver manager in two different ways: one, through the
GetSlivers() call made periodically; two, by users delivering tickets.
The sync() method of the Database class turns this data into reality.

The database format is a dictionary that maps account names to records
(also known as dictionaries).  Inside each record, data supplied or
computed locally is stored under keys that begin with an underscore,
and data from PLC is stored under keys that don't.

In order to maintain service when the node reboots during a network
partition, the database is constantly being dumped to disk.
"""

import cPickle
import threading
import time

import accounts
import logger
import tools
import bwmon

# We enforce minimum allocations to keep the clueless from hosing their slivers.
# Disallow disk loans because there's currently no way to punish slivers over quota.
MINIMUM_ALLOCATION = {'cpu_min': 0, 'cpu_share': 32, 'net_min_rate': 0, 'net_max_rate': 8, 'net_i2_min_rate': 0, 'net_i2_max_rate': 8, 'net_share': 1}
LOANABLE_RESOURCES = MINIMUM_ALLOCATION.keys()

DB_FILE = '/root/sliver_mgr_db.pickle'


# database object and associated lock
db_lock = threading.RLock()
db = None

# these are used in tandem to request a database dump from the dumper daemon
db_cond = threading.Condition(db_lock)
dump_requested = False

# decorator that acquires and releases the database lock before and after the decorated operation
# XXX - replace with "with" statements once we switch to 2.5
def synchronized(fn):
    def sync_fn(*args, **kw_args):
        db_lock.acquire()
        try: return fn(*args, **kw_args)
        finally: db_lock.release()
    sync_fn.__doc__ = fn.__doc__
    sync_fn.__name__ = fn.__name__
    return sync_fn


class Database(dict):
    def __init__(self):
        self._min_timestamp = 0

    def _compute_effective_rspecs(self):
        """Calculate the effects of loans and store the result in field _rspec.  At the moment, we allow slivers to loan only those resources that they have received directly from PLC.  In order to do the accounting, we store three different rspecs: field 'rspec', which is the resources given by PLC; field '_rspec', which is the actual amount of resources the sliver has after all loans; and variable resid_rspec, which is the amount of resources the sliver has after giving out loans but not receiving any."""
        slivers = {}
        for name, rec in self.iteritems():
            if 'rspec' in rec:
                rec['_rspec'] = rec['rspec'].copy()
                slivers[name] = rec
        for rec in slivers.itervalues():
            eff_rspec = rec['_rspec']
            resid_rspec = rec['rspec'].copy()
            for target, resname, amt in rec.get('_loans', []):
                if target in slivers and amt <= resid_rspec[resname] - MINIMUM_ALLOCATION[resname]:
                    eff_rspec[resname] -= amt
                    resid_rspec[resname] -= amt
                    slivers[target]['_rspec'][resname] += amt

    def deliver_record(self, rec):
        """A record is simply a dictionary with 'name' and 'timestamp' keys.  We keep some persistent private data in the records under keys that start with '_'; thus record updates should not displace such keys."""
        if rec['timestamp'] < self._min_timestamp: return
        name = rec['name']
        old_rec = self.get(name)
        if old_rec == None: self[name] = rec
        elif rec['timestamp'] > old_rec['timestamp']:
            for key in old_rec.keys():
                if not key.startswith('_'): del old_rec[key]
            old_rec.update(rec)

    def set_min_timestamp(self, ts):
        """The ._min_timestamp member is the timestamp on the last comprehensive update.  We use it to determine if a record is stale.  This method should be called whenever new GetSlivers() data comes in."""
        self._min_timestamp = ts
        for name, rec in self.items():
            if rec['timestamp'] < ts: del self[name]

    def sync(self):
        """Synchronize reality with the database contents.  This method does a lot of things, and it's currently called after every single batch of database changes (a GetSlivers(), a loan, a record).  It may be necessary in the future to do something smarter."""

        # delete expired records
        now = time.time()
        for name, rec in self.items():
            if rec.get('expires', now) < now: del self[name]

        self._compute_effective_rspecs()

        # create and destroy accounts as needed
        existing_acct_names = accounts.all()
        for name in existing_acct_names:
            if name not in self: accounts.get(name).ensure_destroyed()
        for name, rec in self.iteritems():
            if rec['instantiation'] == 'plc-instantiated': accounts.get(name).ensure_created(rec)

        bwmon.GetSlivers(self)

        # request a database dump
        global dump_requested
        dump_requested = True
        db_cond.notify()


def start():
    """The database dumper daemon.  When it starts up, it populates the database with the last dumped database.  It proceeds to handle dump requests forever."""
    def run():
        global dump_requested
        while True:
            db_lock.acquire()
            while not dump_requested: db_cond.wait()
            db_pickle = cPickle.dumps(db, cPickle.HIGHEST_PROTOCOL)
            dump_requested = False
            db_lock.release()
            try: tools.write_file(DB_FILE, lambda f: f.write(db_pickle))
            except: logger.log_exc()
    global db
    try:
        f = open(DB_FILE)
        try: db = cPickle.load(f)
        finally: f.close()
    except:
        logger.log_exc()
        db = Database()
    tools.as_daemon_thread(run)
