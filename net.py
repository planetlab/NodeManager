"""network configuration"""

import sioc
import bwlimit
import logger

def GetSlivers(data):
    # query running network interfaces
    devs = sioc.gifconf()
    ips = dict(zip(devs.values(), devs.keys()))
    macs = {}
    for dev in devs:
        macs[sioc.gifhwaddr(dev).lower()] = dev

    # XXX Exempt Internet2 destinations from node bwlimits
    # bwlimit.exempt_init('Internet2', internet2_ips)

    for d in data:
        for network in d['networks']:
            # Get interface name preferably from MAC address, falling
            # back on IP address.
            if macs.has_key(network['mac'].lower()):
                dev = macs[network['mac'].lower()]
            elif ips.has_key(network['ip']):
                dev = ips[network['ip']]
            else:
                logger.log('%s: no such interface with address %s/%s' % (self.name, network['ip'], network['mac']))
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

def start(options, config):
    pass
