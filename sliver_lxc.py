#

"""LXC slivers"""

class Sliver_LXC(accounts.Account):
    """This class wraps LXC commands"""

    SHELL = '/bin/bash'
    TYPE = 'sliver.LXC'

    def __init__(self):
        pass
    
    @staticmethod
    def create(name, rec = None):
        print "TODO create"
        
    @staticmethod
    def destroy(name):
        print "TODO destroy"

    def start(self, delay=0):
        print "TODO start"
    
    def stop(self):
        print "TODO stop"
    
    def is_running(self):
        print "TODO is_running"

    
