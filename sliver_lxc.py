#

"""LXC slivers"""

import accounts
import logger
import subprocess
import os

class Sliver_LXC(accounts.Account):
    """This class wraps LXC commands"""

    SHELL = '/bin/sh' 
    # Using /bin/bash triggers destroy root/site_admin (?!?)
    TYPE = 'sliver.LXC'
    # Need to add a tag at myplc to actually use this account
    # type = 'sliver.LXC'

    def __init__(self, rec):
        self.name = rec['name']
        print "LXC __init__ %s"%(self.name)
        logger.verbose ('sliver_lxc: %s init'%self.name)
    
        self.dir = '/vservers/%s'%(self.name)
        
        # Assume the directory with the image and config files
        # are in place
        
        self.config = '%s/config'%(self.dir)
        self.fstab  = '%s/fstab'%(self.dir)
        self.lxc_log  = '%s/lxc.log'%(self.dir)
        self.keys = ''
        self.rspec = {}
        self.slice_id = rec['slice_id']
        self.disk_usage_initialized = False
        self.initscript = ''
        self.enabled = True
        self.configure(rec)

    @staticmethod
    def create(name, rec = None):
        ''' Create dirs, copy fs image, lxc_create '''
        print "LXC create %s"%(name)
        logger.verbose ('sliver_lxc: %s create'%name)
        dir = '/vservers/%s'%(name)
        config = '%s/config'%(dir)
        lxc_log = '%s/lxc.log'%(dir)
        
        if not (os.path.isdir(dir) and 
            os.access(dir, os.R_OK | os.W_OK | os.X_OK)):
            print 'lxc_create: directory %s does not exist or wrong perms'%(dir)
            return
        # Assume for now that the directory is there and with a FS
        command=[]
        # be verbose
        command += ['/bin/bash','-x',]
        command += ['/usr/bin/lxc-create', '-n', name, '-f', config, '&']
        print command
        subprocess.call(command, stdin=open('/dev/null', 'r'), stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT, shell=False)
        
    @staticmethod
    def destroy(name):
        ''' lxc_destroy '''
        print "LXC destroy %s"%(name)
        dir = '/vservers/%s'%(name)
        lxc_log = '%s/lxc.log'%(dir)
        command=[]
        command += ['/usr/bin/lxc-destroy', '-n', name]

        subprocess.call(command, stdin=open('/dev/null', 'r'), stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT, shell=False)
        print "LXC destroy DONE"

    def configure(self, rec):
        print "LXC configure %s"%(self.name) 

    def start(self, delay=0):
        ''' Check existence? lxc_start '''
        print "LXC start %s"%(self.name)
        command=[]
        command += ['/usr/bin/lxc-start', '-n', self.name, '-d']
        print command
        subprocess.call(command, stdin=open('/dev/null', 'r'), stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT, shell=False)

    def stop(self):
        ''' lxc_stop '''
        print "LXC stop %s"%(self.name)
    
    def is_running(self):
        print "LXC is_running %s"%(self.name)
        command = []
        command += ['/usr/bin/lxc-info -n %s'%(self.name)]
        print command
        p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        state = p.communicate()[0].split(' ')[2]
        print state
        if state == 'RUNNING': return True
        else: return False

  
