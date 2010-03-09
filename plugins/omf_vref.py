#
# $Id$
# $URL$
#
# NodeManager plugin - first step of handling omf_controlled slices

"""
Overwrites the 'vref' tag of slivers controlled by OMF so sm.py does the right thing
Needs to be done the 'sm' module kicks in
"""

import logger

# do this early, before step 10
priority = 4

def start(options, conf):
    logger.log("omf_vref: plugin starting up...")

def GetSlivers(data, conf = None, plc = None):
    if 'accounts' not in data: 
        logger.log_missing_data("omf_vref.GetSlivers",'accounts')
        return

    for sliver in data['slivers']:
        name=sliver['name']
        for chunk in sliver['attributes']:
            if chunk['tagname']=='omf_control':
                sliver['vref']='omf'
                logger.log('omf_vref: %s now has vref==omf' % name)
