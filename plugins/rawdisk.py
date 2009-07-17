#!/usr/bin/python -tt
# vim:set ts=4 sw=4 expandtab:
# NodeManager plugin to support mapping unused raw disks into a slice
# that has the rawdisk sliver tag

"""
Raw disk support for NodeManager.

Copies all unused devices into slices with the rawdisk attribute set.
"""

import errno
import os
import time
import re

import logger
import tools

def start(options, config):
    logger.log("rawdisk plugin starting up...")

def get_unused_devices():
    devices = []
    if os.path.exists("/dev/mapper/planetlab-rawdisk"):
        devices.append("/dev/mapper/planetlab-rawdisk")
    # Figure out which partitions are part of the VG
    in_vg = []
    for i in os.listdir("/sys/block"):
        if not i.startswith("dm-"):
            continue
        in_vg.extend(os.listdir("/sys/block/%s/slaves" % i))
    # Read the list of partitions
    partitions = file("/proc/partitions", "r")
    pat = re.compile("\s+")
    while True:
        buf = partitions.readline()
        if buf == "":
            break
        buf = buf.strip()
        fields = re.split(pat, buf)
        print fields
        dev = fields[-1]
        if not dev.startswith("dm-") and dev.endswith("1") and dev not in in_vg:
            devices.append("/dev/%s" % dev)
    partitions.close()
    return devices

def GetSlivers(plc, data, conf):
    if 'slivers' not in data: 
        logger.log("sliverauth: getslivers data lack's sliver information. IGNORING!")
        return

    devices = get_unused_devices()
    for sliver in data['slivers']:
        for attribute in sliver['attributes']:
	    name = attribute.get('tagname',attribute.get('name',''))
            if name == 'rawdisk':
                for i in devices:
                    st = os.stat(i)
                    path = "/vservers/%s%s" % (sliver['name'], i)
                    if os.path.exists(path):
                        # should check whether its the proper type of device
                        continue
                    
                    logger.log("Copying %s to %s" % (i, path))
                    try:
                        if os.path.exists(path):
                            os.unlink(path)
                    except:
                        pass
                    os.mknod(path, st.st_mode, st.st_rdev)
