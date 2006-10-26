"""Node Manager"""

import optparse
import time

from config import *
import accounts
import api
import database
import delegate
import logger
import plc
import sliver_vs
import tools


parser = optparse.OptionParser()
parser.add_option('-d', '--daemon',
                  action='store_true', dest='daemon', default=False,
                  help='run daemonized')
parser.add_option('-s', '--startup',
                  action='store_true', dest='startup', default=False,
                  help='run all sliver startup scripts')
(options, args) = parser.parse_args()

def run():
    try:
        if options.daemon: tools.daemon()

        accounts.register_class(sliver_vs.Sliver_VS)
        accounts.register_class(delegate.Delegate)

        other_pid = tools.pid_file()
        if other_pid != None:
            print """There might be another instance of the node manager running as pid %d.  If this is not the case, please remove the pid file %s""" % (other_pid, PID_FILE)
            return

        database.start()
        api.start()
        while True:
            try: plc.fetch_and_update()
            except: logger.log_exc()
            time.sleep(10)
    except: logger.log_exc()


if __name__ == '__main__': run()
else:
    # This is for debugging purposes.  Open a copy of Python and import nm
    tools.as_daemon_thread(run)
