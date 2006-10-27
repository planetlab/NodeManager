"""Delegate accounts are used to provide secure access to the XMLRPC API.  They are normal Unix accounts with a shell that tunnels XMLRPC requests to the API server."""

import accounts
import logger
import tools


class Delegate(accounts.Account):
    SHELL = '/bin/forward_api_calls'  # tunneling shell
    TYPE = 'delegate'

    @staticmethod
    def create(name):
        add_shell(Delegate.SHELL)
        logger.log_call('/usr/sbin/useradd', '-p', '*', '-s', Delegate.SHELL, name)

    @staticmethod
    def destroy(name): logger.log_call('/usr/sbin/userdel', '-r', name)

def add_shell(shell):
    """Add <shell> to /etc/shells if it's not already there."""
    etc_shells = open('/etc/shells')
    valid_shells = etc_shells.read().split()
    etc_shells.close()
    if shell not in valid_shells:
        etc_shells = open('/etc/shells', 'a')
        print >>etc_shells, shell
        etc_shells.close()
