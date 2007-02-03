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

#import socket
#import xmlrpclib
#import bwlimit

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
default_maxrate = bwlimit.get_bwcap()
default_maxi2rate = bwlimit.bwmax
default_MinRate = 8

# What we cap to when slices break the rules.
# 500 Kbit or 5.4 GB per day
#default_avgrate = 500000
# 1.5 Mbit or 16.4 GB per day
#default_avgexemptrate = 1500000

# 5.4 Gbyte per day. 5.4 * 1024 k * 1024M * 1024G 
# 5.4 Gbyte per day max allowed transfered per recording period
default_ByteMax = 5798205850
default_ByteThresh = int(.8 * default_ByteMax) 
# 16.4 Gbyte per day max allowed transfered per recording period to I2
default_ExemptByteMax = 17609365914 
default_ExemptByteThresh = int(.8 * default_ExemptByteMax) 


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

    def __init__(self, xid, name, maxrate, maxexemptrate, bytes, exemptbytes):
        self.xid = xid
        self.name = name
        self.time = 0
        self.bytes = 0
        self.i2bytes = 0
		self.MaxRate = default_maxrate
		self.MinRate = default_MinRate
		self.Mini2Rate = default_MinRate
		self.Maxi2Rate = default_maxi2rate
        self.MaxKByte = default_ByteMax
        self.ThreshKByte = default_ByteThresh
        self.Maxi2KByte = default_ExemptByteMax
        self.Threshi2KByte = default_ExemptByteThresh
        self.emailed = False

        # Get real values where applicable
        self.reset(maxrate, maxi2rate, bytes, i2bytes)

    def __repr__(self):
        return self.name

    def updateSliceAttributes(self, data):
		
		for sliver in data['slivers']:
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
					self.M = attribute['value']
				elif attribute['name'] == 'net_i2_max_kbyte':	
					self.minrate = attribute['value']
				elif attribute['name'] == 'net_thresh_kbyte':	
					self.minrate = attribute['value']
				elif attribute['name'] == 'net_i2_thresh_kbyte':	
					self.minrate = attribute['value']

    def reset(self, maxrate, maxi2rate, bytes, i2bytes):
        """
        Begin a new recording period. Remove caps by restoring limits
        to their default values.
        """
        
        # Query Node Manager for max rate overrides
        self.updateSliceAttributes()    

        # Reset baseline time
        self.time = time.time()

        # Reset baseline byte coutns
        self.bytes = bytes
        self.i2bytes = exemptbytes

        # Reset email 
        self.emailed = False

		# Reset rates.
        if (self.MaxRate != maxrate) or (self.Maxi2Rate != maxi2rate):
            print "%s reset to %s/%s" % \
                  (self.name,
                   bwlimit.format_tc_rate(self.MaxRate),
                   bwlimit.format_tc_rate(self.Maxi2Rate))
            bwlimit.set(xid = self.xid, maxrate = self.MaxRate, maxexemptrate = self.Maxi2Rate)

    def update(self, maxrate, maxi2rate, bytes, ibytes):
        """
        Update byte counts and check if byte limits have been
        exceeded. 
        """
    
        # Query Node Manager for max rate overrides
        self.updateSliceAttributes()    
     
        # Prepare message parameters from the template
        message = ""
        params = {'slice': self.name, 'hostname': socket.gethostname(),
                  'since': time.asctime(time.gmtime(self.time)) + " GMT",
                  'until': time.asctime(time.gmtime(self.time + period)) + " GMT",
                  'date': time.asctime(time.gmtime()) + " GMT",
                  'period': format_period(period)} 

        if bytes >= (self.bytes + self.ByteThresh):
            new_maxrate = \
            int(((self.ByteMax - (bytes - self.bytes)) * 8)/(period - int(time.time() - self.time)))
            if new_maxrate < default_MinRate:
                new_maxrate = default_MinRate
        else:
            new_maxrate = maxrate

        # Format template parameters for low bandwidth message
        params['class'] = "low bandwidth"
        params['bytes'] = format_bytes(bytes - self.bytes)
        params['maxrate'] = bwlimit.format_tc_rate(maxrate)
        params['limit'] = format_bytes(self.ByteMax)
        params['new_maxrate'] = bwlimit.format_tc_rate(new_maxrate)

        if verbose:
            print "%(slice)s %(class)s " \
                  "%(bytes)s of %(limit)s (%(new_maxrate)s/s maxrate)" % \
                  params

        # Cap low bandwidth burst rate
        if new_maxrate != maxrate:
            message += template % params
            print "%(slice)s %(class)s capped at %(new_maxrate)s/s " % params
    
        if exemptbytes >= (self.exemptbytes + self.ExemptByteThresh):
            new_maxexemptrate = \
            int(((self.ExemptByteMax - (self.bytes - bytes)) * 8)/(period - int(time.time() - self.time)))
            if new_maxexemptrate < default_MinRate:
                new_maxexemptrate = default_MinRate
        else:
            new_maxexemptrate = maxexemptrate

        # Format template parameters for high bandwidth message
        params['class'] = "high bandwidth"
        params['bytes'] = format_bytes(exemptbytes - self.exemptbytes)
        params['maxrate'] = bwlimit.format_tc_rate(maxexemptrate)
        params['limit'] = format_bytes(self.ExemptByteMax)
        params['new_maxexemptrate'] = bwlimit.format_tc_rate(new_maxexemptrate)

        if verbose:
            print "%(slice)s %(class)s " \
                  "%(bytes)s of %(limit)s (%(new_maxrate)s/s maxrate)" % params

        # Cap high bandwidth burst rate
        if new_maxexemptrate != maxexemptrate:
            message += template % params
            print "%(slice)s %(class)s capped at %(new_maxexemptrate)s/s" % params

        # Apply parameters
        if new_maxrate != maxrate or new_maxexemptrate != maxexemptrate:
            bwlimit.set(xid = self.xid, maxrate = new_maxrate, maxexemptrate = new_maxexemptrate)

        # Notify slice
        if message and self.emailed == False:
            subject = "pl_mom capped bandwidth of slice %(slice)s on %(hostname)s" % params
            if debug:
                print subject
                print message + (footer % params)
            else:
                self.emailed = True
                slicemail(self.name, subject, message + (footer % params))

