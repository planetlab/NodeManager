#

"""LXC slivers"""

import accounts
import logger
import subprocess
import os
import libvirt
import sys
from string import Template
import sliver_libvirt as lv

URI = 'lxc://'

class Sliver_LXC(accounts.Account):
    """This class wraps LXC commands"""
   
    SHELL = '/bin/sshsh' 
    
    TYPE = 'sliver.LXC'
    # Need to add a tag at myplc to actually use this account
    # type = 'sliver.LXC'


    @staticmethod
    def create(name, rec=None):
        conn = lv.getConnection(URI)
        
        # Template for libvirt sliver configuration
        try:
            with open('/vservers/.lvref/config_template.xml') as f:
                template = Template(f.read())
                config   = template.substitute(name=name)
        except IOError:
            logger.log('Cannot find XML template file')
            return
        
        lv.create(name, config, rec, conn)

    @staticmethod
    def destroy(name):
        conn = lv.getConnection(URI)
        lv.destroy(name, conn)

    def __init__(self, rec):
        self.name = rec['name']
        logger.verbose ('sliver_lxc: %s init'%(self.name))
         
        self.dir = '/vservers/%s'%(self.name)
        
        # Assume the directory with the image and config files
        # are in place
        
        self.keys = ''
        self.rspec = {}
        self.slice_id = rec['slice_id']
        self.disk_usage_initialized = False
        self.initscript = ''
        self.enabled = True
        self.conn = lv.getConnection(URI)
        try:
            self.container = self.conn.lookupByName(self.name)
        except:
            logger.verbose('sliver_libvirt: Unexpected error on %s: %s'%(self.name, sys.exc_info()[0]))

    def start(self, delay=0):
        lv.start(self.container)

    def stop(self):
        lv.stop(self.container)

    def is_running(self):
        lv.is_running(self.container)

    def configure(self, rec):
        ''' Allocate resources and fancy configuration stuff '''
        logger.verbose('sliver_libvirt: %s configure'%(self.name))
        accounts.Account.configure(self, rec)
