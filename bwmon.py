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
# $Id$
#

import os
import sys
import time
import pickle
import socket
import logger
import copy
import threading
import tools

import bwlimit
import database

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

    def __init__(self, xid, name, rspec):
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
        self.Sharei2 = default_Share
        self.emailed = False

        self.updateSliceAttributes(rspec)
        bwlimit.set(xid = self.xid, 
                minrate = self.MinRate * 1000, 
                maxrate = self.MaxRate * 1000, 
                maxexemptrate = self.Maxi2Rate * 1000,
                minexemptrate = self.Mini2Rate * 1000,
                share = self.Share)

    def __repr__(self):
        return self.name

    def updateSliceAttributes(self, rspec):
        # Get attributes

        # Sanity check plus policy decision for MinRate:
        # Minrate cant be greater than 25% of MaxRate or NodeCap.
        MinRate = int(rspec.get("net_min_rate", default_MinRate))
        if MinRate > int(.25 * default_MaxRate):
            MinRate = int(.25 * default_MaxRate)
        if MinRate != self.MinRate:
            self.MinRate = MinRate
            logger.log("bwmon:  Updating %s: Min Rate = %s" %(self.name, self.MinRate))

        MaxRate = int(rspec.get('net_max_rate', bwlimit.get_bwcap() / 1000))
        if MaxRate != self.MaxRate:
            self.MaxRate = MaxRate
            logger.log("bwmon:  Updating %s: Max Rate = %s" %(self.name, self.MaxRate))

        Mini2Rate = int(rspec.get('net_i2_min_rate', default_Mini2Rate))
        if Mini2Rate != self.Mini2Rate:
            self.Mini2Rate = Mini2Rate 
            logger.log("bwmon:  Updating %s: Min i2 Rate = %s" %(self.name, self.Mini2Rate))

        Maxi2Rate = int(rspec.get('net_i2_max_rate', bwlimit.bwmax / 1000))
        if Maxi2Rate != self.Maxi2Rate:
            self.Maxi2Rate = Maxi2Rate
            logger.log("bwmon:  Updating %s: Max i2 Rate = %s" %(self.name, self.Maxi2Rate))
                          
        MaxKByte = int(rspec.get('net_max_kbyte', default_MaxKByte))
        if MaxKByte != self.MaxKByte:
            self.MaxKByte = MaxKByte
            logger.log("bwmon:  Updating %s: Max KByte lim = %s" %(self.name, self.MaxKByte))
                          
        Maxi2KByte = int(rspec.get('net_i2_max_kbyte', default_Maxi2KByte))
        if Maxi2KByte != self.Maxi2KByte:
            self.Maxi2KByte = Maxi2KByte
            logger.log("bwmon:  Updating %s: Max i2 KByte = %s" %(self.name, self.Maxi2KByte))
                          
        ThreshKByte = int(rspec.get('net_thresh_kbyte', default_ThreshKByte))
        if ThreshKByte != self.ThreshKByte:
            self.ThreshKByte = ThreshKByte
            logger.log("bwmon:  Updating %s: Thresh KByte = %s" %(self.name, self.ThreshKByte))
                          
        Threshi2KByte = int(rspec.get('net_i2_thresh_kbyte', default_Threshi2KByte))
        if Threshi2KByte != self.Threshi2KByte:    
            self.Threshi2KByte = Threshi2KByte
            logger.log("bwmon:  Updating %s: i2 Thresh KByte = %s" %(self.name, self.Threshi2KByte))
 
        Share = int(rspec.get('net_share', default_Share))
        if Share != self.Share:
            self.Share = Share
            logger.log("bwmon:  Updating %s: Net Share = %s" %(self.name, self.Share))

        Sharei2 = int(rspec.get('net_i2_share', default_Share))
        if Sharei2 != self.Sharei2:
            self.Sharei2 = Sharei2 
            logger.log("bwmon:  Updating %s: Net i2 Share = %s" %(self.name, self.i2Share))


    def reset(self, runningmaxrate, runningmaxi2rate, usedbytes, usedi2bytes, rspec):
        """
        Begin a new recording period. Remove caps by restoring limits
        to their default values.
        """
        
        # Query Node Manager for max rate overrides
        self.updateSliceAttributes(rspec)    

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

    def update(self, runningmaxrate, runningmaxi2rate, usedbytes, usedi2bytes, rspec):
        """
        Update byte counts and check if byte limits have been
        exceeded. 
        """
    
        # Query Node Manager for max rate overrides
        self.updateSliceAttributes(rspec)    
     
        # Prepare message parameters from the template
        message = ""
        params = {'slice': self.name, 'hostname': socket.gethostname(),
                  'since': time.asctime(time.gmtime(self.time)) + " GMT",
                  'until': time.asctime(time.gmtime(self.time + period)) + " GMT",
                  'date': time.asctime(time.gmtime()) + " GMT",
                  'period': format_period(period)} 

        if usedbytes >= (self.bytes + (self.ThreshKByte * 1024)):
            if verbose:
                logger.log("bwmon: %s over thresh %s" \
                  % (self.name, format_bytes(self.ThreshKByte * 1024)))
            sum = self.bytes + (self.ThreshKByte * 1024)
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
        params['thresh'] = format_bytes(self.ThreshKByte * 1024)
        params['new_maxrate'] = bwlimit.format_tc_rate(new_maxrate)

        if verbose:
            logger.log("bwmon:  %(slice)s %(class)s " \
                  "%(bytes)s of %(limit)s max %(thresh)s thresh (%(new_maxrate)s/s maxrate)" % \
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

def gethtbs(root_xid, default_xid):
    """
    Return dict {xid: {*rates}} of running htbs as reported by tc that have names.
    Turn off HTBs without names.
    """
    livehtbs = {}
    for params in bwlimit.get():
        (xid, share,
         minrate, maxrate,
         minexemptrate, maxexemptrate,
         usedbytes, usedi2bytes) = params
        
        name = bwlimit.get_slice(xid)

        
        
        if (name is None) \
        and (xid != root_xid) \
        and (xid != default_xid):
            # Orphaned (not associated with a slice) class
            name = "%d?" % xid
            logger.log("bwmon:  Found orphaned HTB %s. Removing." %name)
            bwlimit.off(xid)

        livehtbs[xid] = {'share': share,
            'minrate': minrate,
            'maxrate': maxrate,
            'maxexemptrate': maxexemptrate,
            'minexemptrate': minexemptrate,
            'usedbytes': usedbytes,
            'name': name, 
            'usedi2bytes': usedi2bytes}

    return livehtbs

def sync(nmdbcopy):
    """
    Syncs tc, db, and bwmon.dat.  Then, starts new slices, kills old ones, and updates byte accounts for each running slice.  Sends emails and caps those that went over their limit.
    """
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
    # Incase the limits have changed. 
    default_MaxRate = int(bwlimit.get_bwcap() / 1000)
    default_Maxi2Rate = int(bwlimit.bwmax / 1000)

    # Incase default isn't set yet.
    if default_MaxRate == -1:
        default_MaxRate = 1000000

    try:
        f = open(datafile, "r+")
        logger.log("bwmon:  Loading %s" % datafile)
        (version, slices) = pickle.load(f)
        f.close()
        # Check version of data file
        if version != "$Id$":
            logger.log("bwmon:  Not using old version '%s' data file %s" % (version, datafile))
            raise Exception
    except Exception:
        version = "$Id$"
        slices = {}

    # Get/set special slice IDs
    root_xid = bwlimit.get_xid("root")
    default_xid = bwlimit.get_xid("default")

    # Since root is required for sanity, its not in the API/plc database, so pass {} 
    # to use defaults.
    if root_xid not in slices.keys():
        slices[root_xid] = Slice(root_xid, "root", {})
        slices[root_xid].reset(0, 0, 0, 0, {})
    
    # Used by bwlimit.  pass {} since there is no rspec (like above).
    if default_xid not in slices.keys():
        slices[default_xid] = Slice(default_xid, "default", {})
        slices[default_xid].reset(0, 0, 0, 0, {})

    live = {}
    # Get running slivers that should be on this node (from plc). {xid: name}
    # db keys on name, bwmon keys on xid.  db doesnt have xid either.
    for plcSliver in nmdbcopy.keys():
        live[bwlimit.get_xid(plcSliver)] = nmdbcopy[plcSliver]

    logger.log("bwmon:  Found %s instantiated slices" % live.keys().__len__())
    logger.log("bwmon:  Found %s slices in dat file" % slices.values().__len__())

    # Get actual running values from tc.
    # Update slice totals and bandwidth. {xid: {values}}
    livehtbs = gethtbs(root_xid, default_xid)
    logger.log("bwmon:  Found %s running HTBs" % livehtbs.keys().__len__())

    # Get new slices.
    # live.xids - runing(slices).xids = new.xids
    #newslicesxids = Set(live.keys()) - Set(slices.keys()) 
    newslicesxids = Set(live.keys()) - Set(livehtbs.keys())
    logger.log("bwmon:  Found %s new slices" % newslicesxids.__len__())

    # Incase we rebooted and need to bring up the htbs that are in the db but 
    # not known to tc.
    #nohtbxids = Set(slices.keys()) - Set(livehtbs.keys())
    #logger.log("bwmon:  Found %s slices that should have htbs but dont." % nohtbxids.__len__())
    #newslicesxids.update(nohtbxids)
        
    # Setup new slices
    for newslice in newslicesxids:
        # Delegated slices dont have xids (which are uids) since they haven't been
        # instantiated yet.
        if newslice != None and live[newslice].has_key('_rspec') == True:
            logger.log("bwmon: New Slice %s" % live[newslice]['name'])
            # _rspec is the computed rspec:  NM retrieved data from PLC, computed loans
            # and made a dict of computed values.
            slices[newslice] = Slice(newslice, live[newslice]['name'], live[newslice]['_rspec'])
            slices[newslice].reset(0, 0, 0, 0, live[newslice]['_rspec'])
        else:
            logger.log("bwmon  Slice %s doesn't have xid.  Must be delegated.  Skipping." % live[newslice]['name'])

    # Delete dead slices.
    # First delete dead slices that exist in the pickle file, but
    # aren't instantiated by PLC.
    dead = Set(slices.keys()) - Set(live.keys())
    logger.log("bwmon:  Found %s dead slices" % (dead.__len__() - 2))
    for xid in dead:
        if xid == root_xid or xid == default_xid:
            continue
        logger.log("bwmon:  removing dead slice  %s " % xid)
        if slices.has_key(xid): del slices[xid]
        if livehtbs.has_key(xid): bwlimit.off(xid)

    # Get actual running values from tc since we've added and removed buckets.
    # Update slice totals and bandwidth. {xid: {values}}
    livehtbs = gethtbs(root_xid, default_xid)
    logger.log("bwmon:  now %s running HTBs" % livehtbs.keys().__len__())

    for (xid, slice) in slices.iteritems():
        # Monitor only the specified slices
        if xid == root_xid or xid == default_xid: continue
        if names and name not in names:
            continue
 
        if (time.time() >= (slice.time + period)) or \
        (livehtbs[xid]['usedbytes'] < slice.bytes) or \
        (livehtbs[xid]['usedi2bytes'] < slice.i2bytes):
            # Reset to defaults every 24 hours or if it appears
            # that the byte counters have overflowed (or, more
            # likely, the node was restarted or the HTB buckets
            # were re-initialized).
            slice.reset(livehtbs[xid]['maxrate'], \
                livehtbs[xid]['maxexemptrate'], \
                livehtbs[xid]['usedbytes'], \
                livehtbs[xid]['usedi2bytes'], \
                live[xid]['_rspec'])
        else:
            if debug:  logger.log("bwmon: Updating slice %s" % slice.name)
            # Update byte counts
            slice.update(livehtbs[xid]['maxrate'], \
                livehtbs[xid]['maxexemptrate'], \
                livehtbs[xid]['usedbytes'], \
                livehtbs[xid]['usedi2bytes'], \
                live[xid]['_rspec'])
    
    logger.log("bwmon:  Saving %s slices in %s" % (slices.keys().__len__(),datafile))
    f = open(datafile, "w")
    pickle.dump((version, slices), f)
    f.close()

lock = threading.Event()
def run():
    """When run as a thread, wait for event, lock db, deep copy it, release it, run bwmon.GetSlivers(), then go back to waiting."""
    if debug:  logger.log("bwmon:  Thread started")
    while True:
        lock.wait()
        if debug: logger.log("bwmon:  Event received.  Running.")
        database.db_lock.acquire()
        nmdbcopy = copy.deepcopy(database.db)
        database.db_lock.release()
        try:  sync(nmdbcopy)
        except: logger.log_exc()
        lock.clear()

def start(*args):
    tools.as_daemon_thread(run)

def GetSlivers(*args):
    pass
