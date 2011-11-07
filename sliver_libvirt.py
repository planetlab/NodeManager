#

"""LibVirt slivers"""

import accounts
import logger
import subprocess
import os
import libvirt
import sys

states = {
    libvirt.VIR_DOMAIN_NOSTATE: 'no state',
    libvirt.VIR_DOMAIN_RUNNING: 'running',
    libvirt.VIR_DOMAIN_BLOCKED: 'blocked on resource',
    libvirt.VIR_DOMAIN_PAUSED: 'paused by user',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'being shut down',
    libvirt.VIR_DOMAIN_SHUTOFF: 'shut off',
    libvirt.VIR_DOMAIN_CRASHED: 'crashed',
}

class Sliver_LV(accounts.Account):
    """This class wraps LibVirt commands"""
   
    SHELL = '/bin/sh' 
    # Using /bin/bash triggers destroy root/site_admin (?!?)
    TYPE = 'sliver.LIBVIRT'
    # Need to add a tag at myplc to actually use this account
    # type = 'sliver.LIBVIRT'

    def __init__(self, rec):
        self.name = rec['name']
        print "LIBVIRT %s __init__"%(self.name)
        logger.verbose ('sliver_libvirt: %s init'%(self.name))
         
        self.dir = '/vservers/%s'%(self.name)
        
        # Assume the directory with the image and config files
        # are in place
        
        self.config = '%s/config.xml'%(self.dir)
        self.lxc_log  = '%s/log'%(self.dir)
        self.keys = ''
        self.rspec = {}
        self.slice_id = rec['slice_id']
        self.disk_usage_initialized = False
        self.initscript = ''
        self.enabled = True
        conn = Sliver_LV.getConnection()
        try:
            self.container = conn.lookupByName(self.name)
        except:
            print "Unexpected error:", sys.exc_info()[0]

    @staticmethod
    def create(name, rec = None):
        ''' Create dirs, copy fs image, lxc_create '''
        print "LIBVIRT %s create"%(name)
        logger.verbose ('sliver_libvirt: %s create'%(name))
        dir = '/vservers/%s'%(name)
        config = '%s/config.xml'%(dir)
        lxc_log = '%s/log'%(dir)
        
        if not (os.path.isdir(dir) and 
            os.access(dir, os.R_OK | os.W_OK | os.X_OK)):
            logger.verbose('lxc_create: directory %s does not exist or wrong perms'%(dir))
            return
       
        # Get a connection and lookup for the sliver before actually
        # defining it, just in case it was already defined.
        conn = Sliver_LV.getConnection()
        try:
            dom = conn.lookupByName(name)
        except:
            xml = open(config).read()  
            dom = conn.defineXML(xml)
        print Sliver_LV.info(dom)

    @staticmethod
    def destroy(name):
        ''' NEVER CALLED... Figure out when and what to do... '''
        
        print "LIBVIRT %s destroy"%(name)
        logger.verbose ('sliver_libvirt: %s destroy'%(name))
        
        dir = '/vservers/%s'%(name)
        lxc_log = '%s/lxc.log'%(dir)

        conn = conn.Sliver_LV.getConnection()

        try:
            dom = conn.lookupByName(name)
            conn.destroy(dom)
            conn.undefine(dom)
            print Sliver_LV.info(dom)
        except:
            logger.verbose('sliver_libvirt: %s domain does not exists'%(name))
            print "Unexpected error:", sys.exc_info()[0]


    def configure(self, rec):
        ''' Allocate resources and fancy configuration stuff '''
        print "LIBVIRT %s configure"%(self.name) 
        logger.verbose('sliver_libvirt: %s configure'%(self.name)) 

    def start(self, delay=0):
        ''' Just start the sliver '''
        print "LIBVIRT %s start"%(self.name)
        if self.rspec['enabled'] <= 0:
            logger.log('sliver_libvirt: not starting %s, is not enabled'%(self.name))
            return
        else:
            logger.log('sliver_libvirt: %s starting...' % (self.name))

        # Check if it's running to avoid throwing an exception if the
        # domain was already running, create actually means start
        if not self.is_running():
            self.container.create()
        else:
            logger.verbose('sliver_libvirt: sliver %s already started'%(self.name))
            
    def stop(self):
        ''' NEVER CALLED... Figure out when and what to do... '''
        
        print "LIBVIRT %s stop"%(self.name)
        logger.verbose('sliver_libvirt: %s stop'%(self.name))
        
        try:
            self.container.destroy()
        except:
            print "Unexpected error:", sys.exc_info()[0]
    
    def is_running(self):
        ''' Return True if the domain is running '''
        print "LIBVIRT %s is_running"%(self.name)
        logger.verbose('sliver_libvirt: %s is_running'%(self.name))
        try:
            [state, _, _, _, _] = self.container.info()
            if state == libvirt.VIR_DOMAIN_RUNNING:
                logger.verbose('sliver_libvirt: %s is RUNNING'%(self.name))
                return True
            else:
                info = Sliver_LV.info(self.container)
                logger.verbose('sliver_libvirt: %s is NOT RUNNING...\n%s'%(self.name, info))
                return False
        except:
            print "Unexpected error:", sys.exc_info()

    ''' PRIVATE/HELPER/STATIC METHODS '''
    @staticmethod
    def getConnection():
        ''' Helper method to get a connection to the LXC driver of Libvirt '''
        conn = libvirt.open('lxc:///')
        if conn == None:
            print 'Failed to open connection to LXC hypervisor'
            sys.exit(1)
        else: return conn

    @staticmethod
    def info(dom):
        ''' Helper method to get a "nice" output of the info struct for debug'''
        [state, maxmem, mem, ncpu, cputime] = dom.info()
        return '%s is %s, maxmem = %s, mem = %s, ncpu = %s, cputime = %s' % (dom.name(), states.get(state, state), maxmem, mem, ncpu, cputime)


