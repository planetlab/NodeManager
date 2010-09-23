#!/usr/bin/python -tt
# vim:set ts=4 sw=4 expandtab:
#
# $Id$
# $URL$
#
# NodeManager plugin for creating credentials in slivers
# (*) empower slivers to make API calls throught hmac
# (*) also create a ssh key - used by the OMF resource controller 
#     for authenticating itself with its Experiment Controller
# xxx todo : a config option for turning these 2 things on or off ?

"""
Sliver authentication support for NodeManager.

"""

import os
import random
import string
import tempfile
import socket

import logger
import tools

def start():
    logger.log("sliverauth: (dummy) plugin starting up...")

def GetSlivers(data, config, plc):
    if 'OVERRIDES' in dir(config):
        if config.OVERRIDES.get('sliverauth') == '-1':
            logger.log("sliverauth:  Disabled", 2)
            return

    if 'slivers' not in data:
        logger.log_missing_data("sliverauth.GetSlivers", 'slivers')
        return

    for sliver in data['slivers']:
        path = '/vservers/%s' % sliver['name']
        if not os.path.exists(path):
            # ignore all non-plc-instantiated slivers
            instantiation = sliver.get('instantiation','')
            if instantiation == 'plc-instantiated':
                logger.log("sliverauth: plc-instantiated slice %s does not yet exist. IGNORING!" % sliver['name'])
            continue

        manage_hmac (plc, sliver)
        manage_sshkey (plc, sliver)


def SetSliverTag(plc, slice, tagname, value):
    node_id = tools.node_id()
    slivertags=plc.GetSliceTags({"name":slice,"node_id":node_id,"tagname":tagname})
    if len(slivertags)==0:
        # looks like GetSlivers reports about delegated/nm-controller slices that do *not* belong to this node
        # and this is something that AddSliceTag does not like
        try:
            slivertag_id=plc.AddSliceTag(slice,tagname,value,node_id)
        except:
            logger.log_exc ("sliverauth.SetSliverTag (probably delegated) slice=%(slice)s tag=%(tagname)s node_id=%(node_id)d"%locals())
            pass
    else:
        slivertag_id=slivertags[0]['slice_tag_id']
        plc.UpdateSliceTag(slivertag_id,value)

def find_tag (sliver, tagname):
    for attribute in sliver['attributes']:
        # for legacy, try the old-fashioned 'name' as well
        name = attribute.get('tagname',attribute.get('name',''))
        if name == tagname:
            return attribute['value']
    return None

def manage_hmac (plc, sliver):
    hmac = find_tag (sliver, 'hmac')

    if not hmac:
        # let python do its thing 
        random.seed()
        d = [random.choice(string.letters) for x in xrange(32)]
        hmac = "".join(d)
        SetSliverTag(plc,sliver['name'],'hmac',hmac)
        logger.log("sliverauth: %s: setting hmac" % sliver['name'])

    path = '/vservers/%s/etc/planetlab' % sliver['name']
    if os.path.exists(path):
        keyfile = '%s/key' % path
        if (tools.replace_file_with_string(keyfile,hmac,chmod=0400)):
            logger.log ("sliverauth: (over)wrote hmac into %s " % keyfile)

# create the key if needed and returns the key contents
def generate_sshkey (sliver): 
# initial version was storing stuff in the sliver directly
#    keyfile="/vservers/%s/home/%s/.ssh/id_rsa"%(sliver['name'],sliver['name'])
# we're now storing this in the same place as the authorized_keys, which in turn
# gets mounted to the user's home directory in the sliver
    keyfile="/home/%s/.ssh/id_rsa"%(sliver['name'])
    pubfile="%s.pub"%keyfile
    dotssh=os.path.dirname(keyfile)
    # create dir if needed
    if not os.path.isdir (dotssh):
        os.mkdir (dotssh, 0700)
        logger.log_call ( [ 'chown', "%s:slices"%(sliver['name']), dotssh ] )
    if not os.path.isfile (pubfile):
        comment="%s@%s"%(sliver['name'],socket.gethostname())
        logger.log_call( [ 'ssh-keygen', '-t', 'rsa', '-N', '', '-f', keyfile , '-C', comment] )
        os.chmod (keyfile, 0400)
        logger.log_call ( [ 'chown', "%s:slices"%(sliver['name']), keyfile, pubfile ] )
    return file(pubfile).read().strip()

# a sliver can get created, deleted and re-created
# the slice having the tag is not sufficient to skip key geneneration
def manage_sshkey (plc, sliver):
    # regardless of whether the tag is there or not, we need to grab the file
    # if it's lost b/c e.g. the sliver was destroyed we cannot save the tags content
    ssh_key = generate_sshkey(sliver)
    old_tag = find_tag (sliver, 'ssh_key')
    if ssh_key <> old_tag:
        SetSliverTag(plc, sliver['name'], 'ssh_key', ssh_key)
        logger.log ("sliverauth: %s: setting ssh_key" % sliver['name'])
