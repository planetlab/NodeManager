#
# NodeManager plugin - first step of handling omf_controlled slices
#

"""
Overwrites the 'resctl' tag of slivers controlled by OMF so slivermanager.py does the right thing
"""

import os, os.path
import glob
import subprocess

import tools
import logger

priority = 50

def start():
    logger.log("omf_resctl: plugin starting up...")

def GetSlivers(data, conf = None, plc = None):
    if 'accounts' not in data:
        logger.log_missing_data("omf_resctl.GetSlivers",'accounts')
        return

    try:
        xmpp_server=data['xmpp']['server']
        if not xmpp_server: 
            # we have the key but no value, just as bad
            raise Exception
    except:
        # disabled feature - bailing out
        # xxx might need to clean up more deeply..
        logger.log("PLC config unsufficient (not enabled, or no server set), see the PLC_OMF category -- plugin exiting")
        return

    # as hrn is set only at AddNode-time, upgraded myplcs might still miss this
    # clue: just overwrite the hostname of all nodes
    # for node in GetNodes(): UpdateNode(node['node_id'],{'hostname':node['hostname']})
    try:
        node_hrn = data['hrn']
        if not node_hrn: raise Exception
    except:
        logger.log("Failed to read hrn from GetSlivers, using 'default' - *please upgrade PLCAPI*")
        node_hrn='default   # Failed to read hrn from GetSlivers, please upgrade PLCAPI'

    for sliver in data['slivers']:
        name=sliver['name']
        sliver_pub_key_dir=os.path.join("/home", name, ".ssh/")
        sliver_private_key=os.path.join(sliver_pub_key_dir, "id_rsa")
        for chunk in sliver['attributes']:
            if chunk['tagname']=='omf_control':
                # scan all versions of omf-resctl
                etc_path="/vservers/%s/etc/"%name
                pattern = etc_path + "omf-resctl-*/omf-resctl.yaml.in"
                templates = glob.glob (pattern)
                if not templates:
                    logger.log("WARNING: omf_resctl plugin, no template found for slice %s using pattern %s"\
                                   %(name,pattern))
                    continue
                for template in templates:
                    # remove the .in extension
                    yaml=template[:-3]
                    # figure service name as subdir under etc/
                    service_name=os.path.split(template.replace(etc_path,''))[0]
                    # read template and replace
                    template_contents=file(template).read()
                    yaml_contents=template_contents\
                        .replace('@XMPP_SERVER@',xmpp_server)\
                        .replace('@NODE_HRN@',node_hrn)\
                        .replace('@SLICE_NAME@',name)\
                        .replace('@SLIVER_PRIVATE_KEY@',sliver_private_key)\
                        .replace('@SLIVER_PUB_KEY_DIR@',sliver_pub_key_dir)
                    changes=tools.replace_file_with_string(yaml,yaml_contents)
                    logger.log("yaml_contents length=%d, changes=%r"%(len(yaml_contents),changes))
                    if changes:
                        sp=subprocess.Popen(['vserver',name,'exec','service',service_name,'restart'],
                                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                        (output,retcod)=sp.communicate()
                        logger.log("omf_resctl: %s: restarted resource controller (retcod=%r)"%(name,retcod))
                        logger.log("omf_resctl: got output\n%s"%output)
                    else:
                        logger.log("omf_resctl: %s: omf_control'ed sliver has no change" % name)
