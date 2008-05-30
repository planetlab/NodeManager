#!/usr/bin/python
#
# Test script for obtaining a node session key. Usually, the Boot
# Manager obtains it, then writes it to /etc/planetlab/session. 
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id$
#

import os, sys
import getopt

from config import Config
from plcapi import PLCAPI

def main():
    # Defaults
    config = None
    node_id = None
    key = None

    # Help
    def usage():
        print "Usage: %s [OPTION]..." % sys.argv[0]
        print "Options:"
        print "     -f, --config=FILE       PLC configuration file (default: /etc/planetlab/plc_config)"
        print "     -n, --node-id=FILE      Node ID (or file)"
        print "     -k, --key=FILE          Node key (or file)"
        print "     --help                  This message"
        sys.exit(1)

    # Get options
    try:
        (opts, argv) = getopt.getopt(sys.argv[1:], "f:n:k:h",
                                     ["config=", "cfg=", "file=",
                                      "node=", "nodeid=", "node-id", "node_id",
                                      "key=",
                                      "help"])
    except getopt.GetoptError, err:
        print "Error: " + err.msg
        usage()

    for (opt, optval) in opts:
        if opt == "-f" or opt == "--config" or opt == "--cfg" or opt == "--file":
            config = Config(optval)
        elif opt == "-n" or opt == "--node" or opt == "--nodeid" or opt == "--node-id" or opt == "--node_id":
            if os.path.exists(optval):
                node_id = file(optval).read().strip()
            else:
                node_id = int(optval)
        elif opt == "-k" or opt == "--key":
            if os.path.exists(optval):
                key = file(optval).read().strip()
            else:
                key = optval
        else:
            usage()

    if config is None:
        config = Config()

    if node_id is None or \
       key is None:
        usage()

    # Authenticate as the Boot Manager would and get a session key
    plc = PLCAPI(config.plc_api_uri, config.cacert, (node_id, key))
    session = plc.BootGetNodeDetails()['session']

    plc = PLCAPI(config.plc_api_uri, config.cacert, session)
    assert session == plc.GetSession()

    print session

if __name__ == '__main__':
    main()
