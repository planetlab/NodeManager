#
# $Id$
#

"""network configuration"""

# system provided modules
import os, string, time, socket

# PlanetLab system modules
import sioc, plnet

# local modules
import bwlimit, logger, iptables

def GetSlivers(plc, data):
    InitInterfaces(plc, data)
    InitNodeLimit(data)
    InitI2(plc, data)
    InitNAT(plc, data)

def InitNodeLimit(data):
    if not 'networks' in data: return

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
        hwaddr=network['mac']
        if hwaddr <> None: hwaddr=hwaddr.lower()
        if hwaddr in macs:
            dev = macs[network['mac']]
        elif network['ip'] in ips:
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
    if not 'groups' in data: return

    if "Internet2" in data['groups']:
        logger.log("This is an Internet2 node.  Setting rules.")
        i2nodes = []
        i2nodeids = plc.GetNodeGroups(["Internet2"])[0]['node_ids']
        for node in plc.GetNodeNetworks({"node_id": i2nodeids}, ["ip"]):
            # Get the IPs
            i2nodes.append(node['ip'])
        # this will create the set if it doesn't already exist
        # and add IPs that don't exist in the set rather than
        # just recreateing the set.
        bwlimit.exempt_init('Internet2', i2nodes)
        
        # set the iptables classification rule if it doesnt exist.
        cmd = '-A POSTROUTING -m set --set Internet2 dst -j CLASSIFY --set-class 0001:2000 --add-mark'
        rules = []
        ipt = os.popen("/sbin/iptables-save")
        for line in ipt.readlines(): rules.append(line.strip(" \n"))
        ipt.close()
        if cmd not in rules:
            logger.verbose("net:  Adding iptables rule for Internet2")
            os.popen("/sbin/iptables -t mangle " + cmd)

def InitNAT(plc, data):
    if not 'networks' in data: return
    
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
        hwaddr=network['mac']
        if hwaddr <> None: hwaddr=hwaddr.lower()
        if hwaddr in macs:
            dev = macs[network['mac']]
        elif network['ip'] in ips:
            dev = ips[network['ip']]
        else:
            logger.log('%s: no such interface with address %s/%s' % (network['hostname'], network['ip'], network['mac']))
            continue

        try:
            settings = plc.GetNodeNetworkSettings({'nodenetwork_setting_id': network['nodenetwork_setting_ids']})
        except:
            continue

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

def InitInterfaces(plc, data):
    if not 'networks' in data: return
    plnet.InitInterfaces(logger, plc, data)

def start(options, config):
    pass
