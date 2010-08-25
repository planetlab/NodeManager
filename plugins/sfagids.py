#!/usr/bin/python -tt
# vim:set ts=4 sw=4 expandtab:
#
# $Id$
# $URL$
#
# NodeManager plugin for installing SFA GID's in slivers
# 

import os
import sys
sys.path.append('/usr/share/NodeManager')
import logger
import traceback
try:
    from sfa.util.namespace import *
    from sfa.util.config import Config
    import sfa.util.xmlrpcprotocol as xmlrpcprotocol
    from sfa.trust.certificate import Keypair, Certificate
    from sfa.trust.credential import Credential
    from sfa.trust.gid import GID
    from sfa.trust.hierarchy import Hierarchy
    from sfa.plc.api import ComponentAPI
    sfa = True      
except:
    sfa = None

def start():
    logger.log("sfagid: plugin starting up ...")
    if not sfa:
        return
    keyfile, certfile = get_keypair(None)
    api = ComponentAPI(key_file=keyfile, cert_file=certfile)
    api.get_node_key()

def GetSlivers(data, config=None, plc=None):
    if not sfa:
        return 

    keyfile, certfile = get_keypair(config)
    api = ComponentAPI(key_file=keyfile, cert_file=certfile)
    slivers = [sliver['name'] for sliver in data['slivers']]
    install_gids(api, slivers)
    install_trusted_certs(api)
    
def install_gids(api, slivers):
    # install node gid
    node_gid_file = api.config.config_path + os.sep + "node.gid"
    node_gid = GID(filename=node_gid_file)
    node_gid_str = node_gid.save_to_string(save_parents=True)    
    node_hrn = node_gid.get_hrn()    

    # get currently installed slice and node gids 
    interface_hrn = api.config.SFA_INTERFACE_HRN
    slice_gids = {}
    node_gids = {}
    for slicename in slivers:
        slice_gid_filename = "/vservers/%s/etc/slice.gid" % slicename
        node_gid_filename = "/vservers/%s/etc/node.gid" % slicename
        if os.path.isfile(slice_gid_filename):
            gid_file = open(slice_gid_filename, 'r') 
            slice_gids[sliver] = gid_file.read()
            gid_file.close()
        if os.path.isfile(node_gid_filename):
            gid_file = open(node_gid_filename, 'r')
            node_gids[sliver] = gid_file.read()
            gid_file.close()

    # convert slicenames to hrns
    hrns = [slicename_to_hrn(interface_hrn, slicename) \
            for slicename in slivers]

    # get current gids from registry
    cred = api.getCredential()
    registry = api.get_registry()
    records = registry.GetGids(cred, hrns)
    for record in records:
        # skip if this isnt a slice record 
        if not record['type'] == 'slice':
            continue
        vserver_path = "/vservers/%(slicename)s" % locals()
        # skip if the slice isnt instantiated
        if not os.path.exists(vserver_path):
            continue
        
        # install slice gid if it doesnt already exist or has changed
        slice_gid_str = record['gid']
        slicename = hrn_to_pl_slicename(record['hrn'])
        if slicename not in slice_gids or slice_gids[slicename] != slice_gid_str:
            gid_filename = os.sep.join([vserver_path, "etc", "slice.gid"])
            GID(string=slice_gid_str).save_to_file(gid_filename, save_parents=True)

        # install slice gid if it doesnt already exist or has changed
        if slicename not in node_gids or node_gids[slicename] != node_gid_str:
            gid_filename = os.sep.join([vserver_path, "etc", "node.gid"])
            GID(string=node_gid_str).save_to_file(gid_filename, save_parents=True) 
        
def install_trusted_certs(api):
    cred = api.getCredential()
    registry = api.get_registry()
    trusted_certs = registry.get_trusted_certs(cred)
    trusted_gid_names = []
    for gid_str in trusted_certs:
        gid = GID(string=gid_str)
        gid.decode()
        relative_filename = gid.get_hrn() + ".gid"
        trusted_gid_names.append(relative_filename)
        gid_filename = trusted_certs_dir + os.sep + relative_filename
        if verbose:
            print "Writing GID for %s as %s" % (gid.get_hrn(), gid_filename)
        gid.save_to_file(gid_filename, save_parents=True)

    # remove old certs
    all_gids_names = os.listdir(trusted_certs_dir)
    for gid_name in all_gids_names:
        if gid_name not in trusted_gid_names:
            if verbose:
                print "Removing old gid ", gid_name
            os.unlink(trusted_certs_dir + os.sep + gid_name)
    

def get_keypair(config = None):
    if not config:
        config = Config()
    hierarchy = Hierarchy()
    key_dir= hierarchy.basedir
    data_dir = config.data_path
    keyfile =data_dir + os.sep + "server.key"
    certfile = data_dir + os.sep + "server.cert"

    # check if files already exist
    if os.path.exists(keyfile) and os.path.exists(certfile):
        return (keyfile, certfile)

    # create server key and certificate
    key = Keypair(filename=node_pkey_file)
    cert = Certificate(subject=hrn)
    cert.set_issuer(key=key, subject=hrn)
    cert.set_pubkey(key)
    cert.sign()
    cert.save_to_file(certfile, save_parents=True)
    return (keyfile, certfile)
    

if __name__ == '__main__':
    test_slivers = {'slivers': [
        {'name': 'tmacktestslice', 'attributes': []}
        ]}
    start()
    GetSlivers(test_slivers) 
            
     
