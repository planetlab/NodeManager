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
import glob
import pickle

import logger
import tools

from config import Config
from plcapi import PLCAPI
import random


class NodeManager:

    PLUGIN_PATH = "/usr/share/NodeManager/plugins"

    DB_FILE = "/var/lib/nodemanager/getslivers.pickle"

    # the modules in this directory that need to be run
    # NOTE: modules listed here will also be loaded in this order
    # once loaded, they get re-ordered after their priority (lower comes first)
    # for determining the runtime order
    core_modules=['net', 'conf_files', 'slivermanager', 'bwmon']

    default_period=600
    default_random=301
    default_priority=100

    def __init__ (self):

        parser = optparse.OptionParser()
        parser.add_option('-d', '--daemon', action='store_true', dest='daemon', default=False,
                          help='run daemonized')
        parser.add_option('-f', '--config', action='store', dest='config', default='/etc/planetlab/plc_config',
                          help='PLC configuration file')
        parser.add_option('-k', '--session', action='store', dest='session', default='/etc/planetlab/session',
                          help='API session key (or file)')
        parser.add_option('-p', '--period', action='store', dest='period', default=NodeManager.default_period,
                          help='Polling interval (sec) - default %d'%NodeManager.default_period)
        parser.add_option('-r', '--random', action='store', dest='random', default=NodeManager.default_random,
                          help='Range for additional random polling interval (sec) -- default %d'%NodeManager.default_random)
        parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                          help='more verbose log')
        parser.add_option('-P', '--path', action='store', dest='path', default=NodeManager.PLUGIN_PATH,
                          help='Path to plugins directory')

        # NOTE: BUG the 'help' for this parser.add_option() wont list plugins from the --path argument
        parser.add_option('-m', '--module', action='store', dest='user_module', default='', help='run a single module')
        (self.options, args) = parser.parse_args()

        if len(args) != 0:
            parser.print_help()
            sys.exit(1)

        # determine the modules to be run
        self.modules = NodeManager.core_modules
        # Deal with plugins directory
        if os.path.exists(self.options.path):
            sys.path.append(self.options.path)
            plugins = [ os.path.split(os.path.splitext(x)[0])[1] for x in glob.glob( os.path.join(self.options.path,'*.py') ) ]
            self.modules += plugins
        if self.options.user_module:
            assert self.options.user_module in self.modules
            self.modules=[self.options.user_module]
            logger.verbose('nodemanager: Running single module %s'%self.options.user_module)


    def GetSlivers(self, config, plc):
        """Retrieves GetSlivers at PLC and triggers callbacks defined in modules/plugins"""
        try:
            logger.log("nodemanager: Syncing w/ PLC")
            # retrieve GetSlivers from PLC
            data = plc.GetSlivers()
            # use the magic 'default' slice to retrieve system-wide defaults
            self.getPLCDefaults(data, config)
            # tweak the 'vref' attribute from GetSliceFamily
            self.setSliversVref (data)
            # dump it too, so it can be retrieved later in case of comm. failure
            self.dumpSlivers(data)
            # log it for debug purposes, no matter what verbose is
            logger.log_slivers(data)
            logger.verbose("nodemanager: Sync w/ PLC done")
            last_data=data
        except:
            logger.log_exc("nodemanager: failed in GetSlivers")
            #  XXX So some modules can at least boostrap.
            logger.log("nodemanager:  Can't contact PLC to GetSlivers().  Continuing.")
            data = {}
            # for modules that request it though the 'persistent_data' property
            last_data=self.loadSlivers()
        #  Invoke GetSlivers() functions from the callback modules
        for module in self.loaded_modules:
            logger.verbose('nodemanager: triggering %s.GetSlivers'%module.__name__)
            try:
                callback = getattr(module, 'GetSlivers')
                module_data=data
                if getattr(module,'persistent_data',False):
                    module_data=last_data
                callback(data, config, plc)
            except:
                logger.log_exc("nodemanager: GetSlivers failed to run callback for module %r"%module)


    def getPLCDefaults(self, data, config):
        """
        Get PLC wide defaults from _default system slice.  Adds them to config class.
        """
        for slice in data.get('slivers'):
            if slice['name'] == config.PLC_SLICE_PREFIX+"_default":
                attr_dict = {}
                for attr in slice.get('attributes'): attr_dict[attr['tagname']] = attr['value']
                if len(attr_dict):
                    logger.verbose("nodemanager: Found default slice overrides.\n %s" % attr_dict)
                    config.OVERRIDES = attr_dict
                    return
        # NOTE: if an _default slice existed, it would have been found above and
        #           the routine would return.  Thus, if we've gotten here, then no default
        #           slice is bound to this node.
        if 'OVERRIDES' in dir(config): del config.OVERRIDES


    def setSliversVref (self, data):
        """
        Tweak the 'vref' attribute in all slivers based on the 'GetSliceFamily' key
        """
        # GetSlivers exposes the result of GetSliceFamily() as an separate key in data
        # It is safe to override the attributes with this, as this method has the right logic
        for sliver in data.get('slivers'):
            try:
                slicefamily=sliver.get('GetSliceFamily')
                for att in sliver['attributes']:
                    if att['tagname']=='vref':
                        att['value']=slicefamily
                        continue
                sliver['attributes'].append({ 'tagname':'vref','value':slicefamily})
            except:
                logger.log_exc("nodemanager: Could not overwrite 'vref' attribute from 'GetSliceFamily'",name=sliver['name'])

    def dumpSlivers (self, slivers):
        f = open(NodeManager.DB_FILE, "w")
        logger.log ("nodemanager: saving successfully fetched GetSlivers in %s" % NodeManager.DB_FILE)
        pickle.dump(slivers, f)
        f.close()

    def loadSlivers (self):
        try:
            f = open(NodeManager.DB_FILE, "r+")
            logger.log("nodemanager: restoring latest known GetSlivers from %s" % NodeManager.DB_FILE)
            slivers = pickle.load(f)
            f.close()
            return slivers
        except:
            logger.log("Could not restore GetSlivers from %s" % NodeManager.DB_FILE)
            return {}

    def run(self):
        try:
            if self.options.daemon: tools.daemon()

            # set log level
            if (self.options.verbose):
                logger.set_level(logger.LOG_VERBOSE)

            # Load /etc/planetlab/plc_config
            config = Config(self.options.config)

            try:
                other_pid = tools.pid_file()
                if other_pid != None:
                    print """There might be another instance of the node manager running as pid %d.
If this is not the case, please remove the pid file %s. -- exiting""" % (other_pid, tools.PID_FILE)
                    return
            except OSError, err:
                print "Warning while writing PID file:", err

            # load modules
            self.loaded_modules = []
            for module in self.modules:
                try:
                    m = __import__(module)
                    logger.verbose("nodemanager: triggering %s.start"%m.__name__)
                    m.start()
                    self.loaded_modules.append(m)
                except ImportError, err:
                    print "Warning while loading module %s:" % module, err

            # sort on priority (lower first)
            def sort_module_priority (m1,m2):
                return getattr(m1,'priority',NodeManager.default_priority) - getattr(m2,'priority',NodeManager.default_priority)
            self.loaded_modules.sort(sort_module_priority)

            logger.log('ordered modules:')
            for module in self.loaded_modules:
                logger.log ('%s: %s'%(getattr(module,'priority',NodeManager.default_priority),module.__name__))

            # Load /etc/planetlab/session
            if os.path.exists(self.options.session):
                session = file(self.options.session).read().strip()
            else:
                session = None


            # get random periods
            iperiod=int(self.options.period)
            irandom=int(self.options.random)

            # Initialize XML-RPC client
            plc = PLCAPI(config.plc_api_uri, config.cacert, session, timeout=iperiod/2)

            #check auth
            logger.log("nodemanager: Checking Auth.")
            while plc.check_authentication() != True:
                try:
                    plc.update_session()
                    logger.log("nodemanager: Authentication Failure. Retrying")
                except Exception,e:
                    logger.log("nodemanager: Retry Failed. (%r); Waiting.."%e)
                time.sleep(iperiod)
            logger.log("nodemanager: Authentication Succeeded!")


            while True:
            # Main nodemanager Loop
                logger.log('nodemanager: mainloop - calling GetSlivers - period=%d random=%d'%(iperiod,irandom))
                self.GetSlivers(config, plc)
                delay=iperiod + random.randrange(0,irandom)
                logger.log('nodemanager: mainloop - sleeping for %d s'%delay)
                time.sleep(delay)
        except: logger.log_exc("nodemanager: failed in run")

def run():
    logger.log("======================================== Entering nodemanager.py")
    NodeManager().run()

if __name__ == '__main__':
    run()
else:
    # This is for debugging purposes.  Open a copy of Python and import nodemanager
    tools.as_daemon_thread(run)
