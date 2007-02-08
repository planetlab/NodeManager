#!/usr/bin/python
#
# Average bandwidth monitoring script. Run periodically via cron(8) to
# enforce a soft limit on daily bandwidth usage for each slice. If a
# slice is found to have exceeded its daily bandwidth usage when the
# script is run, its instantaneous rate will be capped at the desired
# average rate. Thus, in the worst case, a slice will only be able to
# send a little more than twice its average daily limit.
#
# Two separate limits are enforced, one for destinations exempt from
# the node bandwidth cap, and the other for all other destinations.
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Andy Bavier <acb@cs.princeton.edu>
# Faiyaz Ahmed <faiyaza@cs.princeton.edu>
# Copyright (C) 2004-2006 The Trustees of Princeton University
#
# $Id: bwmon.py,v 1.20 2007/01/10 16:51:04 faiyaza Exp $
#

import os
import sys
import time
import pickle
import database

#import socket
#import xmlrpclib
import bwlimit

from sets import Set

# Utility functions
#from pl_mom import *

# Constants
seconds_per_day = 24 * 60 * 60
bits_per_byte = 8

# Defaults
debug = False
verbose = 0
datafile = "/var/lib/misc/bwmon.dat"
#nm = None

# Burst to line rate (or node cap).  Set by NM.
default_MaxRate = bwlimit.get_bwcap()
default_Maxi2Rate = bwlimit.bwmax
# Min rate 8 bits/s 
default_MinRate = 0
# 5.4 Gbyte per day. 5.4 * 1024 k * 1024M * 1024G 
# 5.4 Gbyte per day max allowed transfered per recording period
default_MaxKByte = 5662310
default_ThreshKByte = int(.8 * default_MaxKByte) 
# 16.4 Gbyte per day max allowed transfered per recording period to I2
default_Maxi2KByte = 17196646
default_Threshi2KByte = int(.8 * default_Maxi2KByte) 
# Default share quanta
default_Share = 1

# Average over 1 day
period = 1 * seconds_per_day

# Message template
template = \
"""
The slice %(slice)s has transmitted more than %(bytes)s from
%(hostname)s to %(class)s destinations
since %(since)s.

Its maximum %(class)s burst rate will be capped at %(new_maxrate)s/s
until %(until)s.

Please reduce the average %(class)s transmission rate
of the slice to %(limit)s per %(period)s.

""".lstrip()

footer = \
"""
%(date)s %(hostname)s bwcap %(slice)s
""".lstrip()

