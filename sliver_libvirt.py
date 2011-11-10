#

"""LibVirt slivers"""

import accounts
import logger
import subprocess
import os
import os.path
import libvirt
import sys
import shutil

from string import Template

states = {
    libvirt.VIR_DOMAIN_NOSTATE: 'no state',
    libvirt.VIR_DOMAIN_RUNNING: 'running',
    libvirt.VIR_DOMAIN_BLOCKED: 'blocked on resource',
    libvirt.VIR_DOMAIN_PAUSED: 'paused by user',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'being shut down',
    libvirt.VIR_DOMAIN_SHUTOFF: 'shut off',
    libvirt.VIR_DOMAIN_CRASHED: 'crashed',
}

REF_IMG_BASE_DIR = '/vservers/.lvref'
CON_BASE_DIR     = '/vservers'

class Sliver_LV(accounts.Account):
    """This class wraps LibVirt commands"""
   
    SHELL = '/bin/sh' 

    # Need to add a tag at myplc to actually use this account
    # type = 'sliver.LIBVIRT'
    TYPE = 'sliver.LIBVIRT'
    

    @staticmethod
    def create(name, rec = None):
        ''' Create dirs, copy fs image, lxc_create '''
        logger.verbose ('sliver_libvirt: %s create'%(name))

        # Template for libvirt sliver configuration
        try:
            with open('/vservers/.lvref/config_template.xml') as f:
                template = Template(f.read())
                config   = template.substitute(name=name)
        except IOError:
            logger.log('Cannot find XML template file')
            return
        
        # Get the type of image from vref myplc tags specified as:
        # pldistro = lxc
        # fcdistro = squeeze
        # arch x86_64
        vref = rec['vref']
        if vref is None:
            logger.log('sliver_libvirt: %s: WARNING - no vref attached defaults to lxc-debian' % (name))
            vref = "lxc-squeeze-x86_64"

        refImgDir    = os.path.join(REF_IMG_BASE_DIR, vref)
        containerDir = os.path.join(CON_BASE_DIR, name)

        # check the template exists -- there's probably a better way..
        if not os.path.isdir(refImgDir):
            logger.log('sliver_libvirt: %s: ERROR Could not create sliver - reference image %s not found' % (name,vref))
            return

        # Copy the reference image fs
        # shutil.copytree("/vservers/.lvref/%s"%vref, "/vservers/%s"%name, symlinks=True)
        command = ['cp', '-r', refImgDir, containerDir]
        logger.log_call(command, timeout=15*60)

        # Set hostname. A valid hostname cannot have '_'
        with open(os.path.join(containerDir, 'etc/hostname'), 'w') as f:
            print >>f, name.replace('_', '-')

        # Add unix account
        command = ['/usr/sbin/useradd', '-s', '/bin/sh', name]
        logger.log_call(command, timeout=15*60)

        # Get a connection and lookup for the sliver before actually
        # defining it, just in case it was already defined.
        conn = Sliver_LV.getConnection()
        try:
            dom = conn.lookupByName(name)
        except:
            dom = conn.defineXML(config)
        logger.verbose('lxc_create: %s -> %s'%(name, Sliver_LV.info(dom)))

    @staticmethod
    def destroy(name):
        logger.verbose ('sliver_libvirt: %s destroy'%(name))
        
        dir = '/vservers/%s'%(name)
        lxc_log = '%s/lxc.log'%(dir)

        conn = Sliver_LV.getConnection()

        try:
            command = ['/usr/sbin/userdel', name]
            logger.log_call(command, timeout=15*60)
            
            # Destroy libvirt domain
            dom = conn.lookupByName(name)
            dom.destroy()
            dom.undefine()

            # Remove rootfs of destroyed domain
            shutil.rmtree("/vservers/%s"%name)
        except:
            logger.verbose('sliver_libvirt: Unexpected error on %s: %s'%(name, sys.exc_info()[0]))
    
    def __init__(self, rec):
        self.name = rec['name']
        logger.verbose ('sliver_libvirt: %s init'%(self.name))
         
        self.dir = '/vservers/%s'%(self.name)
        
        # Assume the directory with the image and config files
        # are in place
        
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
            logger.verbose('sliver_libvirt: Unexpected error on %s: %s'%(self.name, sys.exc_info()[0]))

    def configure(self, rec):
        ''' Allocate resources and fancy configuration stuff '''
        logger.verbose('sliver_libvirt: %s configure'%(self.name)) 
        accounts.Account.configure(self, rec)  
    
    def start(self, delay=0):
        ''' Just start the sliver '''
        print "LIBVIRT %s start"%(self.name)

        # Check if it's running to avoid throwing an exception if the
        # domain was already running, create actually means start
        if not self.is_running():
            self.container.create()
        else:
            logger.verbose('sliver_libvirt: sliver %s already started'%(self.name))
            
    def stop(self):
        logger.verbose('sliver_libvirt: %s stop'%(self.name))
        
        try:
            self.container.destroy()
        except:
            print "Unexpected error:", sys.exc_info()[0]
    
    def is_running(self):
        ''' Return True if the domain is running '''
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


