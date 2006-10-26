"""Functionality common to all account classes.

Each account class must provide five methods: create(), destroy(),
configure(), start(), and stop().  In addition, it must provide static
member variables SHELL, which contains the unique shell that it uses;
and TYPE, which contains a description of the type that it uses.  TYPE
is divided hierarchically by periods; at the moment the only
convention is that all sliver accounts have type that begins with
sliver.

Because Python does dynamic method lookup, we do not bother with a
boilerplate abstract superclass.

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


# shell path -> account class association
shell_acct_class = {}
# account type -> account class association
type_acct_class = {}

def register_class(acct_class):
    """Call once for each account class.  This method adds the class to the dictionaries used to look up account classes by shell and type."""
    shell_acct_class[acct_class.SHELL] = acct_class
    type_acct_class[acct_class.TYPE] = acct_class


# private account name -> worker object association and associated lock
_name_worker_lock = threading.Lock()
_name_worker = {}

def all():
    """Return the names of all accounts on the system with recognized shells."""
    return [pw_ent[0] for pw_ent in pwd.getpwall() if pw_ent[6] in shell_acct_class]

def get(name):
    """Return the worker object for a particular username.  If no such object exists, create it first."""
    _name_worker_lock.acquire()
    try:
        if name not in _name_worker: _name_worker[name] = Worker(name)
        return _name_worker[name]
    finally: _name_worker_lock.release()


def install_keys(rec):
    """Write <rec['keys']> to <rec['name']>'s authorized_keys file."""
    name = rec['name']
    dot_ssh = '/home/%s/.ssh' % name
    def do_installation():
        if not os.access(dot_ssh, os.F_OK): os.mkdir(dot_ssh)
        tools.write_file(dot_ssh + '/authorized_keys', lambda thefile: thefile.write(rec['keys']))
    logger.log('%s: installing ssh keys' % name)
    tools.fork_as(name, do_installation)


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
        self._q.put((self._ensure_created, rec.copy()))

    def _ensure_created(self, rec):
        curr_class = self._get_class()
        next_class = type_acct_class[rec['account_type']]
        if next_class != curr_class:
            self._destroy(curr_class)
            self._create_sem.acquire()
            try: next_class.create(self.name)
            finally: self._create_sem.release()
        self._make_acct_obj()
        self._acct.configure(rec)
        if next_class != curr_class: self._acct.start()

    def ensure_destroyed(self): self._q.put((self._ensure_destroyed,))
    def _ensure_destroyed(self): self._destroy(self._get_class())

    def start(self): self._q.put((self._start,))
    def _start(self):
        self._make_acct_obj()
        self._acct.start()

    def stop(self): self._q.put((self._stop,))
    def _stop(self):
        self._make_acct_obj()
        self._acct.stop()

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

    def _make_acct_obj(self):
        curr_class = self._get_class()
        if not isinstance(self._acct, curr_class): self._acct = curr_class(self.name)

    def _run(self):
        while True:
            try:
                cmd = self._q.get()
                cmd[0](*cmd[1:])
            except: logger.log_exc()