class Slice:
    """
    Stores the last recorded bandwidth parameters of a slice.

    xid - slice context/VServer ID
    name - slice name
    time - beginning of recording period in UNIX seconds
    bytes - low bandwidth bytes transmitted at the beginning of the recording period
    i2bytes - high bandwidth bytes transmitted at the beginning of the recording period (for I2 -F)
    ByteMax - total volume of data allowed
    ByteThresh - After thresh, cap node to (maxbyte - bytes)/(time left in period)
    ExemptByteMax - Same as above, but for i2.
    ExemptByteThresh - i2 ByteThresh
    maxrate - max_rate slice attribute. 
    maxexemptrate - max_exempt_rate slice attribute.
    self.emailed = did we email during this recording period

    """

    def __init__(self, xid, name, maxrate, maxi2rate, bytes, i2bytes, data):
        self.xid = xid
        self.name = name
        self.time = 0
        self.bytes = 0
        self.i2bytes = 0
        self.MaxRate = default_MaxRate
        self.MinRate = default_MinRate
        self.Maxi2Rate = default_Maxi2Rate
        self.MaxKByte = default_MaxKByte
        self.ThreshKByte = default_ThreshKByte
        self.Maxi2KByte = default_Maxi2KByte
        self.Threshi2KByte = default_Threshi2KByte
        self.Share = default_Share
        self.emailed = False

        # Get real values where applicable
        self.reset(maxrate, maxi2rate, bytes, i2bytes, data)

    def __repr__(self):
        return self.name

    @database.synchronized
    def updateSliceAttributes(self, data):
        for sliver in data['slivers']:
            if sliver['name'] == self.name:    
                for attribute in sliver['attributes']:
                    if attribute['name'] == 'net_min_rate':        
                        self.MinRate = attribute['value']
                    elif attribute['name'] == 'net_max_rate':        
                        self.MaxRate = attribute['value']
                    elif attribute['name'] == 'net_i2_min_rate':
                        self.Mini2Rate = attribute['value']
                    elif attribute['name'] == 'net_i2_max_rate':        
                        self.Maxi2Rate = attribute['value']
                    elif attribute['name'] == 'net_max_kbyte':        
                        self.MaxKbyte = attribute['value']
                    elif attribute['name'] == 'net_i2_max_kbyte':    
                        self.Maxi2KByte = attribute['value']
                    elif attribute['name'] == 'net_thresh_kbyte':    
                        self.ThreshKByte = attribute['value']
                    elif attribute['name'] == 'net_i2_thresh_kbyte':    
                        self.Threshi2KByte = attribute['value']
                    elif attribute['name'] == 'net_share':    
                        self.Share = attribute['value']
                    elif attribute['name'] == 'net_i2_share':    
                        self.Sharei2 = attribute['value']

    def reset(self, runningmaxrate, runningmaxi2rate, usedbytes, usedi2bytes, data):
        """
        Begin a new recording period. Remove caps by restoring limits
        to their default values.
        """
        
        # Query Node Manager for max rate overrides
        self.updateSliceAttributes(data)    

        # Reset baseline time
        self.time = time.time()

        # Reset baseline byte coutns
        self.bytes = usedbytes
        self.i2bytes = usedi2bytes

        # Reset email 
        self.emailed = False

        # Reset rates.
        if (self.MaxRate != runningmaxrate) or (self.Maxi2Rate != runningmaxi2rate):
            print "%s reset to %s/%s" % \
                  (self.name,
                   bwlimit.format_tc_rate(self.MaxRate),
                   bwlimit.format_tc_rate(self.Maxi2Rate))
            bwlimit.set(xid = self.xid, 
                minrate = self.MinRate, 
                maxrate = self.MaxRate, 
                maxexemptrate = self.Maxi2Rate,
                minexemptrate = self.Mini2Rate,
                share = self.Share)

    def update(self, runningmaxrate, runningmaxi2rate, usedbytes, usedi2bytes, data):
        """
        Update byte counts and check if byte limits have been
        exceeded. 
        """
    
        # Query Node Manager for max rate overrides
        self.updateSliceAttributes(data)    
     
        # Prepare message parameters from the template
        message = ""
        params = {'slice': self.name, 'hostname': socket.gethostname(),
                  'since': time.asctime(time.gmtime(self.time)) + " GMT",
                  'until': time.asctime(time.gmtime(self.time + period)) + " GMT",
                  'date': time.asctime(time.gmtime()) + " GMT",
                  'period': format_period(period)} 

        if usedi2bytes >= (self.usedbytes + self.ByteThresh):
            maxbyte = self.MaxKByte * 1024
            bytesused = bytes - self.bytes
            timeused = int(time.time() - self.time)
            new_maxrate = int(((maxbyte - bytesused) * 8)/(period - timeused))
            if new_maxrate < self.MinRate:
                new_maxrate = self.MinRate
        else:
            new_maxrate = self.MaxRate 

        # Format template parameters for low bandwidth message
        params['class'] = "low bandwidth"
        params['bytes'] = format_bytes(usedbytes - self.bytes)
        params['maxrate'] = bwlimit.format_tc_rate(runningmaxrate)
        params['limit'] = format_bytes(self.MaxKByte)
        params['new_maxrate'] = bwlimit.format_tc_rate(new_maxrate)

        if verbose:
            print "%(slice)s %(class)s " \
                  "%(bytes)s of %(limit)s (%(new_maxrate)s/s maxrate)" % \
                  params

        # Cap low bandwidth burst rate
        if new_maxrate != runningmaxrate:
            message += template % params
            print "%(slice)s %(class)s capped at %(new_maxrate)s/s " % params
    
        if usedi2bytes >= (self.i2bytes + self.Threshi2KBytes):
            maxi2byte = self.Maxi2KByte * 1024
            i2bytesused = i2bytes - self.i2bytes
            timeused = int(time.time() - self.time)
            new_maxi2rate = int(((maxi2byte - i2bytesused) * 8)/(period - timeused))
            if new_maxi2rate < self.Mini2Rate:
                new_maxi2rate = self.Mini2Rate
        else:
            new_maxi2rate = self.Maxi2Rate 

        # Format template parameters for high bandwidth message
        params['class'] = "high bandwidth"
        params['bytes'] = format_bytes(usedi2bytes - self.i2bytes)
        params['maxrate'] = bwlimit.format_tc_rate(runningmaxi2rate)
        params['limit'] = format_bytes(self.Maxi2KByte)
        params['new_maxexemptrate'] = bwlimit.format_tc_rate(new_maxi2rate)

        if verbose:
            print "%(slice)s %(class)s " \
                  "%(bytes)s of %(limit)s (%(new_maxrate)s/s maxrate)" % params

        # Cap high bandwidth burst rate
        if new_maxi2rate != runningmaxi2rate:
            message += template % params
            print "%(slice)s %(class)s capped at %(new_maxexemptrate)s/s" % params

        # Apply parameters
        if new_maxrate != runningmaxrate or new_maxi2rate != runningmaxi2rate:
            bwlimit.set(xid = self.xid, maxrate = new_maxrate, maxexemptrate = new_maxi2rate)

        # Notify slice
        if message and self.emailed == False:
            subject = "pl_mom capped bandwidth of slice %(slice)s on %(hostname)s" % params
            if debug:
                print subject
                print message + (footer % params)
            else:
                self.emailed = True
                slicemail(self.name, subject, message + (footer % params))

