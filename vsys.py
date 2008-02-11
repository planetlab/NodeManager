# $Id$
# $URL$

"""vsys configurator.  Maintains ACLs and script pipes inside vservers based on slice attributes."""

import logger
import os
from sets import Set

VSYSCONF="/etc/vsys.conf"
VSYSBKEND="/vsys"

def start(options, config):
    pass


def GetSlivers(data):
    """For each sliver with the vsys attribute, set the script ACL, create the vsys directory in the slice, and restart vsys."""
    # Touch ACLs and create dict of available
    scripts = dict.fromkeys(touchAcls(),[])
    # slices that need to be written to the conf
    slices = []
    # Parse attributes and update dict of scripts
    for sliver in data['slivers']:
        for attribute in sliver['attributes']:
            if attribute['name'] == 'vsys':
                # add to conf
                slices.append(sliver['name'])
                # As the name implies, when we find an attribute, we
                createVsysDir(sliver['name'])
                # add it to our list of slivers that need vsys
                if attribute['value'] in scripts.keys():
                    scripts[attribute['value']].append(slice['name'])
 
    # Write the conf
    writeConf(slices, parseConf())
    # Write out the ACLs
    if writeAcls(scripts, parseAcls()): 
        logger.log("vsys: restarting vsys service")
        os.system("/etc/init.d/vsys restart")


def createVsysDir(sliver):
    '''Create /vsys directory in slice.  Update vsys conf file.'''
    try: os.makedirs("/vservers/%s/vsys" % sliver['name'])
    except OSError: pass


def touchAcls():
    '''Creates empty acl files for scripts.  
    To be ran in case of new scripts that appear in the backend.
    Returns list of available scripts.'''
    acls = []
    scripts = []
    for (root, dirs, files) in os.walk(VSYSBKEND):
        for file in files:
            if file.endswith(".acl"):
                acls.append(file.rstrip(".acl"))
            else:
                scripts.append(file)
    print scripts
    for new in (Set(scripts) - Set(acls)):
        logger.log("vsys:  Found new script %s.  Writing empty acl." % new)
        f = open("%s/%s.acl" %(VSYSBKEND, new), "w")
        f.write("\n")
        f.close()
    
    return scripts


def writeAcls(currentscripts, oldscripts):
    '''Creates .acl files for script in the script repo.'''
    # Check each oldscript entry to see if we need to modify
    _restartvsys = False
    for (acl, oldslivers) in oldscripts.iteritems():
        if (len(oldslivers) != len(currentscripts[acl])) or \
        (len(Set(oldslivers) - Set(currentscripts[acl])) != 0):
            _restartvsys = True
            logger.log("vsys: Updating %s.acl w/ slices %s" % (acl, currentscripts[acl]))
            f = open("%s/%s.acl" % (VSYSBKEND, acl), "w")
            for slice in currentscripts[acl]: f.write("%s\n" % slice)
            f.close()
    # Trigger a restart
    return _restartvsys


def parseAcls():
    '''Parse the frontend script acls.  Return {script: [slices]} in conf.'''
    # make a dict of what slices are in what acls.
    scriptacls = {}
    for (root, dirs, files) in os.walk(VSYSBKEND):
        for file in files:
            if file.endswith(".acl"):
                f = open(root+"/"+file,"r+")
                scriptname = file.rstrip(".acl")
                scriptacls[scriptname] = []
                for slice in f.readlines():  
                    scriptacls[scriptname].append(slice.rstrip())
                f.close()
    # return what scripts are configured for which slices.
    return scriptacls


def writeConf(slivers, oldslivers):
    # Check if this is needed
    if (len(slivers) != len(oldslivers)) or \
    (len(Set(oldslivers) - Set(slivers)) != 0):
        logger.log("vsys:  Updating %s" % VSYSCONF)
        f = open(VSYSCONF,"w")
        for sliver in slivers:
            f.write("/vservers/%(name)s/vsys %(name)s\n" % {"name": sliver})
        f.truncate()
        f.close()

def parseConf():
    '''Parse the vsys conf and return list of slices in conf.'''
    scriptacls = {}
    slicesinconf = []
    try: 
        f = open(VSYSCONF)
        for line in f.readlines():
            (slice, path) = line.split()
            slicesinconf.append(slice)
        f.close()
    except: logger.log_exc()
    return slicesinconf


