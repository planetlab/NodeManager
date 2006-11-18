#!/usr/bin/python

"""Node Manager"""

import optparse
import time
import xmlrpclib
import socket
import os

import logger
import tools

from config import Config
from plcapi import PLCAPI

parser = optparse.OptionParser()
parser.add_option('-d', '--daemon', action='store_true', dest='daemon', default=False, help='run daemonized')
parser.add_option('-s', '--startup', action='store_true', dest='startup', default=False, help='run all sliver startup scripts')
parser.add_option('-f', '--config', action='store', dest='config', default='/etc/planetlab/plc_config', help='PLC configuration file')
parser.add_option('-k', '--session', action='store', dest='session', default='/etc/planetlab/session', help='API session key (or file)')
parser.add_option('-p', '--period', action='store', dest='period', default=600, help='Polling interval (sec)')
(options, args) = parser.parse_args()

# XXX - awaiting a real implementation
data = []
modules = []

def GetSlivers(plc):
    data = plc.GetSlivers()

    for mod in modules: mod.GetSlivers_callback(data)

def start_and_register_callback(mod, config):
    mod.start(options, config)
    modules.append(mod)


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

        try:
            import sm
            start_and_register_callback(sm, config)
            import conf_files
            start_and_register_callback(conf_files, config)
        except ImportError, err:
            print "Warning while registering callbacks:", err

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
            time.sleep(options.period)
    except: logger.log_exc()


if __name__ == '__main__': run()
else:
    # This is for debugging purposes.  Open a copy of Python and import nm
    tools.as_daemon_thread(run)
