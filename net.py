#
#
"""network configuration"""

import sioc
import bwlimit
import logger
import string
import iptables

def GetSlivers(plc, data):
    InitNodeLimit(data)
    InitI2(plc, data)
    InitNAT(plc, data)

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
        for node in plc.GetInterfaces({"node_id": i2nodeids}, ["ip"]):
            i2nodes.append(node['ip'])
        bwlimit.exempt_init('Internet2', i2nodes)

def InitNAT(plc, data):
    # query running network interfaces
    devs = sioc.gifconf()
    ips = dict(zip(devs.values(), devs.keys()))
    macs = {}
    for dev in devs:
        macs[sioc.gifhwaddr(dev).lower()] = dev

    ipt = iptables.IPTables()
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

        try:
            settings = plc.GetInterfaceSettings({'interface_setting_id': network['interface_setting_ids']})
        except:
            continue
        # XXX arbitrary names
        for setting in settings:
            if setting['category'].upper() != 'FIREWALL':
                continue
            if setting['name'].upper() == 'EXTERNAL':
                # Enable NAT for this interface
                ipt.add_ext(dev)
            elif setting['name'].upper() == 'INTERNAL':
                ipt.add_int(dev)
            elif setting['name'].upper() == 'PF': # XXX Uglier code is hard to find...
                for pf in setting['value'].split("\n"):
                    fields = {}
                    for field in pf.split(","):
                        (key, val) = field.split("=", 2)
                        fields[key] = val
                    if 'new_dport' not in fields:
                        fields['new_dport'] = fields['dport']
                    if 'source' not in fields:
                        fields['source'] = "0.0.0.0/0"
                    ipt.add_pf(fields)
    ipt.commit()

def start(options, config):
    pass
