import Queue
import os
import pwd
import threading

import logger
import tools


_name_worker_lock = threading.Lock()
_name_worker = {}

def all():
    pw_ents = pwd.getpwall()
    for pw_ent in pw_ents:
        if pw_ent[6] in acct_class_by_shell:
            yield acct_class_by_shell[pw_ent[6]].TYPE, pw_ent[0]

def get(name):
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


TYPES = []
acct_class_by_shell = {}
acct_class_by_type = {}

def register_account_type(acct_class):
    TYPES.append(acct_class.TYPE)
    acct_class_by_shell[acct_class.SHELL] = acct_class
    acct_class_by_type[acct_class.TYPE] = acct_class


class Worker:
    # these semaphores are acquired before creating/destroying an account
    _create_sem = threading.Semaphore(1)
    _destroy_sem = threading.Semaphore(1)

    def __init__(self, name):
        self.name = name
        self._acct = None
        self._q = Queue.Queue()
        tools.as_daemon_thread(self._run)

    def ensure_created(self, rec):
        self._q.put((self._ensure_created, tools.deepcopy(rec)))

    def _ensure_created(self, rec):
        curr_class = self._get_class()
        next_class = acct_class_by_type[rec['account_type']]
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
        return acct_class_by_shell[shell]

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
