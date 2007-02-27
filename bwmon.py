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
# $Id: bwmon.py,v 1.10 2007/02/27 23:03:58 faiyaza Exp $
#

import os
import sys
import time
import pickle

import socket
#import xmlrpclib
import bwlimit
import logger

from sets import Set
try:
    sys.path.append("/etc/planetlab")
    from plc_config import *
except:
    logger.log("bwmon:  Warning: Configuration file /etc/planetlab/plc_config.py not found")
    PLC_NAME = "PlanetLab"
    PLC_SLICE_PREFIX = "pl"
    PLC_MAIL_SUPPORT_ADDRESS = "support@planet-lab.org"
    PLC_MAIL_SLICE_ADDRESS = "SLICE@slices.planet-lab.org"


# Utility functions
#from pl_mom import *

# Constants
seconds_per_day = 24 * 60 * 60
bits_per_byte = 8

# Defaults
debug = False 
verbose = False
datafile = "/var/lib/misc/bwmon.dat"
#nm = None

# Burst to line rate (or node cap).  Set by NM. in KBit/s
default_MaxRate = int(bwlimit.get_bwcap() / 1000)
default_Maxi2Rate = int(bwlimit.bwmax / 1000)
# Min rate 8 bits/s 
default_MinRate = 0
default_Mini2Rate = 0
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

def format_bytes(bytes, si = True):
    """
    Formats bytes into a string
    """
    if si:
        kilo = 1000.
    else:
        # Officially, a kibibyte
        kilo = 1024.

    if bytes >= (kilo * kilo * kilo):
        return "%.1f GB" % (bytes / (kilo * kilo * kilo))
    elif bytes >= 1000000:
        return "%.1f MB" % (bytes / (kilo * kilo))
    elif bytes >= 1000:
        return "%.1f KB" % (bytes / kilo)
    else:
        return "%.0f bytes" % bytes

def format_period(seconds):
    """
    Formats a period in seconds into a string
    """

    if seconds == (24 * 60 * 60):
        return "day"
    elif seconds == (60 * 60):
        return "hour"
    elif seconds > (24 * 60 * 60):
        return "%.1f days" % (seconds / 24. / 60. / 60.)
    elif seconds > (60 * 60):
        return "%.1f hours" % (seconds / 60. / 60.)
    elif seconds > (60):
        return "%.1f minutes" % (seconds / 60.)
    else:
        return "%.0f seconds" % seconds

