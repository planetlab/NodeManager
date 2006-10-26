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
    """Call once for each account class.  This method adds the class to the dictionaries used to ook up account classes by shell and type."""
    shell_acct_class[acct_class.SHELL] = acct_class
    type_acct_class[acct_class.TYPE] = acct_class


# private account name -> worker object association and associated lock
_name_worker_lock = threading.Lock()
_name_worker = {}

def all():
    """Returns a list of all NM accounts on the system.  Format is (type, username)."""
    pw_ents = pwd.getpwall()
    for pw_ent in pw_ents:
        if pw_ent[6] in shell_acct_class:
            yield shell_acct_class[pw_ent[6]].TYPE, pw_ent[0]

def get(name):
    """Return the worker object for a particular username.  If no such object exists, create it first."""
    _name_worker_lock.acquire()
    try:
        if name not in _name_worker: _name_worker[name] = Worker(name)
        return _name_worker[name]
    finally: _name_worker_lock.release()


def install_ssh_keys(rec):
    """Write <rec['ssh_keys']> to <rec['name']>'s authorized_keys file."""
    dot_ssh = '/home/%s/.ssh' % rec['name']
    def do_installation():
        if not os.access(dot_ssh, os.F_OK): os.mkdir(dot_ssh)
        tools.write_file(dot_ssh + '/authorized_keys',
                         lambda thefile: thefile.write(rec['ssh_keys']))
    logger.log('%s: installing ssh keys' % rec['name'])
    tools.fork_as(rec['name'], do_installation)


class Worker:
    # these semaphores are acquired before creating/destroying an account
    _create_sem = threading.Semaphore(1)
    _destroy_sem = threading.Semaphore(1)

    def __init__(self, name):
        # username
        self.name = name
        # the account object currently associated with this worker
        self._acct = None
        # task list
        # outsiders request operations by putting (fn, args...) tuples on _q
        # the worker thread (created below) will perform these operations in order
        self._q = Queue.Queue()
        tools.as_daemon_thread(self._run)

    def ensure_created(self, rec):
        """Caused the account specified by <rec> to exist if it doesn't already."""
        self._q.put((self._ensure_created, tools.deepcopy(rec)))

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
        if not isinstance(self._acct, curr_class):
            self._acct = curr_class(self.name)

    def _run(self):
        while True:
            try:
                cmd = self._q.get()
                cmd[0](*cmd[1:])
            except: logger.log_exc()
