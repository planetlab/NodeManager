import cPickle
import sys
import threading
import time

from config import DB_FILE
import accounts
import bwcap
import logger
import tools


_db_lock = threading.RLock()
_db_cond = threading.Condition(_db_lock)
_dump_requested = False


def synchronized(function):
    def sync_fun(*args, **kw_args):
        _db_lock.acquire()
        try: return function(*args, **kw_args)
        finally: _db_lock.release()
    sync_fun.__doc__ = function.__doc__
    sync_fun.__name__ = function.__name__
    return sync_fun


class Database(dict):
    def deliver_records(self, recs):
        ts = self.get_timestamp()
        for rec in recs:
            old_rec = self.setdefault(rec['record_key'], {})
            if rec['timestamp'] >= max(ts, old_rec.get('timestamp', 0)):
                old_rec.update(rec, dirty=True)
        self.compute_effective_rspecs()
        if self.get_timestamp() > ts:
            self.delete_old_records()
            self.delete_old_accounts()
            for rec in self.itervalues(): rec['dirty'] = True
        self.create_new_accounts()
        self.update_bwcap()

    def get_timestamp(self):
        return self.get('timestamp', {'timestamp': 0})['timestamp']


    def compute_effective_rspecs(self):
        """Apply loans to field 'rspec' to get field 'eff_rspec'."""
        slivers = dict([(rec['name'], rec) for rec in self.itervalues() \
                        if rec.get('account_type') == 'sliver'])

        # Pass 1: copy 'rspec' to 'eff_rspec', saving the old value
        for sliver in slivers.itervalues():
            sliver['old_eff_rspec'] = sliver.get('eff_rspec')
            sliver['eff_rspec'] = sliver['rspec'].copy()

        # Pass 2: apply loans
        for sliver in slivers.itervalues():
            remaining_loanable_amount = sliver['rspec'].copy()
            for other_name, resource, amount in sliver.get('loans', []):
                if other_name in slivers and \
                       0 < amount <= remaining_loanable_amount[resource]:
                    sliver['eff_rspec'][resource] -= amount
                    remaining_loanable_amount[resource] -= amount
                    slivers[other_name]['eff_rspec'][resource] += amount

        # Pass 3: mark changed rspecs dirty
        for sliver in slivers.itervalues():
            if sliver['eff_rspec'] != sliver['old_eff_rspec']:
                sliver['needs_update'] = True
            del sliver['old_eff_rspec']


    def delete_old_records(self):
        ts = self.get_timestamp()
        now = time.time()
        for key in self.keys():
            rec = self[key]
            if rec['timestamp'] < ts or rec.get('expiry', sys.maxint) < now:
                del self[key]

    def delete_old_accounts(self):
        for acct_type, name in accounts.all():
            if ('%s_%s' % (acct_type, name)) not in self:
                accounts.get(name).ensure_destroyed()

    def create_new_accounts(self):
        """Invoke the appropriate create() function for every dirty account."""
        for rec in self.itervalues():
            if 'account_type' not in rec: continue
            if rec['dirty'] and rec['plc_instantiated']:
                accounts.get(rec['name']).ensure_created(rec)
            rec['dirty'] = False

    def update_bwcap(self):
        bwcap_rec = self.get('bwcap')
        if bwcap_rec and bwcap_rec['dirty']:
            bwcap.update(bwcap_rec)
            bwcap_rec['dirty'] = False


_db = Database()

@synchronized
def deliver_records(recs):
    global _dump_requested
    _db.deliver_records(recs)
    _dump_requested = True
    _db_cond.notify()

@synchronized
def get_sliver(name): return _db.get('sliver_'+name)

def start():
    def run():
        global _dump_requested
        _db_lock.acquire()
        try:  # load the db
            f = open(DB_FILE)
            _db.update(cPickle.load(f))
            f.close()
        except: logger.log_exc()
        while True:  # handle dump requests forever
            while not _dump_requested:
                _db_cond.wait()
            db_copy = tools.deepcopy(_db)
            _dump_requested = False
            _db_lock.release()
            try: tools.write_file(DB_FILE,
                                  lambda f: cPickle.dump(db_copy, f, -1))
            except: logger.log_exc()
            _db_lock.acquire()
    tools.as_daemon_thread(run)
