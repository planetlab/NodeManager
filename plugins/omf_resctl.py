#
# $Id$
# $URL$
#
# NodeManager plugin - first step of handling omf_controlled slices

"""
Overwrites the 'resctl' tag of slivers controlled by OMF so sm.py does the right thing
"""

import subprocess

import tools
import logger

priority = 11

### xxx this should not be version-dependent
service_name='omf-resctl-5.3'

def start(options, conf):
    logger.log("omf_resctl: plugin starting up...")

def GetSlivers(data, conf = None, plc = None):
    if 'accounts' not in data: 
        logger.log_missing_data("omf_resctl.GetSlivers",'accounts')
        return

    try:
        xmpp_server=data['xmpp']['server']
    except:
        # disabled feature - bailing out
        # xxx might need to clean up more deeply..
        return

    for sliver in data['slivers']:
        name=sliver['name']
        for chunk in sliver['attributes']:
            if chunk['tagname']=='omf_control':
                # filenames
                yaml="/vservers/%s/etc/omf-resctl/omf-resctl.yaml"%name
                template="%s.in"%yaml
                # read template and replace
                template=file(template).read()
                yaml_contents=template\
                    .replace('@XMPP_SERVER@',xmpp_server)\
                    .replace('@NODE_HRN@','default')\
                    .replace('@SLICE_NAME@',name)
                changes=tools.replace_file_with_string(yaml,yaml_contents)
                if changes:
                    sp=subprocess.Popen(['vserver',name,'exec','service',service_name,'restart'],
                                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                    (output,retcod)=sp.communicate()
                    logger.log("omf_resctl: %s: restarted resource controller (retcod=%r)"%(name,retcod))
                    logger.log("omf_resctl: got output\n%s"%output)
                else:
                    logger.log("omf_resctl: %s: omf_control'ed sliver has no change" % name)
