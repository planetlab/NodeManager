# $Id$
# $URL$
#
# NodeManager plugin - first step of handling omf_controlled slices

"""
Overwrites the 'resctl' tag of slivers controlled by OMF so sm.py does the right thing
"""

import logger

priority = 45
# this instructs nodemanager that we want to use the latest known data when the plc link is down
persistent_data = True

def start(options, conf):
    logger.log("reservation: plugin starting up...")

def GetSlivers(data, conf = None, plc = None):

    if 'reservation_policy' not in data: 
        logger.log_missing_data("reservation.GetSlivers",'reservation_policy')
        return
    reservation_policy=data['reservation_policy']

    if 'leases' not in data: 
        logger.log_missing_data("reservation.GetSlivers",'leases')
        return

    if reservation_policy in ['lease_or_idle','lease_or_shared']:
        logger.log( 'reservation.GetSlivers - scaffolding...')
    elif reservation_policy == 'none':
        return
    else:
        logger.log("reservation: ignoring -- unexpected value for reservation_policy %r"%reservation_policy)
        return
