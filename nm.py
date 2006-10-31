"""Node Manager"""

import optparse
import time
import xmlrpclib

import conf_files
import logger
import sm
import tools


parser = optparse.OptionParser()
parser.add_option('-d', '--daemon', action='store_true', dest='daemon', default=False, help='run daemonized')
parser.add_option('-s', '--startup', action='store_true', dest='startup', default=False, help='run all sliver startup scripts')
(options, args) = parser.parse_args()

# XXX - awaiting a real implementation
data = []
modules = []

def GetSlivers():
    for mod in modules: mod.GetSlivers_callback(data)

def start_and_register_callback(mod):
    mod.start(options)
    modules.append(mod)


def run():
    try:
        if options.daemon: tools.daemon()


        other_pid = tools.pid_file()
        if other_pid != None:
            print """There might be another instance of the node manager running as pid %d.  If this is not the case, please remove the pid file %s""" % (other_pid, tools.PID_FILE)
            return

        start_and_register_callback(sm)
        start_and_register_callback(conf_files)
        while True:
            try: GetSlivers()
            except: logger.log_exc()
            time.sleep(10)
    except: logger.log_exc()


if __name__ == '__main__': run()
else:
    # This is for debugging purposes.  Open a copy of Python and import nm
    tools.as_daemon_thread(run)
