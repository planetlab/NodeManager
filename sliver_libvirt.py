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

STATES = {
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

connections = dict()

def getConnection(uri):
    # TODO: error checking
    return connections.setdefault(uri, libvirt.open(uri))

def create(name, xml, rec, conn):
    ''' Create dirs, copy fs image, lxc_create '''
    logger.verbose ('sliver_libvirt: %s create'%(name))
    
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

    # Add slices group if not already present
    command = ['/usr/sbin/groupadd', 'slices']
    logger.log_call(command, timeout=15*60)
    
    # Add unix account (TYPE is specified in the subclass)
    command = ['/usr/sbin/useradd', '-g', 'slices', '-s', '/bin/sshsh', name, '-p', '*']
    logger.log_call(command, timeout=15*60)
    command = ['mkdir', '/home/%s/.ssh'%name]
    logger.log_call(command, timeout=15*60)

    # Create PK pair keys to connect from the host to the guest without
    # password... maybe remove the need for authentication inside the
    # guest?
    command = ['su', '-s', '/bin/bash', '-c', 'ssh-keygen -t rsa -N "" -f /home/%s/.ssh/id_rsa'%(name)]
    logger.log_call(command, timeout=15*60)
    
    command = ['chown', '-R', '%s.slices'%name, '/home/%s/.ssh'%name]
    logger.log_call(command, timeout=15*60)

    command = ['cp', '/home/%s/.ssh/id_rsa.pub'%name, '%s/root/.ssh/authorized_keys'%containerDir]
    logger.log_call(command, timeout=15*60)

    # Get a connection and lookup for the sliver before actually
    # defining it, just in case it was already defined.
    try:
        dom = conn.lookupByName(name)
    except:
        dom = conn.defineXML(xml)
    logger.verbose('lxc_create: %s -> %s'%(name, debuginfo(dom)))


def destroy(name, conn):
    logger.verbose ('sliver_libvirt: %s destroy'%(name))
    
    dir = '/vservers/%s'%(name)
    lxc_log = '%s/lxc.log'%(dir)

    try:
        
        # Destroy libvirt domain
        dom = conn.lookupByName(name)
        dom.destroy()
        dom.undefine()

        # Remove user after destroy domain to force logout
        command = ['/usr/sbin/userdel', '-f', '-r', name]
        logger.log_call(command, timeout=15*60)
        
        # Remove rootfs of destroyed domain
        shutil.rmtree("/vservers/%s"%name)
    except:
        logger.verbose('sliver_libvirt: Unexpected error on %s: %s'%(name, sys.exc_info()[0]))


def start(dom):
    ''' Just start the sliver '''
    print "LIBVIRT %s start"%(dom.name())

    # Check if it's running to avoid throwing an exception if the
    # domain was already running, create actually means start
    if not is_running(dom):
        dom.create()
    else:
        logger.verbose('sliver_libvirt: sliver %s already started'%(dom.name()))
       

def stop(dom):
    logger.verbose('sliver_libvirt: %s stop'%(dom.name()))
    
    try:
        dom.destroy()
    except:
        print "Unexpected error:", sys.exc_info()[0]
    
def is_running(dom):
    ''' Return True if the domain is running '''
    logger.verbose('sliver_libvirt: %s is_running'%dom.name())
    try:
        [state, _, _, _, _] = dom.info()
        if state == libvirt.VIR_DOMAIN_RUNNING:
            logger.verbose('sliver_libvirt: %s is RUNNING'%(dom.name()))
            return True
        else:
            info = debuginfo(dom)
            logger.verbose('sliver_libvirt: %s is NOT RUNNING...\n%s'%(dom.name(), info))
            return False
    except:
        print "Unexpected error:", sys.exc_info()

def debuginfo(dom):
    ''' Helper method to get a "nice" output of the info struct for debug'''
    [state, maxmem, mem, ncpu, cputime] = dom.info()
    return '%s is %s, maxmem = %s, mem = %s, ncpu = %s, cputime = %s' % (dom.name(), STATES.get(state, state), maxmem, mem, ncpu, cputime)


