"""configuration files"""

import grp
import os
import pwd
import sha
import string
import urllib

import logger
import tools


BOOT_SERVER = "plc-a.demo.vmware"


def checksum(path):
    try:
        f = open(path)
        try: return sha.new(f.read()).digest()
        finally: f.close()
    except IOError: return None

def system(cmd):
    if cmd:
        logger.log('cf: running command %s' % cmd)
        return os.system(cmd)
    else: return 0

def conf_file(cf_rec):
    if not cf_rec['enabled']: return
    dest = cf_rec['dest']
    logger.log('cf: considering file %s' % dest)
    err_cmd = cf_rec['error_cmd']
    mode = string.atoi(cf_rec['file_permissions'], base=8)
    uid = pwd.getpwnam(cf_rec['file_owner'])[2]
    gid = grp.getgrnam(cf_rec['file_group'])[2]
    src, msg = urllib.urlretrieve('https://%s%s' % (BOOT_SERVER, cf_rec['source']))
    if not cf_rec['always_update'] and checksum(src) == checksum(dest):
        logger.log('cf: skipping file %s, always_update is false and checksums are identical' % dest)
        return
    if system(cf_rec['preinstall_cmd']):
        system(err_cmd)
        if not cf_rec['ignore_cmd_errors']: return
    logger.log('cf: installing file %s' % dest)
    os.chmod(src, mode)
    os.chown(src, uid, gid)
    os.rename(src, dest)
    if system(cf_rec['postinstall_cmd']): system(err_cmd)

def GetSlivers_callback(data):
    def run():
        for d in data:
            for f in d['conf_files']:
                try: conf_file(f)
                except: logger.log_exc()
    tools.as_daemon_thread(run)

def start(options): pass
