# $Id$
# $URL$

"""vsys configurator.  Maintains ACLs and script pipes inside vservers based on slice attributes."""

import logger
import os


def start(options, config):
    pass

def GetSlivers(data):
    """For each sliver with the vsys attribute, set the script ACL, create the vsys directory in the slice, and restart vsys."""
    confedSlivers = parseConf("/etc/vsys.conf")
    newSlivers = []
    for sliver in data['slivers']:
        for attribute in sliver['attributes']:
            if attribute['name'] == 'vsys':
                # As the name implies, when we find an attribute, we
                createVsysDir(sliver)
                if sliver['name'] not in confedSlivers: newSlivers.append(sliver['name'])

    writeConf(confedSlivers + newSlivers, "/etc/vsys.conf")

def secureScripts():

def createVsysDir(sliver):
    '''Create /vsys directory in slice.  Update vsys conf file.'''
    try: os.makedirs("/vservers/%s/vsys" % sliver['name'])
    except OSError: pass


def parseConf(file):
    '''Parse the vserver conf.  Return [slices] in conf.'''
    slices = []
    f = open(file)
    for line in f.readlines():
        (slice, path) = line.split()
        slices.append(slice)
    f.close()
    return slices


def writeConf(slivers, file):
    f = open(file,"w")
    for sliver in slivers:
        f.write("/vservers/%(name)s/vsys %(name)s\n" % {"name": sliver})
    f.truncate()
    f.close()
