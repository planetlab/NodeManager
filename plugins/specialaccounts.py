#!/usr/bin/python -tt
# vim:set ts=4 sw=4 expandtab:
#
# $Id$
# $URL$
#
# NodeManager plugin to create special accounts

"""
create/populate accounts/ssh keys for special persons such as root, site_admin, etc.

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

# right after conf_files
priority = 3

def start(options, conf):
    logger.log("specialaccounts: plugin starting up...")

def GetSlivers(data, conf = None, plc = None):
    if 'accounts' not in data:
        logger.log_missing_data("specialaccounts.GetSlivers",'accounts')
        return

    for account in data['accounts']:
        name = account['name']
        new_keys = account['keys']

        logger.log('specialaccounts: dealing with account %s'%name)

        # look up account name, which must exist
        pw_info = pwd.getpwnam(name)
        uid = pw_info[2]
        gid = pw_info[3]
        pw_dir = pw_info[5]

        # populate account's .ssh/authorized_keys file
        dot_ssh = os.path.join(pw_dir,'.ssh')
        if not os.access(dot_ssh, os.F_OK): os.mkdir(dot_ssh)
        auth_keys = os.path.join(dot_ssh,'authorized_keys')

        # catenate all keys in string, add newlines just in case (looks like keys already have this, but)
        auth_keys_contents = '\n'.join(new_keys)+'\n'

        changes = tools.replace_file_with_string(auth_keys,auth_keys_contents)
        if changes:
            logger.log("specialaccounts: keys file changed: %s" % auth_keys)

        # always set permissions properly
        os.chmod(dot_ssh, 0700)
        os.chown(dot_ssh, uid,gid)
        os.chmod(auth_keys, 0600)
        os.chown(auth_keys, uid,gid)

        logger.log('specialaccounts: installed ssh keys for %s' % name)