def GetSlivers(data):
    # Defaults
    global datafile, \
        period, \
	    default_MaxRate, \
	    default_Maxi2Rate, \
	    default_MinRate, \
	    default_MaxKByte,\
	    default_ThreshKByte,\
        default_Maxi2KByte,\
        default_Threshi2KByte,\
        default_Share

    # All slices
    names = []

    try:
        f = open(datafile, "r+")
        if verbose:
            print "Loading %s" % datafile
        (version, slices) = pickle.load(f)
        f.close()
        # Check version of data file
        if version != "$Id: bwmon.py,v 1.20 2007/01/10 16:51:04 faiyaza Exp $":
            print "Not using old version '%s' data file %s" % (version, datafile)
            raise Exception
    except Exception:
        version = "$Id: bwmon.py,v 1.20 2007/01/10 16:51:04 faiyaza Exp $"
        slices = {}

    # Get special slice IDs
    root_xid = bwlimit.get_xid("root")
    default_xid = bwlimit.get_xid("default")

	# {name: xid}
    live = {}
	for sliver in data['slivers']:
		live[sliver['name']] = bwlimit.get_xid(sliver['name'])

    # Get actuall running values from tc.
    for params in bwlimit.get():
        (xid, share,
         minrate, maxrate,
         minexemptrate, maxexemptrate,
         bytes, i2bytes) = params

        # Ignore root and default buckets
        if xid == root_xid or xid == default_xid:
            continue

        name = bwlimit.get_slice(xid)
        if name is None:
            # Orphaned (not associated with a slice) class
            name = "%d?" % xid
            bwlimit.off(xid)

        # Monitor only the specified slices
        if names and name not in names:
            continue
        #slices is populated from the pickle file
        #xid is populated from bwlimit (read from /etc/passwd) 
        if slices.has_key(xid):
            slice = slices[xid]
            if time.time() >= (slice.time + period) or \
               bytes < slice.bytes or i2bytes < slice.i2bytes:
                # Reset to defaults every 24 hours or if it appears
                # that the byte counters have overflowed (or, more
                # likely, the node was restarted or the HTB buckets
                # were re-initialized).
                slice.reset(maxrate, maxexemptrate, bytes, i2bytes, data)
            else:
                # Update byte counts
                slice.update(maxrate, maxexemptrate, bytes, i2bytes, data)
        else:
            # New slice, initialize state
            slice = slices[xid] = Slice(xid, name, maxrate, maxexemptrate, bytes, i2bytes, data)

    # Delete dead slices
    dead = Set(slices.keys()) - Set(live.values())
    for xid in dead:
        del slices[xid]
        bwlimit.off(xid)

    print "Saving %s" % datafile
    f = open(datafile, "w")
    pickle.dump((version, slices), f)
    f.close()


#def GetSlivers(data):
#    for sliver in data['slivers']:
#        if sliver.has_key('attributes'):
#           print sliver
#            for attribute in sliver['attributes']:
#                if attribute['name'] == "KByteThresh": print attribute['value']

def start(options, config):
    pass

if __name__ == '__main__':
    main()
