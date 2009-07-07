# $Id$
# $URL$

"""Codemux configurator.  Monitors slice attributes and configures CoDemux to mux port 80 based on HOST field in HTTP request.  Forwards to localhost port belonging to configured slice."""

import logger
import os
import vserver
from sets import Set
from config import Config

CODEMUXCONF="/etc/codemux/codemux.conf"

def start(options, conf):
    logger.log("codemux plugin starting up...")

def GetSlivers(plc, data, config):
    """
    For each sliver with the codemux attribute, parse out "host,port" 
    and make entry in conf.  Restart service after.
    """
    if 'OVERRIDES' in dir(config):
        if config.OVERRIDES.get('codemux') == '-1':
            logger.log("codemux:  Disabled", 2)
            stopService()
            return

    logger.log("codemux:  Starting.", 2)
    # slices already in conf
    slicesinconf = parseConf()
    # slices that need to be written to the conf
    codemuxslices = {}
    
    # XXX Hack for planetflow
    if slicesinconf.has_key("root"): _writeconf = False
    else: _writeconf = True

    # Parse attributes and update dict of scripts
    for sliver in data['slivers']:
        for attribute in sliver['attributes']:
            if attribute['tagname'] == 'codemux':
                # add to conf.  Attribute is [host, port]
                params = {'host': attribute['value'].split(",")[0], 
                          'port': attribute['value'].split(",")[1]}
                try:
                    # Check to see if sliver is running.  If not, continue
                    if vserver.VServer(sliver['name']).is_running():
                        # Check if new or needs updating
                        if (sliver['name'] not in slicesinconf.keys()) \
                        or (params not in slicesinconf.get(sliver['name'], [])):
                            logger.log("codemux:  Updaiting slice %s using %s" % \
                                (sliver['name'], params['host']))
                            #  Toggle write.
                            _writeconf = True
                        # Add to dict of codemuxslices.  Make list to support more than one
                        # codemuxed host per slice.
                        codemuxslices.setdefault(sliver['name'],[])
                        codemuxslices[sliver['name']].append(params)
                except:
                    logger.log("codemux:  sliver %s not running yet.  Deferring."\
                                % sliver['name'])
                    pass

    # Remove slices from conf that no longer have the attribute
    for deadslice in Set(slicesinconf.keys()) - Set(codemuxslices.keys()):
        # XXX Hack for root slice
        if deadslice != "root": 
            logger.log("codemux:  Removing %s" % deadslice)
            _writeconf = True 

    if _writeconf:  writeConf(sortDomains(codemuxslices))    
    # ensure the service is running
    startService()


def writeConf(slivers, conf = CODEMUXCONF):
    '''Write conf with default entry up top. Elements in [] should have lower order domain names first. Restart service.'''
    f = open(conf, "w")
    # This needs to be the first entry...
    try: 
        f.write("* root 1080 %s\n" % Config().PLC_PLANETFLOW_HOST)
    except AttributeError: 
        logger.log("codemux:  Can't find PLC_CONFIG_HOST in config. Using PLC_API_HOST")
        f.write("* root 1080 %s\n" % Config().PLC_API_HOST)
    # Sort items for like domains
    for mapping in slivers:
        for (host, params) in mapping.iteritems():
            if params['slice'] == "root":  continue
            f.write("%s %s %s\n" % (host, params['slice'], params['port']))
    f.truncate()
    f.close()
    try:  restartService()
    except:  logger.log_exc()


def sortDomains(slivers):
    '''Given a dict of {slice: {domainname, port}}, return array of slivers with lower order domains first'''
    dnames = {} # {host: slice}
    for (slice, params) in slivers.iteritems():
        for mapping in params:
            dnames[mapping['host']] = {"slice":slice, "port": mapping['port']}
    hosts = dnames.keys()
    # sort by length
    hosts.sort(key=str.__len__)
    # longer first
    hosts.reverse()
    # make list of slivers
    sortedslices = []
    for host in hosts: sortedslices.append({host: dnames[host]})
    
    return sortedslices

        
def parseConf(conf = CODEMUXCONF):
    '''Parse the CODEMUXCONF and return dict of slices in conf. {slice: (host,port)}'''
    slicesinconf = {} # default
    try: 
        f = open(conf)
        for line in f.readlines():
            if line.startswith("#") \
            or (len(line.split()) > 4) \
            or (len(line.split()) < 3):
                continue
            (host, slice, port) = line.split()[:3]
            logger.log("codemux:  found %s in conf" % slice, 2)
            slicesinconf.setdefault(slice, [])
            slicesinconf[slice].append({"host": host, "port": port})
        f.close()
    except IOError: logger.log_exc()
    return slicesinconf


def isRunning():
    if len(os.popen("pidof codemux").readline().rstrip("\n")) > 0:
        return True
    else:
        return False


def restartService():
    logger.log("codemux:  Restarting codemux service")
    if isRunning():
        logger.log_call("/etc/init.d/codemux","condrestart")
    else:
        logger.log_call("/etc/init.d/codemux","restart")


def startService():
    if not isRunning():
        logger.log("codemux:  Starting codemux service")
        logger.log_call("/etc/init.d/codemux", "start")


def stopService():
    if isRunning():
        logger.log("codemux:  Stopping codemux service")
        logger.log_call("/etc/init.d/codemux", "stop")
