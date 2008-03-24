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
    # slices already in conf
    slicesinconf = parseConf()
    # slices that need to be written to the conf
    codemuxslices = {}
    _writeconf = False
    # Parse attributes and update dict of scripts
    for sliver in data['slivers']:
        for attribute in sliver['attributes']:
            if attribute['name'] == 'codemux':
                # add to conf.  Attribute is [host, port]
                [host, port] = attribute['value'].split()
                try:
                    # Check to see if sliver is running.  If not, continue
                    if vserver.VServer(sliver['name']).is_running():
                        # Check for new
                        if sliver['name'] not in slicesinconf.keys():
                            logger.log("codemux:  New slice %s using %s" % \
                                (sliver['name'], host))
                            codemuxslices[sliver['name']] = {'host': host, 'port': port}
                            _writeconf = True
                        # Check old slivers for changes
                        else:
                            sliverinconf = slicesinconf[sliver['name']]
                            if (sliverinconf['host'] != host) or \
                                (sliverinconf['port'] != port):
                                logger.log("codemux:  Updating slice %s" % sliver['name'])
                                _writeconf = True
                                codemuxslices[sliver['name']] = {'host': host, 'port': port}
                except:
                    logger.log("codemux:  sliver %s not running yet.  Deferring."\
                                % sliver['name'])
                    pass

    if _writeconf:  writeConf(codemuxslices)

def writeConf(slivers, conf = CODEMUXCONF):
    '''Write conf with default entry up top. Restart service.'''
    f.open(conf)
    f.write("* root 1080")
    for (host, slice, port) in slivers.iteritems():
        f.write("%s %s %s" % [host, slice, port])
    f.truncate()
    f.close()
    logger.log("codemux: restarting codemux service")
    os.system("/etc/init.d/codemux restart")


def parseConf(conf = CODEMUXCONF):
    '''Parse the CODEMUXCONF and return dict of slices in conf. {slice: (host,port)}'''
    slicesinconf = {} 
    try: 
        f = open(conf)
        for line in f.readlines():
            if line.startswith("#") or (len(line.split()) != 3):  
                continue
            (host, slice, port) = line.split()[:3]
            slicesinconf[slice] = {"host": host, "port": port}
        f.close()
    except: logger.log_exc()
    return slicesinconf


