#

"""LXC slivers"""

import accounts
import logger

class Sliver_LXC(accounts.Account):
    """This class wraps LXC commands"""

    SHELL = '/bin/bash'
    TYPE = 'sliver.LXC'
    # Need to add a tag at myplc to actually use this account
    # type = 'sliver.LXC'

    def __init__(self, rec):
        print "TODO WIP __init__"
        name=rec['name']
        logger.verbose ('sliver_lxc: %s init'%name)
    
    @staticmethod
    def create(name, rec = None):
        print "TODO create"
        
    @staticmethod
    def destroy(name):
        print "TODO destroy"

    def configure(self, rec):
        ''' Called by accounts.ensure_created -> start -> _acct.configure '''
        print "TODO configure" 
        name=rec['name']

    def start(self, delay=0):
        print "TODO start"
    
    def stop(self):
        print "TODO stop"
    
    def is_running(self):
        print "TODO is_running"
        return True

    
