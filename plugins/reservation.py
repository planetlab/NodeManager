# $Id$
# $URL$
#
# NodeManager plugin - first step of handling reservable nodes

"""
Manages running slices when reservation_policy is 'lease_or_idle' or 'lease_or_shared'
"""

import time
import threading

import logger

priority = 45

# this instructs nodemanager that we want to use the latest known data in case the plc link is down
persistent_data = True

# of course things would be simpler if node manager was to create one instance of the plugins 
# instead of blindly caling functions in the module...

##############################
# rough implementation for a singleton class
def Singleton (klass,*args,**kwds):
    if not hasattr(klass,'_instance'):
        klass._instance=klass(*args,**kwds)
    return klass._instance

def start(options, conf):
    return Singleton(reservation).start(options,conf)

def GetSlivers(data, conf = None, plc = None):
    return Singleton(reservation).GetSlivers(data, conf, plc)

##############################
class reservation:

    def __init__ (self):
        # the last snapshot of data exposed by GetSlivers
        self.data = None
        # this is a dict mapping a raounded timestamp to the corr. Timer object
        self.timers = {}
 
    # the granularity is set in the API (initial value is 15 minutes)
    # and it used to round all leases start/until times
    # changing this dynamically can have some weird effects of course..
    def granularity (self):
        try:
            return self.data['lease_granularity']
        # in case we'd try to access this before it's populated..
        except:
            return 60*60

    # round to granularity
    def round_time (self, time):
        granularity=self.granularity()
        return ((int(time)+granularity/2)/granularity)*granularity

    def clear_timers (self):
        for timer in self.timers.values():
            timer.cancel()
        self.timers={}

    def clear_timer (self,timestamp):
        round=self.round_time(timestamp)
        if self.timers.has_key(round):
            timer=self.timers[round]
            timer.cancel()
            del self.timers[round]

    def sync_timers_from_leases (self):
        self.clear_timers()
        for lease in self.data['leases']:
            self.ensure_timer(lease['t_from'])
            self.ensure_timer(lease['t_until'])

    def ensure_timer(self, timestamp):
        now=time.time()
        # forget about past events
        if timestamp < now: return
        round=self.round_time(timestamp)
        if self.timers.has_key(round): return
        def this_closure ():
            self.round_time_callback (round)
        timer=threading.Timer(timestamp-now,this_closure)
        self.timers[round]=timer
        timer.start()

    def round_time_callback (self, time_arg):
        now=time.time()
        round_now=self.round_time(now)
        logger.log('reservation.round_time_callback now=%f round_now=%d arg=%d...'%(now,round_now,time_arg))
        leases_text="leases=%r"%self.data['leases']
        logger.log(leases_text)

    def show_time (self, timestamp):
        return time.strftime ("%Y-%m-%d %H:%M %Z",time.gmtime(timestamp))

    ####################
    def start(self,options,conf):
        logger.log("reservation: plugin performing dummy start...")

    # this method is entirely about making sure that we have events scheduled 
    # at the <granularity> intervals where there is a lease that starts or ends
    def GetSlivers (self, data, conf=None, plc=None):
    
        # check we're using a compliant GetSlivers
        if 'reservation_policy' not in data: 
            logger.log_missing_data("reservation.GetSlivers",'reservation_policy')
            return
        reservation_policy=data['reservation_policy']
        if 'leases' not in data: 
            logger.log_missing_data("reservation.GetSlivers",'leases')
            return
    

        # store data locally
        # since we've asked for persistent_data, we should not get an empty data here
        if data: self.data = data

        # regular nodes are not affected
        if reservation_policy == 'none':
            return
        elif reservation_policy not in ['lease_or_idle','lease_or_shared']:
            logger.log("reservation: ignoring -- unexpected value for reservation_policy %r"%reservation_policy)
            return
        # at this point we have reservation_policy in ['lease_or_idle','lease_or_shared']
        # we make no difference for now
        logger.verbose('reservation.GetSlivers : reservable node -- listing timers ')
        
        self.sync_timers_from_leases()
        for timestamp in self.timers.keys():
            logger.verbose('TIMER armed for %s'%self.show_time(timestamp))
           
        logger.verbose('reservation.GetSlivers : end listing timers')
        
