#!/usr/bin/python
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
parser.add_option('-m', '--module', action='store', dest='module', default='', help='run a single module among '+' '.join(known_modules))
(options, args) = parser.parse_args()

modules = []

def GetSlivers(plc):
    try: 
        logger.log("Syncing w/ PLC")
        data = plc.GetSlivers()
    except: 
        logger.log_exc()
        #  XXX So some modules can at least boostrap.
        data = {}
    if (options.verbose):
        logger.log_slivers(data)
    # Set i2 ip list for nodes in I2 nodegroup.
    try: net.GetSlivers(plc, data)
    except: logger.log_exc()
    #  All other callback modules
    for module in modules:
        try:        
            callback = getattr(module, 'GetSlivers')
            callback(data)
        except: logger.log_exc()

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
            session = options.session

        # Initialize XML-RPC client
        iperiod=int(options.period)
        irandom=int(options.random)
        plc = PLCAPI(config.plc_api_uri, config.cacert, session, timeout=iperiod/2)

        while True:
        # Main NM Loop
            logger.verbose('mainloop - nm:getSlivers - period=%d random=%d'%(iperiod,irandom))
            GetSlivers(plc)
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
