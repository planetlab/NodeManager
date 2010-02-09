#!/usr/bin/python
#
# $Id$
# $URL$
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

import logger
import tools

from config import Config
from plcapi import PLCAPI 
import random

id="$Id$"
savedargv = sys.argv[:]

# NOTE: modules listed here should also be loaded in this order
# see the priority set in each module - lower comes first
known_modules=['net','conf_files', 'sm', 'bwmon']

plugin_path = "/usr/share/NodeManager/plugins"

default_period=600
default_random=301

parser = optparse.OptionParser()
parser.add_option('-d', '--daemon', action='store_true', dest='daemon', default=False, help='run daemonized')
parser.add_option('-s', '--startup', action='store_true', dest='startup', default=False, help='run all sliver startup scripts')
parser.add_option('-f', '--config', action='store', dest='config', default='/etc/planetlab/plc_config', help='PLC configuration file')
parser.add_option('-k', '--session', action='store', dest='session', default='/etc/planetlab/session', help='API session key (or file)')
parser.add_option('-p', '--period', action='store', dest='period', default=default_period, 
                  help='Polling interval (sec) - default %d'%default_period)
parser.add_option('-r', '--random', action='store', dest='random', default=default_random, 
                  help='Range for additional random polling interval (sec) -- default %d'%default_random)
parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False, help='more verbose log')
parser.add_option('-P', '--path', action='store', dest='path', default=plugin_path, help='Path to plugins directory')

# NOTE: BUG the 'help' for this parser.add_option() wont list plugins from the --path argument
parser.add_option('-m', '--module', action='store', dest='module', default='', help='run a single module among '+' '.join(known_modules))
(options, args) = parser.parse_args()

# Deal with plugins directory
if os.path.exists(options.path):
    sys.path.append(options.path)
    plugins = [ os.path.split(os.path.splitext(x)[0])[1] for x in glob.glob( os.path.join(options.path,'*.py') ) ]
    known_modules += plugins

modules = []

def GetSlivers(config, plc):
    '''Run call backs defined in modules'''
    try: 
        logger.log("nm: Syncing w/ PLC")
        # retrieve GetSlivers from PLC
        data = plc.GetSlivers()
        # use the magic 'default' slice to retrieve system-wide defaults
        getPLCDefaults(data, config)
        # tweak the 'vref' attribute from GetSliceFamily
        setSliversVref (data)
        # always dump it for debug purposes
        # used to be done only in verbose; very helpful though, and tedious to obtain,
        # so let's dump this unconditionnally
        logger.log_slivers(data)
        logger.verbose("nm: Sync w/ PLC done")
    except: 
        logger.log_exc("nm: failed in GetSlivers")
        #  XXX So some modules can at least boostrap.
        logger.log("nm:  Can't contact PLC to GetSlivers().  Continuing.")
        data = {}
    #  Invoke GetSlivers() functions from the callback modules
    for module in modules:
#        logger.log('trigerring GetSlivers callback for module %s'%module.__name__)
        try:        
            callback = getattr(module, 'GetSlivers')
            callback(data, config, plc)
        except: 
            logger.log_exc("nm: GetSlivers failed to run callback for module %r"%module)


def getPLCDefaults(data, config):
    '''
    Get PLC wide defaults from _default system slice.  Adds them to config class.
    '''
    for slice in data.get('slivers'): 
        if slice['name'] == config.PLC_SLICE_PREFIX+"_default":
            attr_dict = {}
            for attr in slice.get('attributes'): attr_dict[attr['tagname']] = attr['value'] 
            if len(attr_dict):
                logger.verbose("nm: Found default slice overrides.\n %s" % attr_dict)
                config.OVERRIDES = attr_dict
                return
    # NOTE: if an _default slice existed, it would have been found above and
    # 	    the routine would return.  Thus, if we've gotten here, then no default
    # 	    slice is bound to this node.
    if 'OVERRIDES' in dir(config): del config.OVERRIDES


def setSliversVref (data):
    '''
    Tweak the 'vref' attribute in all slivers based on the 'GetSliceFamily' key
    '''
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
            logger.log_exc("nm: Could not overwrite 'vref' attribute from 'GetSliceFamily'",name=sliver['name'])
    

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
            logger.verbose('nm: Running single module %s'%options.module)
        else:
            running_modules=known_modules
        for module in running_modules:
            try:
                m = __import__(module)
                m.start(options, config)
                modules.append(m)
            except ImportError, err:
                print "Warning while loading module %s:" % module, err

        default_priority=100
        # sort on priority (lower first)
        def sort_module_priority (m1,m2):
            return getattr(m1,'priority',default_priority) - getattr(m2,'priority',default_priority)
        modules.sort(sort_module_priority)

        logger.verbose('modules priorities and order:')
        for module in modules: logger.verbose ('%s: %s'%(getattr(module,'priority',default_priority),module.__name__))

        # Load /etc/planetlab/session
        if os.path.exists(options.session):
            session = file(options.session).read().strip()
        else:
            session = None

        # Initialize XML-RPC client
        iperiod=int(options.period)
        irandom=int(options.random)
        plc = PLCAPI(config.plc_api_uri, config.cacert, session, timeout=iperiod/2)

        #check auth
        logger.log("nm: Checking Auth.")
        while plc.check_authentication() != True:
            try:
                plc.update_session()
                logger.log("nm: Authentication Failure. Retrying")
            except:
                logger.log("nm: Retry Failed. Waiting")
            time.sleep(iperiod)
        logger.log("nm: Authentication Succeeded!")


        while True:
        # Main NM Loop
            logger.verbose('nm: mainloop - calling GetSlivers - period=%d random=%d'%(iperiod,irandom))
            GetSlivers(config, plc)
            delay=iperiod + random.randrange(0,irandom)
            logger.verbose('nm: mainloop - sleeping for %d s'%delay)
            time.sleep(delay)
    except: logger.log_exc("nm: failed in run")


if __name__ == '__main__':
    logger.log("======================================== Entering nm.py "+id)
    run()
else:
    # This is for debugging purposes.  Open a copy of Python and import nm
    tools.as_daemon_thread(run)
