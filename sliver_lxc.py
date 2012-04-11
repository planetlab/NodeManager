#

"""LXC slivers"""

import accounts
import logger
import subprocess
import os
import libvirt
import sys
from string import Template
import bwlimit
import sliver_libvirt as lv

class Sliver_LXC(lv.Sliver_Libvirt):
    """This class wraps LXC commands"""

    SHELL = '/bin/sshsh'
    TYPE = 'sliver.LXC'
    # Need to add a tag at myplc to actually use this account
    # type = 'sliver.LXC'

    REF_IMG_BASE_DIR = '/vservers/.lvref'
    CON_BASE_DIR     = '/vservers'

    @staticmethod
    def create(name, rec=None):
        ''' Create dirs, copy fs image, lxc_create '''
        logger.verbose ('sliver_lxc: %s create'%(name))
        conn = lv.getConnection(Sliver_LXC.TYPE)

        # Get the type of image from vref myplc tags specified as:
        # pldistro = lxc
        # fcdistro = squeeze
        # arch x86_64
        vref = rec['vref']
        if vref is None:
            logger.log('sliver_libvirt: %s: WARNING - no vref attached defaults to lxc-f14' % (name))
            vref = "lxc-f14-x86_64"

        refImgDir    = os.path.join(Sliver_LXC.REF_IMG_BASE_DIR, vref)
        containerDir = os.path.join(Sliver_LXC.CON_BASE_DIR, name)

        # check the template exists -- there's probably a better way..
        if not os.path.isdir(refImgDir):
            logger.log('sliver_lxc: %s: ERROR Could not create sliver - reference image %s not found' % (name,vref))
            logger.log('sliver_lxc: %s: ERROR ctd expected reference image in %s'%(name,refImgDir))
            return

        # Snapshot the reference image fs (assume the reference image is in its own
        # subvolume)
        command = ['btrfs', 'subvolume', 'snapshot', refImgDir, containerDir]
        logger.log_call(command, timeout=15*60)
        command = ['chmod', '755', containerDir]
        logger.log_call(command, timeout=15*60)

        # TODO: set quotas...

        # Set hostname. A valid hostname cannot have '_'
        #with open(os.path.join(containerDir, 'etc/hostname'), 'w') as f:
        #    print >>f, name.replace('_', '-')

        # Add slices group if not already present
        command = ['/usr/sbin/groupadd', 'slices']
        logger.log_call(command, timeout=15*60)

        # Add unix account (TYPE is specified in the subclass)
        command = ['/usr/sbin/useradd', '-g', 'slices', '-s', Sliver_LXC.SHELL, name, '-p', '*']
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

        command = ['mkdir', '%s/root/.ssh'%containerDir]
        logger.log_call(command, timeout=15*60)

        command = ['cp', '/home/%s/.ssh/id_rsa.pub'%name, '%s/root/.ssh/authorized_keys'%containerDir]
        logger.log_call(command, timeout=15*60)

        # Lookup for xid and create template after the user is created so we
        # can get the correct xid based on the name of the slice
        xid = bwlimit.get_xid(name)

        # Template for libvirt sliver configuration
        try:
            with open(Sliver_LXC.REF_IMG_BASE_DIR + '/config_template.xml') as f:
                template = Template(f.read())
                xml  = template.substitute(name=name, xid=xid)
        except IOError:
            logger.log('Cannot find XML template file')
            return

        # Lookup for the sliver before actually
        # defining it, just in case it was already defined.
        try:
            dom = conn.lookupByName(name)
        except:
            dom = conn.defineXML(xml)
        logger.verbose('lxc_create: %s -> %s'%(name, lv.debuginfo(dom)))


    @staticmethod
    def destroy(name):
        logger.verbose ('sliver_lxc: %s destroy'%(name))
        conn = lv.getConnection(Sliver_LXC.TYPE)

        containerDir = Sliver_LXC.CON_BASE_DIR + '/%s'%(name)

        try:
            # Destroy libvirt domain
            dom = conn.lookupByName(name)
        except:
            logger.verbose('sliver_lxc: Domain %s does not exist! UNEXPECTED'%name)
            return

        try:
            dom.destroy()
        except:
            logger.verbose('sliver_lxc: Domain %s not running... continuing.'%name)

        dom.undefine()

        # Remove user after destroy domain to force logout
        command = ['/usr/sbin/userdel', '-f', '-r', name]
        logger.log_call(command, timeout=15*60)

        # Remove rootfs of destroyed domain
        command = ['btrfs', 'subvolume', 'delete', containerDir]
        logger.log_call(command, timeout=15*60)

        logger.verbose('sliver_libvirt: %s destroyed.'%name)

