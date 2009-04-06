#!/usr/bin/python

#
# Useful information can be found at https://svn.planet-lab.org/wiki/NodeManager
#

# Faiyaz Ahmed <faiyaza at cs dot princeton dot edu>
# Copyright (C) 2008 The Trustees of Princeton University


"""Node Manager"""

import optparse
import time
import xmlrpclib
import socket
import os
import sys
import resource

import logger
import tools

from config import Config
from plcapi import PLCAPI 
import random
import net

id="$Id$"
savedargv = sys.argv[:]

known_modules=['conf_files', 'sm', 'bwmon', 'vsys', 'codemux']

parser = optparse.OptionParser()
parser.add_option('-d', '--daemon', action='store_true', dest='daemon', default=False, help='run daemonized')
parser.add_option('-s', '--startup', action='store_true', dest='startup', default=False, help='run all sliver startup scripts')
parser.add_option('-f', '--config', action='store', dest='config', default='/etc/planetlab/plc_config', help='PLC configuration file')
parser.add_option('-k', '--session', action='store', dest='session', default='/etc/planetlab/session', help='API session key (or file)')
parser.add_option('-p', '--period', action='store', dest='period', default=600, help='Polling interval (sec)')
parser.add_option('-r', '--random', action='store', dest='random', default=301, help='Range for additional random polling interval (sec)')
parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False, help='more verbose log')
parser.add_option('-P', '--path', action='store', dest='path', default='/usr/share/NodeManager/plugins', help='Path to plugins directory')
parser.add_option('-m', '--module', action='store', dest='module', default='', help='run a single module among '+' '.join(known_modules))
(options, args) = parser.parse_args()

# Deal with plugins directory
if os.path.exists(options.path):
    sys.path.append(options.path)
    known_modules += [i[:-3] for i in os.listdir(options.path) if i.endswith(".py") and (i[:-3] not in known_modules)]

modules = []

def GetSlivers(plc, config):
    '''Run call backs defined in modules'''
    try: 
        logger.log("Syncing w/ PLC")
        data = plc.GetSlivers()
        getPLCDefaults(data, config)
        if (options.verbose): logger.log_slivers(data)
    except: 
        logger.log_exc()
        #  XXX So some modules can at least boostrap.
        logger.log("nm:  Can't contact PLC to GetSlivers().  Continuing.")
        data = {}
    # Set i2 ip list for nodes in I2 nodegroup
    # and init network interfaces (unless overridden)
    try: net.GetSlivers(plc, data, config) # TODO - num of args needs to be unified across mods.
    except: logger.log_exc()
    #  All other callback modules
    for module in modules:
        try:        
            callback = getattr(module, 'GetSlivers')
            callback(data)
        except: logger.log_exc()


def getPLCDefaults(data, config):
    '''
    Get PLC wide defaults from _default system slice.  Adds them to config class.
    '''
    for slice in data.get('slivers'): 
        if slice['name'] == config.PLC_SLICE_PREFIX+"_default":
            attr_dict = {}
            for attr in slice.get('attributes'): attr_dict[attr['name']] = attr['value'] 
            if len(attr_dict):
                logger.verbose("Found default slice overrides.\n %s" % attr_dict)
                config.OVERRIDES = attr_dict
            return 
    if 'OVERRIDES' in dir(config): del config.OVERRIDES


def run():
    try:
        if options.daemon: tools.daemon()

        # set log level
        if (options.verbose):
            logger.set_level(logger.LOG_VERBOSE)

        # Load /etc/planetlab/plc_config
        config = Config(options.config)

        try:
            other_pid = tools.pid_file()
            if other_pid != None:
                print """There might be another instance of the node manager running as pid %d.  If this is not the case, please remove the pid file %s""" % (other_pid, tools.PID_FILE)
                return
        except OSError, err:
            print "Warning while writing PID file:", err

        # Load and start modules
        if options.module:
            assert options.module in known_modules
            running_modules=[options.module]
            logger.verbose('Running single module %s'%options.module)
        else:
            running_modules=known_modules
        for module in running_modules:
            try:
                m = __import__(module)
                m.start(options, config)
                modules.append(m)
            except ImportError, err:
                print "Warning while loading module %s:" % module, err

        # Load /etc/planetlab/session
        if os.path.exists(options.session):
            session = file(options.session).read().strip()
        else:
            session = None

        # Initialize XML-RPC client
        iperiod=int(options.period)
        irandom=int(options.random)
        plc = PLCAPI(config.plc_api_uri, config.cacert, session, timeout=iperiod/2)

        while True:
        # Main NM Loop
            logger.verbose('mainloop - nm:getSlivers - period=%d random=%d'%(iperiod,irandom))
            GetSlivers(plc, config)
            delay=iperiod + random.randrange(0,irandom)
            logger.verbose('mainloop - sleeping for %d s'%delay)
            time.sleep(delay)
    except: logger.log_exc()


if __name__ == '__main__':
    logger.log("Entering nm.py "+id)
    stacklim = 512*1024  # 0.5 MiB
    curlim = resource.getrlimit(resource.RLIMIT_STACK)[0]  # soft limit
    if curlim > stacklim:
        resource.setrlimit(resource.RLIMIT_STACK, (stacklim, stacklim))
        # for some reason, doesn't take effect properly without the exec()
        python = '/usr/bin/python'
        os.execv(python, [python] + savedargv)
    run()
else:
    # This is for debugging purposes.  Open a copy of Python and import nm
    tools.as_daemon_thread(run)
