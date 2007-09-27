
#
#
"""network configuration"""

import sioc
import bwlimit
import logger
import string

def GetSlivers(plc, data):
    InitNodeLimit(data)
    InitI2(plc, data)

def InitNodeLimit(data):
    # query running network interfaces
    devs = sioc.gifconf()
    ips = dict(zip(devs.values(), devs.keys()))
    macs = {}
    for dev in devs:
        macs[sioc.gifhwaddr(dev).lower()] = dev

    # XXX Exempt Internet2 destinations from node bwlimits
    # bwlimit.exempt_init('Internet2', internet2_ips)
    for network in data['networks']:
        # Get interface name preferably from MAC address, falling
        # back on IP address.
        if macs.has_key(network['mac']):
            dev = macs[network['mac'].lower()]
        elif ips.has_key(network['ip']):
            dev = ips[network['ip']]
        else:
            logger.log('%s: no such interface with address %s/%s' % (network['hostname'], network['ip'], network['mac']))
            continue

        # Get current node cap
        try:
            old_bwlimit = bwlimit.get_bwcap(dev)
        except:
            old_bwlimit = None

        # Get desired node cap
        if network['bwlimit'] is None or network['bwlimit'] < 0:
            new_bwlimit = bwlimit.bwmax
        else:
            new_bwlimit = network['bwlimit']

        if old_bwlimit != new_bwlimit:
            # Reinitialize bandwidth limits
            bwlimit.init(dev, new_bwlimit)

            # XXX This should trigger an rspec refresh in case
            # some previously invalid sliver bwlimit is now valid
            # again, or vice-versa.

def InitI2(plc, data):
    if "Internet2" in data['groups']:
        logger.log("This is an Internet2 node.  Setting rules.")
        i2nodes = []
        i2nodeids = plc.GetNodeGroups(["Internet2"])[0]['node_ids']
        for node in plc.GetNodeNetworks({"node_id": i2nodeids}, ["ip"]):
            i2nodes.append(node['ip'])
        bwlimit.exempt_init('Internet2', i2nodes)

def start(options, config):
    pass
