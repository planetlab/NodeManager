#!/usr/bin/python -tt
# vim:set ts=4 sw=4 expandtab:
# NodeManager plugin to empower slivers to make API calls

"""
Sliver authentication support for NodeManager.

"""

import errno
import os
import random
import string
import tempfile
import time

import logger
import tools

def start(options, conf):
    logger.log("sliverauth plugin starting up...")

def SetSliverTag(plc, slice, tagname, value):
    node_id = tools.node_id()
    slivertags=plc.GetSliceTags({"name":slice,"node_id":node_id,"tagname":tagname})
    if len(slivertags)==0:
        slivertag_id=plc.AddSliceTag(slice,tagname,value,node_id)
    else:
        slivertag_id=slivertags[0]['slice_tag_id']
        plc.UpdateSliceTag(slivertag_id,value)

def GetSlivers(data, config, plc):
    if 'OVERRIDES' in dir(config):
        if config.OVERRIDES.get('sliverauth') == '-1':
            logger.log("sliverauth:  Disabled", 2)
            return

    if 'slivers' not in data:
        logger.log("sliverauth: getslivers data lack's sliver information. IGNORING!")
        return

    for sliver in data['slivers']:
        found_hmac = False
        for attribute in sliver['attributes']:
            name = attribute.get('tagname',attribute.get('name',''))
            if name == 'hmac':
                found_hmac = True
                hmac = attribute['value']
                break

        if not found_hmac:
            # XXX need a better random seed?!
            random.seed(time.time())
            d = [random.choice(string.letters) for x in xrange(32)]
            hmac = "".join(d)
            SetSliverTag(plc,sliver['name'],'hmac',hmac)
            logger.log("sliverauth setting %s hmac" % sliver['name'])

        path = '/vservers/%s/etc/planetlab' % sliver['name']
        if os.path.exists(path):
            keyfile = '%s/key' % path 
            oldhmac = ''
            if os.path.exists(keyfile):
                f = open(keyfile,'r')
                oldhmac = f.read()
                f.close()

            if oldhmac <> hmac:
                # create a temporary file in the vserver
                fd, name = tempfile.mkstemp('','key',path)
                os.write(fd,hmac)
                os.close(fd)
                if os.path.exists(keyfile):
                    os.unlink(keyfile)
                os.rename(name,keyfile)
                logger.log("sliverauth writing hmac to %s " % keyfile)

            os.chmod(keyfile,0400)

