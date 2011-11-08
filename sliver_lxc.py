#

"""LXC slivers"""

import accounts
import logger
import subprocess
import os
import libvirt
import sys

def test_template():

    xml_template = """
    <domain type='lxc'>
        <name>test_1</name>
        <memory>32768</memory>
        <os>
            <type>exe</type>
            <init>/bin/sh</init>
        </os>
        <vcpu>1</vcpu>
        <clock offset='utc'/>
        <on_poweroff>destroy</on_poweroff>
        <on_reboot>restart</on_reboot>
        <on_crash>destroy</on_crash>
        <devices>
            <emulator>/usr/libexec/libvirt_lxc</emulator>
            <filesystem type='mount'>
                <source dir='/vservers/test_1/rootfs/'/>
                <target dir='/'/>
            </filesystem>
            <interface type='network'>
                <source network='default'/>
            </interface>
            <console type='pty' />
        </devices>
    </domain>"""

    return xml_template

def createConnection():
    conn = libvirt.open('lxc:///')
    if conn == None:
        print 'Failed to open connection to LXC hypervisor'
        sys.exit(1)
    else: return conn


states = {
    libvirt.VIR_DOMAIN_NOSTATE: 'no state',
    libvirt.VIR_DOMAIN_RUNNING: 'running',
    libvirt.VIR_DOMAIN_BLOCKED: 'blocked on resource',
    libvirt.VIR_DOMAIN_PAUSED: 'paused by user',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'being shut down',
    libvirt.VIR_DOMAIN_SHUTOFF: 'shut off',
    libvirt.VIR_DOMAIN_CRASHED: 'crashed',
}

def info(dom):
    [state, maxmem, mem, ncpu, cputime] = dom.info()
    return '%s is %s,\nmaxmem = %s, mem = %s, ncpu = %s, cputime = %s' % (dom.name(), states.get(state, state), maxmem, mem, ncpu, cputime)

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
        self.connection = createConnection()

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
        #subprocess.call(command, stdin=open('/dev/null', 'r'), stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT, shell=False)
        conn = createConnection()
        try:
            dom0 = conn.lookupByName(name)
        except:
            dom0 = conn.defineXML(test_template())
        print info(dom0)

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

 
