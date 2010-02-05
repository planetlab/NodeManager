# $Id$
# $URL$

"""Delegate accounts are used to provide secure access to the XMLRPC API.  They are normal Unix accounts with a shell that tunnels XMLRPC requests to the API server."""

import accounts
import logger
import tools
from pwd import getpwnam
from grp import getgrnam

class Controller(accounts.Account):
    SHELL = '/usr/bin/forward_api_calls'  # tunneling shell
    TYPE = 'controller.Controller'

    @staticmethod
    def create(name, vref = None):
        add_shell(Controller.SHELL)
        group = getgrnam("slices")[2]
        logger.log_call('/usr/sbin/useradd', '-p', '*', '-g', str(group), '-s', Controller.SHELL, name)

    @staticmethod
    def destroy(name): logger.log_call('/usr/sbin/userdel', '-r', name)

    def is_running(self):
        logger.verbose("controller: is_running:  %s" % self.name)
        return getpwnam(self.name)[6] == self.SHELL
    

def add_shell(shell):
    """Add <shell> to /etc/shells if it's not already there."""
    etc_shells = open('/etc/shells')
    valid_shells = etc_shells.read().split()
    etc_shells.close()
    if shell not in valid_shells:
        etc_shells = open('/etc/shells', 'a')
        print >>etc_shells, shell
        etc_shells.close()
