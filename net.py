# $Id$
# $URL$

"""network configuration"""

# system provided modules
import os, string, time, socket

# PlanetLab system modules
import sioc, plnet

# local modules
import bwlimit, logger, iptables, tools

# we can't do anything without a network
priority=1

dev_default = tools.get_default_if()

def start(options, conf):
    logger.log("net: plugin starting up...")

def GetSlivers(data, config, plc):
    logger.verbose("net: GetSlivers called.")
    if not 'interfaces' in data:
        logger.log_missing_data('net.GetSlivers','interfaces')
        return
    plnet.InitInterfaces(logger, plc, data)
    if 'OVERRIDES' in dir(config):
        if config.OVERRIDES.get('net_max_rate') == '-1':
            logger.log("net: Slice and node BW Limits disabled.")
            if len(bwlimit.tc("class show dev %s" % dev_default)):
                logger.verbose("net: *** DISABLING NODE BW LIMITS ***")
                bwlimit.stop()
        else:
            InitNodeLimit(data)
            InitI2(plc, data)
    else:
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

    for interface in data['interfaces']:
        # Get interface name preferably from MAC address, falling
        # back on IP address.
        hwaddr=interface['mac']
        if hwaddr <> None: hwaddr=hwaddr.lower()
        if hwaddr in macs:
            dev = macs[interface['mac']]
        elif interface['ip'] in ips:
            dev = ips[interface['ip']]
        else:
            logger.log('net: %s: no such interface with address %s/%s' % (interface['hostname'], interface['ip'], interface['mac']))
            continue

        # Get current node cap
        try:
            old_bwlimit = bwlimit.get_bwcap(dev)
        except:
            old_bwlimit = None

        # Get desired node cap
        if interface['bwlimit'] is None or interface['bwlimit'] < 0:
            new_bwlimit = bwlimit.bwmax
        else:
            new_bwlimit = interface['bwlimit']

        if old_bwlimit != new_bwlimit:
            # Reinitialize bandwidth limits
            bwlimit.init(dev, new_bwlimit)

            # XXX This should trigger an rspec refresh in case
            # some previously invalid sliver bwlimit is now valid
            # again, or vice-versa.

def InitI2(plc, data):
    if not 'groups' in data: return

    if "Internet2" in data['groups']:
        logger.log("net: This is an Internet2 node.  Setting rules.")
        i2nodes = []
        i2nodeids = plc.GetNodeGroups(["Internet2"])[0]['node_ids']
        for node in plc.GetInterfaces({"node_id": i2nodeids}, ["ip"]):
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

    # query running network interfaces
    devs = sioc.gifconf()
    ips = dict(zip(devs.values(), devs.keys()))
    macs = {}
    for dev in devs:
        macs[sioc.gifhwaddr(dev).lower()] = dev

    ipt = iptables.IPTables()
    for interface in data['interfaces']:
        # Get interface name preferably from MAC address, falling
        # back on IP address.
        hwaddr=interface['mac']
        if hwaddr <> None: hwaddr=hwaddr.lower()
        if hwaddr in macs:
            dev = macs[interface['mac']]
        elif interface['ip'] in ips:
            dev = ips[interface['ip']]
        else:
            logger.log('net: %s: no such interface with address %s/%s' % (interface['hostname'], interface['ip'], interface['mac']))
            continue

        try:
            settings = plc.GetInterfaceTags({'interface_tag_id': interface['interface_tag_ids']})
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

def start(options, config):
    pass