def slicemail(slice, subject, body):
    sendmail = os.popen("/usr/sbin/sendmail -N never -t -f%s" % PLC_MAIL_SUPPORT_ADDRESS, "w")

    # PLC has a separate list for pl_mom messages
    if PLC_MAIL_SUPPORT_ADDRESS == "support@planet-lab.org":
        to = ["pl-mom@planet-lab.org"]
    else:
        to = [PLC_MAIL_SUPPORT_ADDRESS]

    if slice is not None and slice != "root":
        to.append(PLC_MAIL_SLICE_ADDRESS.replace("SLICE", slice))

    header = {'from': "%s Support <%s>" % (PLC_NAME, PLC_MAIL_SUPPORT_ADDRESS),
              'to': ", ".join(to),
              'version': sys.version.split(" ")[0],
              'subject': subject}

    # Write headers
    sendmail.write(
"""
Content-type: text/plain
From: %(from)s
Reply-To: %(from)s
To: %(to)s
X-Mailer: Python/%(version)s
Subject: %(subject)s

""".lstrip() % header)

    # Write body
    sendmail.write(body)
    # Done
    sendmail.close()


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

    def __init__(self, xid, name, data):
        self.xid = xid
        self.name = name
        self.time = 0
        self.bytes = 0
        self.i2bytes = 0
        self.MaxRate = default_MaxRate
        self.MinRate = default_MinRate
        self.Maxi2Rate = default_Maxi2Rate
        self.Mini2Rate = default_Mini2Rate
        self.MaxKByte = default_MaxKByte
        self.ThreshKByte = default_ThreshKByte
        self.Maxi2KByte = default_Maxi2KByte
        self.Threshi2KByte = default_Threshi2KByte
        self.Share = default_Share
        self.emailed = False

        self.updateSliceAttributes(data)
        bwlimit.set(xid = self.xid, 
                minrate = self.MinRate, 
                maxrate = self.MaxRate, 
                maxexemptrate = self.Maxi2Rate,
                minexemptrate = self.Mini2Rate,
                share = self.Share)


    def __repr__(self):
        return self.name

    def updateSliceAttributes(self, data):
        for sliver in data['slivers']:
            if sliver['name'] == self.name: 
                for attribute in sliver['attributes']:
                    if attribute['name'] == 'net_min_rate':     
                        logger.log("bwmon:  Updating %s. Min Rate = %s" \
                          %(self.name, self.MinRate))
                        # To ensure min does not go above 25% of nodecap.
                        if int(attribute['value']) > int(.25 * default_MaxRate):
                            self.MinRate = int(.25 * default_MaxRate)
                        else:    
                            self.MinRate = int(attribute['value'])
                    elif attribute['name'] == 'net_max_rate':       
                        self.MaxRate = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Max Rate = %s" \
                          %(self.name, self.MaxRate))
                    elif attribute['name'] == 'net_i2_min_rate':
                        self.Mini2Rate = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Min i2 Rate = %s" \
                          %(self.name, self.Mini2Rate))
                    elif attribute['name'] == 'net_i2_max_rate':        
                        self.Maxi2Rate = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Max i2 Rate = %s" \
                          %(self.name, self.Maxi2Rate))
                    elif attribute['name'] == 'net_max_kbyte':      
                        self.MaxKByte = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Max KByte lim = %s" \
                          %(self.name, self.MaxKByte))
                    elif attribute['name'] == 'net_i2_max_kbyte':   
                        self.Maxi2KByte = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Max i2 KByte = %s" \
                          %(self.name, self.Maxi2KByte))
                    elif attribute['name'] == 'net_thresh_kbyte':   
                        self.ThreshKByte = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Thresh KByte = %s" \
                          %(self.name, self.ThreshKByte))
                    elif attribute['name'] == 'net_i2_thresh_kbyte':    
                        self.Threshi2KByte = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. i2 Thresh KByte = %s" \
                          %(self.name, self.Threshi2KByte))
                    elif attribute['name'] == 'net_share':  
                        self.Share = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Net Share = %s" \
                          %(self.name, self.Share))
                    elif attribute['name'] == 'net_i2_share':   
                        self.Sharei2 = int(attribute['value'])
                        logger.log("bwmon:  Updating %s. Net i2 Share = %s" \
                          %(self.name, self.i2Share))


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
        maxrate = self.MaxRate * 1000 
        maxi2rate = self.Maxi2Rate * 1000 
        # Reset rates.
        if (self.MaxRate != runningmaxrate) or (self.Maxi2Rate != runningmaxi2rate):
            logger.log("bwmon:  %s reset to %s/%s" % \
                  (self.name,
                   bwlimit.format_tc_rate(maxrate),
                   bwlimit.format_tc_rate(maxi2rate)))
            bwlimit.set(xid = self.xid, 
                minrate = self.MinRate * 1000, 
                maxrate = self.MaxRate * 1000, 
                maxexemptrate = self.Maxi2Rate * 1000,
                minexemptrate = self.Mini2Rate * 1000,
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

        if usedbytes >= (self.bytes + (self.ThreshKByte * 1024)):
            maxbyte = self.MaxKByte * 1024
            bytesused = usedbytes - self.bytes
            timeused = int(time.time() - self.time)
            new_maxrate = int(((maxbyte - bytesused) * 8)/(period - timeused))
            if new_maxrate < (self.MinRate * 1000):
                new_maxrate = self.MinRate * 1000
        else:
            new_maxrate = self.MaxRate * 1000 

        # Format template parameters for low bandwidth message
        params['class'] = "low bandwidth"
        params['bytes'] = format_bytes(usedbytes - self.bytes)
        params['limit'] = format_bytes(self.MaxKByte * 1024)
        params['new_maxrate'] = bwlimit.format_tc_rate(new_maxrate)

        if verbose:
            logger.log("bwmon:  %(slice)s %(class)s " \
                  "%(bytes)s of %(limit)s (%(new_maxrate)s/s maxrate)" % \
                  params)

        # Cap low bandwidth burst rate
        if new_maxrate != runningmaxrate:
            message += template % params
            logger.log("bwmon:   ** %(slice)s %(class)s capped at %(new_maxrate)s/s " % params)
    
        if usedi2bytes >= (self.i2bytes + (self.Threshi2KByte * 1024)):
            maxi2byte = self.Maxi2KByte * 1024
            i2bytesused = usedi2bytes - self.i2bytes
            timeused = int(time.time() - self.time)
            new_maxi2rate = int(((maxi2byte - i2bytesused) * 8)/(period - timeused))
            if new_maxi2rate < (self.Mini2Rate * 1000):
                new_maxi2rate = self.Mini2Rate * 1000
        else:
            new_maxi2rate = self.Maxi2Rate * 1000

        # Format template parameters for high bandwidth message
        params['class'] = "high bandwidth"
        params['bytes'] = format_bytes(usedi2bytes - self.i2bytes)
        params['limit'] = format_bytes(self.Maxi2KByte * 1024)
        params['new_maxexemptrate'] = bwlimit.format_tc_rate(new_maxi2rate)

        if verbose:
            logger.log("bwmon:  %(slice)s %(class)s " \
                  "%(bytes)s of %(limit)s (%(new_maxrate)s/s maxrate)" % params)

        # Cap high bandwidth burst rate
        if new_maxi2rate != runningmaxi2rate:
            message += template % params
            logger.log("bwmon:  %(slice)s %(class)s capped at %(new_maxexemptrate)s/s" % params)

        # Apply parameters
        if new_maxrate != runningmaxrate or new_maxi2rate != runningmaxi2rate:
            bwlimit.set(xid = self.xid, maxrate = new_maxrate, maxexemptrate = new_maxi2rate)

        # Notify slice
        if message and self.emailed == False:
            subject = "pl_mom capped bandwidth of slice %(slice)s on %(hostname)s" % params
            if debug:
                logger.log("bwmon:  "+ subject)
                logger.log("bwmon:  "+ message + (footer % params))
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
        default_Share,\
        verbose

    # All slices
    names = []

    try:
        f = open(datafile, "r+")
        logger.log("bwmon:  Loading %s" % datafile)
        (version, slices) = pickle.load(f)
        f.close()
        # Check version of data file
        if version != "$Id: bwmon.py,v 1.10 2007/02/27 23:03:58 faiyaza Exp $":
            logger.log("bwmon:  Not using old version '%s' data file %s" % (version, datafile))
            raise Exception
    except Exception:
        version = "$Id: bwmon.py,v 1.10 2007/02/27 23:03:58 faiyaza Exp $"
        slices = {}

    # Get/set special slice IDs
    root_xid = bwlimit.get_xid("root")
    default_xid = bwlimit.get_xid("default")

    if root_xid not in slices.keys():
        slices[root_xid] = Slice(root_xid, "root", data)
        slices[root_xid].reset(0, 0, 0, 0, data)

    if default_xid not in slices.keys():
        slices[default_xid] = Slice(default_xid, "default", data)
        slices[default_xid].reset(0, 0, 0, 0, data)

    live = {}
    # Get running slivers. {xid: name}
    for sliver in data['slivers']:
        live[bwlimit.get_xid(sliver['name'])] = sliver['name']

    # Setup new slices.
    # live.xids - runing.xids = new.xids
    newslicesxids = Set(live.keys()) - Set(slices.keys())
    for newslicexid in newslicesxids:
        if newslicexid != None:
            logger.log("bwmon: New Slice %s" % live[newslicexid])
            slices[newslicexid] = Slice(newslicexid, live[newslicexid], data)
            slices[newslicexid].reset(0, 0, 0, 0, data)
        else:
            logger.log("bwmon  Slice %s doesn't have xid.  Must be delegated.  Skipping." % live[newslicexid])
    # Get actual running values from tc.
    # Update slice totals and bandwidth.
    for params in bwlimit.get():
        (xid, share,
         minrate, maxrate,
         minexemptrate, maxexemptrate,
         usedbytes, usedi2bytes) = params
        
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
               usedbytes < slice.bytes or usedi2bytes < slice.i2bytes:
                # Reset to defaults every 24 hours or if it appears
                # that the byte counters have overflowed (or, more
                # likely, the node was restarted or the HTB buckets
                # were re-initialized).
                slice.reset(maxrate, maxexemptrate, usedbytes, usedi2bytes, data)
            else:
                # Update byte counts
                slice.update(maxrate, maxexemptrate, usedbytes, usedi2bytes, data)
        else:
            # Just in case.  Probably (hopefully) this will never happen.
            # New slice, initialize state
            logger.log("bwmon: New Slice %s" % name)
            slice = slices[xid] = Slice(xid, name, data)
            slice.reset(maxrate, maxexemptrate, usedbytes, usedi2bytes, data)

    # Delete dead slices
    dead = Set(slices.keys()) - Set(live.keys())
    for xid in dead:
        if xid == root_xid or xid == default_xid:
            continue
        del slices[xid]
        bwlimit.off(xid)

    logger.log("bwmon:  Saving %s" % datafile)
    f = open(datafile, "w")
    pickle.dump((version, slices), f)
    f.close()


#def GetSlivers(data):
#   for sliver in data['slivers']:
#       if sliver.has_key('attributes'):
#          print sliver
#           for attribute in sliver['attributes']:
#               if attribute['name'] == "KByteThresh": print attribute['value']

def start(options, config):
    pass

