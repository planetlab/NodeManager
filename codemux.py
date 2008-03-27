# $Id$
# $URL$

"""Codemux configurator.  Monitors slice attributes and configures CoDemux to mux port 80 based on HOST field in HTTP request.  Forwards to localhost port belonging to configured slice."""

import logger
import os
import vserver
from sets import Set

CODEMUXCONF="/etc/codemux/codemux.conf"

def start(options, config):
    pass


def GetSlivers(data):
    """For each sliver with the codemux attribute, parse out "host,port" and make entry in conf.  Restart service after."""
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
            if attribute['name'] == 'codemux':
                # add to conf.  Attribute is [host, port]
                [host, port] = attribute['value'].split(",")
                try:
                    # Check to see if sliver is running.  If not, continue
                    if vserver.VServer(sliver['name']).is_running():
                        # Add to dict of codemuxslices 
                        codemuxslices[sliver['name']] = {'host': host, 'port': port}
                        # Check if new
                        if sliver['name'] not in slicesinconf.keys():
                            logger.log("codemux:  New slice %s using %s" % \
                                (sliver['name'], host))
                            #  Toggle write.
                            _writeconf = True
                        # Check old slivers for changes
                        else:
                            # Get info about slice in conf
                            sliverinconf = slicesinconf[sliver['name']]
                            # Check values for changes.
                            if (sliverinconf['host'] != host) or \
                                (sliverinconf['port'] != port):
                                logger.log("codemux:  Updating slice %s" % sliver['name'])
                                # use updated values
                                codemuxslices[sliver['name']] = {'host': host, 'port': port}
                                #  Toggle write.
                                _writeconf = True
                except:
                    logger.log("codemux:  sliver %s not running yet.  Deferring."\
                                % sliver['name'])

                    logger.log_exc(name = "codemux")
                    pass

    # Remove slices from conf that no longer have the attribute
    for deadslice in Set(slicesinconf.keys()) - Set(codemuxslices.keys()):
        # XXX Hack for root slice
        if deadslice != "root": 
            logger.log("codemux:  Removing %s" % deadslice)
            _writeconf = True 

    if _writeconf:  writeConf(codemuxslices)

def writeConf(slivers, conf = CODEMUXCONF):
    '''Write conf with default entry up top.  Write lower order domain names first. Restart service.'''
    f = open(conf, "w")
    # This needs to be the first entry...
    f.write("* root 1080\n")
    # Sort items for like domains
    for slice in sortDomains(slivers):
        if slice == "root":  continue
        f.write("%s %s %s\n" % (slivers[slice]['host'], slice, slivers[slice]['port']))
    f.truncate()
    f.close()
    try:  restartService()
    except:  logger.log_exc()

def sortDomains(slivers):
    '''Given a dict of {slice: {domainname, port}}, return array of slivers with lower order domains first'''
    dnames = {} # {host: slice}
    for (slice,params) in slivers.iteritems():
        dnames[params['host']] = slice
    hosts = dnames.keys()
    # sort by length
    hosts.sort(key=str.__len__)
    # longer first
    hosts.reverse()
    # make list of slivers
    sortedslices = []
    for host in hosts: sortedslices.append(dnames[host])
    
    return sortedslices
        
def parseConf(conf = CODEMUXCONF):
    '''Parse the CODEMUXCONF and return dict of slices in conf. {slice: (host,port)}'''
    slicesinconf = {} # default
    try: 
        f = open(conf)
        for line in f.readlines():
            if line.startswith("#") or (len(line.split()) != 3):
                continue
            (host, slice, port) = line.split()[:3]
            logger.log("codemux:  found %s in conf" % slice, 2)
            slicesinconf[slice] = {"host": host, "port": port}
        f.close()
    except IOError: logger.log_exc()
    return slicesinconf

def restartService():
    logger.log("codemux:  Restarting codemux service")
    os.system("/etc/init.d/codemux stop")
    f = os.popen("/sbin/pidof codemux")
    tmp = f.readlines()
    f.close()
    if len(tmp) > 0: 
        pids = tmp[0].rstrip("\n").split()
        for pid in pids:
            logger.log("codemux:  Killing stalled pid %s" % pid, 2)
            os.kill(pid, 9)
    os.system("/etc/init.d/codemux start")
