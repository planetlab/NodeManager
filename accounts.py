"""Functionality common to all account classes.

Each subclass of Account must provide five methods: create() and
destroy(), which are static; configure(), start(), and stop(), which
are not.  configure(), which takes a record as its only argument, does
things like set up ssh keys.  In addition, an Account subclass must
provide static member variables SHELL, which contains the unique shell
that it uses; and TYPE, a string that is used by the account creation
code.  For no particular reason, TYPE is divided hierarchically by
periods; at the moment the only convention is that all sliver accounts
have type that begins with sliver.

There are any number of race conditions that may result from the fact
that account names are not unique over time.  Moreover, it's a bad
idea to perform lengthy operations while holding the database lock.
In order to deal with both of these problems, we use a worker thread
for each account name that ever exists.  On 32-bit systems with large
numbers of accounts, this may cause the NM process to run out of
*virtual* memory!  This problem may be remedied by decreasing the
maximum stack size.
"""

import Queue
import os
import pwd
import threading

import logger
import tools


# When this variable is true, start after any ensure_created
Startingup = False
# Cumulative delay for starts when Startingup is true
csd_lock = threading.Lock()
cumstartdelay = 0

# shell path -> account class association
shell_acct_class = {}
# account type -> account class association
type_acct_class = {}

def register_class(acct_class):
    """Call once for each account class.  This method adds the class to the dictionaries used to look up account classes by shell and type."""
    shell_acct_class[acct_class.SHELL] = acct_class
    type_acct_class[acct_class.TYPE] = acct_class


# private account name -> worker object association and associated lock
name_worker_lock = threading.Lock()
name_worker = {}

def allpwents():
    return [pw_ent for pw_ent in pwd.getpwall() if pw_ent[6] in shell_acct_class]

def all():
    """Return the names of all accounts on the system with recognized shells."""
    return [pw_ent[0] for pw_ent in allpwents()]

def get(name):
    """Return the worker object for a particular username.  If no such object exists, create it first."""
    name_worker_lock.acquire()
    try:
        if name not in name_worker: name_worker[name] = Worker(name)
        return name_worker[name]
    finally: name_worker_lock.release()


class Account:
    def __init__(self, rec):
        logger.verbose('Initing account %s'%rec['name'])
        self.name = rec['name']
        self.keys = ''
        self.initscriptchanged = False
        self.configure(rec)

    @staticmethod
    def create(name, vref = None): abstract
    @staticmethod
    def destroy(name): abstract

    def configure(self, rec):
        """Write <rec['keys']> to my authorized_keys file."""
        logger.verbose('in accounts:configure')
        new_keys = rec['keys']
        if new_keys != self.keys:
            self.keys = new_keys
            dot_ssh = '/home/%s/.ssh' % self.name
            def do_installation():
                if not os.access(dot_ssh, os.F_OK): os.mkdir(dot_ssh)
                os.chmod(dot_ssh, 0700)
                tools.write_file(dot_ssh + '/authorized_keys', lambda f: f.write(new_keys))
            logger.verbose('%s: installing ssh keys' % self.name)
            tools.fork_as(self.name, do_installation)

    def start(self, delay=0): pass
    def stop(self): pass


class Worker:
    # these semaphores are acquired before creating/destroying an account
    _create_sem = threading.Semaphore(1)
    _destroy_sem = threading.Semaphore(1)

    def __init__(self, name):
        self.name = name  # username
        self._acct = None  # the account object currently associated with this worker
        # task list
        # outsiders request operations by putting (fn, args...) tuples on _q
        # the worker thread (created below) will perform these operations in order
        self._q = Queue.Queue()
        tools.as_daemon_thread(self._run)

    def ensure_created(self, rec):
        """Cause the account specified by <rec> to exist if it doesn't already."""
        if rec.has_key('name'):
            logger.verbose('Worker.ensure_created with name=%s'%rec['name'])
        self._q.put((self._ensure_created, rec.copy(), Startingup))
        logger.verbose('Worker queue has %d item(s)'%self._q.qsize())

    def _ensure_created(self, rec, startingup):
        curr_class = self._get_class()
        next_class = type_acct_class[rec['type']]
        if next_class != curr_class:
            self._destroy(curr_class)
            self._create_sem.acquire()
            try: next_class.create(self.name, rec['vref'])
            finally: self._create_sem.release()
        if not isinstance(self._acct, next_class): self._acct = next_class(rec)
        else: self._acct.configure(rec)
        if startingup:
            csd_lock.acquire()
            global cumstartdelay
            delay = cumstartdelay
            cumstartdelay += 2
            csd_lock.release()
            self._acct.start(delay=delay)
        elif next_class != curr_class or self._acct.initscriptchanged:
            self._acct.start()

    def ensure_destroyed(self): self._q.put((self._ensure_destroyed,))
    def _ensure_destroyed(self): self._destroy(self._get_class())

    def start(self, delay=0): self._q.put((self._start, delay))
    def _start(self, d): self._acct.start(delay=d)

    def stop(self): self._q.put((self._stop,))
    def _stop(self): self._acct.stop()

    def _destroy(self, curr_class):
        self._acct = None
        if curr_class:
            self._destroy_sem.acquire()
            try: curr_class.destroy(self.name)
            finally: self._destroy_sem.release()

    def _get_class(self):
        try: shell = pwd.getpwnam(self.name)[6]
        except KeyError: return None
        return shell_acct_class[shell]

    def _run(self):
        """Repeatedly pull commands off the queue and execute.  If memory usage becomes an issue, it might be wise to terminate after a while."""
        while True:
            try:
                logger.verbose('Worker:_run : getting - size is %d'%self._q.qsize())
                cmd = self._q.get()
                cmd[0](*cmd[1:])
            except:
                logger.log_exc(self.name)