def main():
    # Defaults
    global datafile, period
    # All slices
    names = []
    # Check if we are already running
    writepid("bwmon")

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

    live = []
    # Get actuall running values from tc.
    for params in bwlimit.get():
        (xid, share,
         minrate, maxrate,
         minexemptrate, maxexemptrate,
         bytes, i2bytes) = params
        live.append(xid)

        # Ignore root and default buckets
        if xid == root_xid or xid == default_xid:
            continue

        name = bwlimit.get_slice(xid)
        if name is None:
            # Orphaned (not associated with a slice) class
            name = "%d?" % xid

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
                slice.reset(maxrate, maxexemptrate, bytes, exemptbytes)
            else:
                # Update byte counts
                slice.update(maxrate, maxexemptrate, bytes, exemptbytes)
        else:
            # New slice, initialize state
            slice = slices[xid] = Slice(xid, name, maxrate, maxexemptrate, bytes, exemptbytes)

    # Delete dead slices
    dead = Set(slices.keys()) - Set(live)
    for xid in dead:
        del slices[xid]

    if verbose:
        print "Saving %s" % datafile
    f = open(datafile, "w")
    pickle.dump((version, slices), f)
    f.close()



def GetSlivers(data):
    for sliver in data['slivers']:
        if sliver.has_key('attributes'):
            print sliver
            for attribute in sliver['attributes']:
                if attribute['name'] == "KByteThresh": print attribute['value']

def start(options, config):
    pass


if __name__ == '__main__':
    main()
