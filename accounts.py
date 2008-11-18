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

"""

import Queue
import os
import pwd
from grp import getgrnam
import threading

import logger
import tools


# When this variable is true, start after any ensure_created
Startingup = False
# shell path -> account class association
shell_acct_class = {}
# account type -> account class association
type_acct_class = {}

# these semaphores are acquired before creating/destroying an account
create_sem = threading.Semaphore(1)
destroy_sem = threading.Semaphore(1)

def register_class(acct_class):
    """Call once for each account class.  This method adds the class to the dictionaries used to look up account classes by shell and type."""
    shell_acct_class[acct_class.SHELL] = acct_class
    type_acct_class[acct_class.TYPE] = acct_class


# private account name -> worker object association and associated lock
name_worker_lock = threading.Lock()
# dict of account_name: <Worker Object>
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
        if name not in name_worker: 
            logger.verbose("Accounts:get(%s) new Worker" % name)
            name_worker[name] = Worker(name)
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
        logger.verbose('%s: in accounts:configure'%self.name)
        new_keys = rec['keys']
        if new_keys != self.keys:
            self.keys = new_keys
            dot_ssh = '/home/%s/.ssh' % self.name
            if not os.access(dot_ssh, os.F_OK): os.mkdir(dot_ssh)
            os.chmod(dot_ssh, 0700)
            tools.write_file(dot_ssh + '/authorized_keys', lambda f: f.write(new_keys))
            logger.log('%s: installing ssh keys' % self.name)
            user = pwd.getpwnam(self.name)[2]
            group = getgrnam("slices")[2]
            os.chown(dot_ssh, user, group)
            os.chown(dot_ssh + '/authorized_keys', user, group)

    def start(self, delay=0): pass
    def stop(self): pass
    def is_running(self): pass

class Worker:
    def __init__(self, name):
        self.name = name  # username
        self._acct = None  # the account object currently associated with this worker

    def ensure_created(self, rec, startingup = Startingup):
        """Check account type is still valid.  If not, recreate sliver.  If still valid,
        check if running and configure/start if not."""
        curr_class = self._get_class()
        next_class = type_acct_class[rec['type']]
        if next_class != curr_class:
            self._destroy(curr_class)
            create_sem.acquire()
            try: next_class.create(self.name, rec['vref'])
            finally: create_sem.release()
        if not isinstance(self._acct, next_class): self._acct = next_class(rec)
        if startingup or \
          not self.is_running() or \
          next_class != curr_class or \
          self._acct.initscriptchanged:
            self.start(rec)
        else: self._acct.configure(rec)

    def ensure_destroyed(self): self._destroy(self._get_class())

    def start(self, rec, d = 0): 
        self._acct.configure(rec)
        self._acct.start(delay=d)

    def stop(self): self._acct.stop()

    def is_running(self): 
        if self._acct.is_running():
            status = True
        else:
            status = False
            logger.verbose("Worker(%s): is not running" % self.name)
        return status

    def _destroy(self, curr_class):
        self._acct = None
        if curr_class:
            destroy_sem.acquire()
            try: curr_class.destroy(self.name)
            finally: destroy_sem.release()

    def _get_class(self):
        try: shell = pwd.getpwnam(self.name)[6]
        except KeyError: return None
        return shell_acct_class[shell]
