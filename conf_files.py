"""configuration files"""

import grp
import os
import pwd
import sha
import string
import threading

import config
import curlwrapper
import logger
import tools


class conf_files:
    def __init__(self):
        self.cond = threading.Condition()
        self.config = config.Config()
        self.data = None

    def checksum(self, path):
        try:
            f = open(path)
            try: return sha.new(f.read()).digest()
            finally: f.close()
        except IOError: return None

    def system(self, cmd):
        if cmd:
            logger.log('conf_files: running command %s' % cmd)
            return os.system(cmd)
        else: return 0

    def update_conf_file(self, cf_rec):
        if not cf_rec['enabled']: return
        dest = cf_rec['dest']
        logger.log('conf_files: considering file %s' % dest)
        err_cmd = cf_rec['error_cmd']
        mode = string.atoi(cf_rec['file_permissions'], base=8)
        uid = pwd.getpwnam(cf_rec['file_owner'])[2]
        gid = grp.getgrnam(cf_rec['file_group'])[2]
        url = 'https://%s/%s' % (self.config.PLC_BOOT_HOST, cf_rec['source'])
        contents = curlwrapper.retrieve(url)
        logger.log('conf_files: retrieving url %s' % url)
        if not cf_rec['always_update'] and sha.new(contents).digest() == self.checksum(dest):
            logger.log('conf_files: skipping file %s, always_update is false and checksums are identical' % dest)
            return
        if self.system(cf_rec['preinstall_cmd']):
            self.system(err_cmd)
            if not cf_rec['ignore_cmd_errors']: return
        logger.log('conf_files: installing file %s' % dest)
        tools.write_file(dest, lambda f: f.write(contents), mode=mode, uidgid=(uid,gid))
        if self.system(cf_rec['postinstall_cmd']): system(err_cmd)

    def run(self):
        while True:
            self.cond.acquire()
            while self.data == None: self.cond.wait()
            data = self.data
            self.data = None
            self.cond.release()
            for d in data:
                for f in d['conf_files']:
                    try: self.update_conf_file(f)
                    except: logger.log_exc()

    def callback(self, data):
        if data != None:
            self.cond.acquire()
            self.data = data
            self.cond.notify()
            self.cond.release()

main = conf_files()

def GetSlivers_callback(data): main.callback(data)

def start(options): tools.as_daemon_thread(main.run)
