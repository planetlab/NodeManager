#!/usr/bin/python -tt
# vim:set ts=4 sw=4 expandtab:
# NodeManager plugin to create special accounts

"""
Have NM create/populate accounts/ssh keys for special persons such as root, site_admin, etc.

"""

import errno
import os
import random
import string
import tempfile
import grp
import pwd

import logger
import tools

def start(options, conf):
    logger.log("personkeys plugin starting up...")

def GetSlivers(data, conf = None, plc = None):
    if 'accounts' not in data: 
        logger.log("specialaccounts: No account information found.  DISABLED!")
        return

    for account in data['accounts']:
        name = account['name']
        new_keys = account['keys']

        # look up account name, which must exist
        pw_info = pwd.getpwnam(name)
        uid = pw_info[2]
        gid = pw_info[3]
        pw_dir = pw_info[5]

        # populate account's .ssh/authorized_keys file
        dot_ssh = os.path.join(pw_dir,'.ssh')
        if not os.access(dot_ssh, os.F_OK): os.mkdir(dot_ssh)
        auth_keys = os.path.join(dot_ssh,'authorized_keys')

        logger.log("new keys = %s" % auth_keys)
        fd, fname = tempfile.mkstemp('','authorized_keys',dot_ssh)

        for key in new_keys:
            os.write(fd,key)
            os.write(fd,'\n')

        os.close(fd)
        if os.path.exists(auth_keys): os.unlink(auth_keys)
        os.rename(fname, auth_keys)

        # set permissions properly
        os.chmod(dot_ssh, 0700)
        os.chown(dot_ssh, uid,gid)
        os.chmod(auth_keys, 0600)
        os.chown(auth_keys, uid,gid)

        logger.log('specialacounts: installed ssh keys for %s' % name)
