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
import accounts

# there is an implicit assumption that this triggers after slicemanager
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

    debug=False
    debug=True

    def __init__ (self):
        # the last snapshot of data exposed by GetSlivers
        self.data = None
        # this is a dict mapping a raounded timestamp to the corr. Timer object
        self.timers = {}
 
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
        if reservation.debug:
            self.list_timers()

    ####################
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

    def sync_timers_from_leases (self):
        self.clear_timers()
        for lease in self.data['leases']:
            self.ensure_timer(lease['t_from'])
            self.ensure_timer(lease['t_until'])

    def list_timers(self):
        timestamps=self.timers.keys()
        timestamps.sort()
        for timestamp in timestamps:
            logger.verbose('reservation: TIMER armed for %s'%reservation.time_printable(timestamp))
        logger.verbose('reservation.GetSlivers : end listing timers')

    def ensure_timer(self, timestamp):
        now=time.time()
        # forget about past events
        if timestamp < now: return
        round=self.round_time(timestamp)
        if round in self.timers: return
        def this_closure ():
            self.granularity_callback (round)
        timer=threading.Timer(timestamp-now,this_closure)
        self.timers[round]=timer
        timer.start()

    
    @staticmethod
    def time_printable (timestamp):
        return time.strftime ("%Y-%m-%d %H:%M UTC",time.gmtime(timestamp))

    @staticmethod
    def lease_printable (lease):
        d=dict ( lease.iteritems())
        d['from']=reservation.time_printable(lease['t_from'])
        d['until']=reservation.time_printable(lease['t_from'])
        s=[]
        s.append("slice=%(name)s (%(slice_id)d)"%d)
        s.append("from %(from)s"%d)
        s.append("until %(until)s"%d)
        return " ".join(s)

    # this is invoked at the granularity boundaries where something happens (a lease ends or/and a lease starts)
    def granularity_callback (self, time_arg):
        now=time.time()
        round_now=self.round_time(now)
        leases=self.data['leases']
        ###
        if reservation.debug:
            logger.verbose('reservation.granularity_callback now=%f round_now=%d arg=%d...'%(now,round_now,time_arg))
        if leases and reservation.debug:
            logger.verbose('reservation: Listing leases beg')
            for lease in leases:
                logger.verbose("reservation: lease="+reservation.lease_printable(lease))
            logger.verbose('reservation: Listing leases end')

        ### what do we have to do at this point in time?
        ending_lease=None
        for lease in leases:
            if lease['t_until']==round_now:
                logger.verbose('reservation: end of lease for slice %s - (lease=%s)'%(lease['name'],reservation.lease_printable(lease)))
                ending_lease=lease
        starting_lease=None
        for lease in leases:
            if lease['t_from']==round_now:
                logger.verbose('reservation: start of lease for slice %s - (lease=%s)'%(lease['name'],reservation.lease_printable(lease)))
                starting_lease=lease

        ## sanity check
        if not ending_lease and not starting_lease:
            logger.log("reservation.granularity_callback: unexpected void event")
            return

        ## leases end and restart, about the same sliver
        if ending_lease and starting_lease and ending_lease['name']==starting_lease['name']:
            slicename=ending_lease['name']
            if self.is_running(slicename):
                logger.log("reservation.granularity_callback: end/start of same sliver %s -- ignored"%ending_lease['name'])
                return
            else:
                logger.log("reservation.granularity_callback: mmh, the sliver is unexpectedly not running, starting it...")
                self.restart_slice(slicename)

        # otherwise things are simple
        if ending_lease: self.suspend_slice (ending_lease['name'])
        if starting_lease: self.restart_slice (starting_lease['name'])

    def debug_box(self,message,slicename=None):
        if reservation.debug:
            logger.verbose ('reservation: '+message)
            logger.log_call( ['/usr/sbin/vserver-stat', ] )
            if slicename:
                logger.log_call ( ['/usr/sbin/vserver',slicename,'status', ])
        
    def is_running (self, slicename):
        try:
            return accounts.get(slicename).is_running()
        except:
            return False

    # quick an d dirty - this does not obey the accounts/sliver_vs/controller hierarchy 
    def suspend_slice(self, slicename):
        logger.log('reservation: Suspending slice %s'%(slicename))
        self.debug_box('before suspending',slicename)
        worker=accounts.get(slicename)
        try:
            logger.verbose("reservation: Located worker object %r"%worker)
            worker.stop()
        except:
            logger.log_exc("reservation.suspend_slice: Could not stop slice %s through its worker"%slicename)
        # we hope the status line won't return anything
        self.debug_box('after suspending',slicename)
                
    def restart_slice(self, slicename):
        logger.log('reservation: Restarting slice %s'%(slicename))
        self.debug_box('before restarting',slicename)
        worker=accounts.get(slicename)
        try:
            # dig in self.data to retrieve corresponding rec
            slivers = [ sliver for sliver in self.data.slivers if sliver['name']==slicename ]
            sliver=slivers[0]
            
            # 
            logger.verbose("reservation: Located worker object %r"%worker)
            worker.start(rec)
        except:
            logger.log_exc("reservation.restart_slice: Could not start slice %s through its worker"%slicename)
        # we hope the status line won't return anything
        self.debug_box('after restarting',slicename)
        
