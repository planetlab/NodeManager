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


savedargv = sys.argv[:]

parser = optparse.OptionParser()
parser.add_option('-d', '--daemon', action='store_true', dest='daemon', default=False, help='run daemonized')
parser.add_option('-s', '--startup', action='store_true', dest='startup', default=False, help='run all sliver startup scripts')
parser.add_option('-f', '--config', action='store', dest='config', default='/etc/planetlab/plc_config', help='PLC configuration file')
parser.add_option('-k', '--session', action='store', dest='session', default='/etc/planetlab/session', help='API session key (or file)')
parser.add_option('-p', '--period', action='store', dest='period', default=600, help='Polling interval (sec)')
(options, args) = parser.parse_args()

modules = []

def GetSlivers(plc):
    data = plc.GetSlivers()
    # net needs access to API for i2 nodes.
    for module in modules:
        if module.__name__ == 'net':
            module.GetSlivers(plc, data)
        else:
            callback = getattr(module, 'GetSlivers')
            callback(data)

def run():
    try:
        if options.daemon: tools.daemon()

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
        for module in ['net', 'proper', 'conf_files', 'sm']:
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
        plc = PLCAPI(config.plc_api_uri, config.cacert, session, timeout=options.period/2)

        while True:
            try: GetSlivers(plc)
            except: logger.log_exc()
            time.sleep(options.period + random.randrange(0,301))
    except: logger.log_exc()


if __name__ == '__main__':
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
