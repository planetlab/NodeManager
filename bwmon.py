#!/usr/bin/python
#
# Average bandwidth monitoring script. Run periodically via NM db.sync to
# enforce a soft limit on daily bandwidth usage for each slice. If a
# slice is found to have transmitted 80% of its daily byte limit usage,
# its instantaneous rate will be capped at the bytes remaning in the limit
# over the time remaining in the recording period.
#
# Two separate limits are enforced, one for destinations exempt from
# the node bandwidth cap (i.e. Internet2), and the other for all other destinations.
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Andy Bavier <acb@cs.princeton.edu>
# Faiyaz Ahmed <faiyaza@cs.princeton.edu>
# Copyright (C) 2004-2008 The Trustees of Princeton University
#

import os
import sys
import time
import pickle
import socket
import copy
import threading

import logger
import tools
import bwlimit
import database
from config import Config

priority = 20

# Defaults
# Set DEBUG to True if you don't want to send emails
DEBUG = False
# Set ENABLE to False to setup buckets, but not limit.
ENABLE = True

DB_FILE = "/var/lib/nodemanager/bwmon.pickle"

# Constants
seconds_per_day = 24 * 60 * 60
bits_per_byte = 8

dev_default = tools.get_default_if()
# Burst to line rate (or node cap).  Set by NM. in KBit/s
default_MaxRate = int(bwlimit.get_bwcap(dev_default) / 1000)
default_Maxi2Rate = int(bwlimit.bwmax / 1000)
# 5.4 Gbyte per day. 5.4 * 1024 k * 1024M * 1024G
# 5.4 Gbyte per day max allowed transfered per recording period
# 5.4 Gbytes per day is aprox 512k/s for 24hrs (approx because original math was wrong
# but its better to keep a higher byte total and keep people happy than correct
# the problem and piss people off.
# default_MaxKByte = 5662310

# -- 6/1/09
# llp wants to double these, so we use the following
# 1mbit * 24hrs * 60mins * 60secs = bits/day
# 1000000 * 24 * 60 * 60 / (1024 * 8)
default_MaxKByte = 10546875

# 16.4 Gbyte per day max allowed transfered per recording period to I2
# default_Maxi2KByte = 17196646

# -- 6/1/09
# 3Mb/s for 24hrs a day (30.17 gigs)
default_Maxi2KByte = 31640625

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
    '''
    Front end to sendmail.  Sends email to slice alias with given subject and body.
    '''
    config = Config()
    sendmail = os.popen("/usr/sbin/sendmail -N never -t -f%s" % config.PLC_MAIL_SUPPORT_ADDRESS, "w")

    # Parsed from MyPLC config
    to = [config.PLC_MAIL_MOM_LIST_ADDRESS]

    if slice is not None and slice != "root":
        to.append(config.PLC_MAIL_SLICE_ADDRESS.replace("SLICE", slice))

    header = {'from': "%s Support <%s>" % (config.PLC_NAME,
                                           config.PLC_MAIL_SUPPORT_ADDRESS),
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
    MaxKByte - total volume of data allowed
    ThreshKbyte - After thresh, cap node to (maxkbyte - bytes)/(time left in period)
    Maxi2KByte - same as MaxKByte, but for i2
    Threshi2Kbyte - same as Threshi2KByte, but for i2
    MaxRate - max_rate slice attribute.
    Maxi2Rate - max_exempt_rate slice attribute.
    Share - Used by Sirius to loan min rates
    Sharei2 - Used by Sirius to loan min rates for i2
    self.emailed - did slice recv email during this recording period

    """

    def __init__(self, xid, name, rspec):
        self.xid = xid
        self.name = name
        self.time = 0
        self.bytes = 0
        self.i2bytes = 0
        self.MaxRate = default_MaxRate
        self.MinRate = bwlimit.bwmin / 1000
        self.Maxi2Rate = default_Maxi2Rate
        self.Mini2Rate = bwlimit.bwmin / 1000
        self.MaxKByte = default_MaxKByte
        self.ThreshKByte = int(.8 * self.MaxKByte)
        self.Maxi2KByte = default_Maxi2KByte
        self.Threshi2KByte = int(.8 * self.Maxi2KByte)
        self.Share = default_Share
        self.Sharei2 = default_Share
        self.emailed = False
        self.capped = False

        self.updateSliceTags(rspec)
        bwlimit.set(xid = self.xid, dev = dev_default,
                minrate = self.MinRate * 1000,
                maxrate = self.MaxRate * 1000,
                maxexemptrate = self.Maxi2Rate * 1000,
                minexemptrate = self.Mini2Rate * 1000,
                share = self.Share)

    def __repr__(self):
        return self.name

    def updateSliceTags(self, rspec):
        '''
        Use respects from GetSlivers to PLC to populate slice object.  Also
        do some sanity checking.
        '''

        # Sanity check plus policy decision for MinRate:
        # Minrate cant be greater than 25% of MaxRate or NodeCap.
        MinRate = int(rspec.get("net_min_rate", bwlimit.bwmin / 1000))
        if MinRate > int(.25 * default_MaxRate):
            MinRate = int(.25 * default_MaxRate)
        if MinRate != self.MinRate:
            self.MinRate = MinRate
            logger.log("bwmon: Updating %s: Min Rate = %s" %(self.name, self.MinRate))

        MaxRate = int(rspec.get('net_max_rate', default_MaxRate))
        if MaxRate != self.MaxRate:
            self.MaxRate = MaxRate
            logger.log("bwmon: Updating %s: Max Rate = %s" %(self.name, self.MaxRate))

        Mini2Rate = int(rspec.get('net_i2_min_rate', bwlimit.bwmin / 1000))
        if Mini2Rate != self.Mini2Rate:
            self.Mini2Rate = Mini2Rate
            logger.log("bwmon: Updating %s: Min i2 Rate = %s" %(self.name, self.Mini2Rate))

        Maxi2Rate = int(rspec.get('net_i2_max_rate', default_Maxi2Rate))
        if Maxi2Rate != self.Maxi2Rate:
            self.Maxi2Rate = Maxi2Rate
            logger.log("bwmon: Updating %s: Max i2 Rate = %s" %(self.name, self.Maxi2Rate))

        MaxKByte = int(rspec.get('net_max_kbyte', default_MaxKByte))
        if MaxKByte != self.MaxKByte:
            self.MaxKByte = MaxKByte
            logger.log("bwmon: Updating %s: Max KByte lim = %s" %(self.name, self.MaxKByte))

        Maxi2KByte = int(rspec.get('net_i2_max_kbyte', default_Maxi2KByte))
        if Maxi2KByte != self.Maxi2KByte:
            self.Maxi2KByte = Maxi2KByte
            logger.log("bwmon: Updating %s: Max i2 KByte = %s" %(self.name, self.Maxi2KByte))

        ThreshKByte = int(rspec.get('net_thresh_kbyte', (MaxKByte * .8)))
        if ThreshKByte != self.ThreshKByte:
            self.ThreshKByte = ThreshKByte
            logger.log("bwmon: Updating %s: Thresh KByte = %s" %(self.name, self.ThreshKByte))

        Threshi2KByte = int(rspec.get('net_i2_thresh_kbyte', (Maxi2KByte * .8)))
        if Threshi2KByte != self.Threshi2KByte:
            self.Threshi2KByte = Threshi2KByte
            logger.log("bwmon: Updating %s: i2 Thresh KByte = %s" %(self.name, self.Threshi2KByte))

        Share = int(rspec.get('net_share', default_Share))
        if Share != self.Share:
            self.Share = Share
            logger.log("bwmon: Updating %s: Net Share = %s" %(self.name, self.Share))

        Sharei2 = int(rspec.get('net_i2_share', default_Share))
        if Sharei2 != self.Sharei2:
            self.Sharei2 = Sharei2
            logger.log("bwmon: Updating %s: Net i2 Share = %s" %(self.name, self.i2Share))


    def reset(self, runningrates, rspec):
        """
        Begin a new recording period. Remove caps by restoring limits
        to their default values.
        """
        # Cache share for later comparison
        self.Share = runningrates.get('share', 1)

        # Query Node Manager for max rate overrides
        self.updateSliceTags(rspec)

        # Reset baseline time
        self.time = time.time()

        # Reset baseline byte coutns
        self.bytes = runningrates.get('usedbytes', 0)
        self.i2bytes = runningrates.get('usedi2bytes', 0)

        # Reset email
        self.emailed = False
        # Reset flag
        self.capped = False
        # Reset rates.
        maxrate = self.MaxRate * 1000
        minrate = self.MinRate * 1000
        maxi2rate = self.Maxi2Rate * 1000
        mini2rate = self.Mini2Rate * 1000

        if (maxrate != runningrates.get('maxrate', 0)) or \
         (minrate != runningrates.get('maxrate', 0)) or \
         (maxi2rate != runningrates.get('maxexemptrate', 0)) or \
         (mini2rate != runningrates.get('minexemptrate', 0)) or \
         (self.Share != runningrates.get('share', 0)):
            logger.log("bwmon: %s reset to %s/%s" % \
                           (self.name,
                            bwlimit.format_tc_rate(maxrate),
                            bwlimit.format_tc_rate(maxi2rate)))
            bwlimit.set(xid = self.xid, dev = dev_default,
                minrate = self.MinRate * 1000,
                maxrate = self.MaxRate * 1000,
                maxexemptrate = self.Maxi2Rate * 1000,
                minexemptrate = self.Mini2Rate * 1000,
                share = self.Share)

    def notify(self, new_maxrate, new_maxexemptrate, usedbytes, usedi2bytes):
        """
        Notify the slice it's being capped.
        """
         # Prepare message parameters from the template
        message = ""
        params = {'slice': self.name, 'hostname': socket.gethostname(),
                  'since': time.asctime(time.gmtime(self.time)) + " GMT",
                  'until': time.asctime(time.gmtime(self.time + period)) + " GMT",
                  'date': time.asctime(time.gmtime()) + " GMT",
                  'period': format_period(period)}

        if new_maxrate != (self.MaxRate * 1000):
            # Format template parameters for low bandwidth message
            params['class'] = "low bandwidth"
            params['bytes'] = format_bytes(usedbytes - self.bytes)
            params['limit'] = format_bytes(self.MaxKByte * 1024)
            params['new_maxrate'] = bwlimit.format_tc_rate(new_maxrate)

            # Cap low bandwidth burst rate
            message += template % params
            logger.log("bwmon:  ** %(slice)s %(class)s capped at %(new_maxrate)s/s " % params)

        if new_maxexemptrate != (self.Maxi2Rate * 1000):
            # Format template parameters for high bandwidth message
            params['class'] = "high bandwidth"
            params['bytes'] = format_bytes(usedi2bytes - self.i2bytes)
            params['limit'] = format_bytes(self.Maxi2KByte * 1024)
            params['new_maxrate'] = bwlimit.format_tc_rate(new_maxexemptrate)

            message += template % params
            logger.log("bwmon:  ** %(slice)s %(class)s capped at %(new_maxrate)s/s " % params)

        # Notify slice
        if self.emailed == False:
            subject = "pl_mom capped bandwidth of slice %(slice)s on %(hostname)s" % params
            if DEBUG:
                logger.log("bwmon: "+ subject)
                logger.log("bwmon: "+ message + (footer % params))
            else:
                self.emailed = True
                logger.log("bwmon: Emailing %s" % self.name)
                slicemail(self.name, subject, message + (footer % params))


    def update(self, runningrates, rspec):
        """
        Update byte counts and check if byte thresholds have been
        exceeded. If exceeded, cap to remaining bytes in limit over remaining time in period.
        Recalculate every time module runs.
        """
        # cache share for later comparison
        runningrates['share'] = self.Share

        # Query Node Manager for max rate overrides
        self.updateSliceTags(rspec)

        usedbytes = runningrates['usedbytes']
        usedi2bytes = runningrates['usedi2bytes']

        # Check limits.
        if usedbytes >= (self.bytes + (self.ThreshKByte * 1024)):
            sum = self.bytes + (self.ThreshKByte * 1024)
            maxbyte = self.MaxKByte * 1024
            bytesused = usedbytes - self.bytes
            timeused = int(time.time() - self.time)
            # Calcuate new rate. in bit/s
            new_maxrate = int(((maxbyte - bytesused) * 8)/(period - timeused))
            # Never go under MinRate
            if new_maxrate < (self.MinRate * 1000):
                new_maxrate = self.MinRate * 1000
            # State information.  I'm capped.
            self.capped += True
        else:
            # Sanity Check
            new_maxrate = self.MaxRate * 1000
            self.capped += False

        if usedi2bytes >= (self.i2bytes + (self.Threshi2KByte * 1024)):
            maxi2byte = self.Maxi2KByte * 1024
            i2bytesused = usedi2bytes - self.i2bytes
            timeused = int(time.time() - self.time)
            # Calcuate New Rate.
            new_maxi2rate = int(((maxi2byte - i2bytesused) * 8)/(period - timeused))
            # Never go under MinRate
            if new_maxi2rate < (self.Mini2Rate * 1000):
                new_maxi2rate = self.Mini2Rate * 1000
            # State information.  I'm capped.
            self.capped += True
        else:
            # Sanity
            new_maxi2rate = self.Maxi2Rate * 1000
            self.capped += False

        # Check running values against newly calculated values so as not to run tc
        # unnecessarily
        if (runningrates['maxrate'] != new_maxrate) or \
        (runningrates['minrate'] != self.MinRate * 1000) or \
        (runningrates['maxexemptrate'] != new_maxi2rate) or \
        (runningrates['minexemptrate'] != self.Mini2Rate * 1000) or \
        (runningrates['share'] != self.Share):
            # Apply parameters
            bwlimit.set(xid = self.xid, dev = dev_default,
                minrate = self.MinRate * 1000,
                maxrate = new_maxrate,
                minexemptrate = self.Mini2Rate * 1000,
                maxexemptrate = new_maxi2rate,
                share = self.Share)

        # Notify slice
        if self.capped == True:
            self.notify(new_maxrate, new_maxi2rate, usedbytes, usedi2bytes)


def gethtbs(root_xid, default_xid):
    """
    Return dict {xid: {*rates}} of running htbs as reported by tc that have names.
    Turn off HTBs without names.
    """
    livehtbs = {}
    for params in bwlimit.get(dev = dev_default):
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
            logger.log("bwmon: Found orphaned HTB %s. Removing." %name)
            bwlimit.off(xid, dev = dev_default)

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
    Syncs tc, db, and bwmon.pickle.
    Then, starts new slices, kills old ones, and updates byte accounts for each running slice.
    Sends emails and caps those that went over their limit.
    """
    # Defaults
    global DB_FILE, \
        period, \
        default_MaxRate, \
        default_Maxi2Rate, \
        default_MaxKByte,\
        default_Maxi2KByte,\
        default_Share, \
        dev_default

    # All slices
    names = []
    # In case the limits have changed.
    default_MaxRate = int(bwlimit.get_bwcap(dev_default) / 1000)
    default_Maxi2Rate = int(bwlimit.bwmax / 1000)

    # Incase default isn't set yet.
    if default_MaxRate == -1:
        default_MaxRate = 1000000

    try:
        f = open(DB_FILE, "r+")
        logger.verbose("bwmon: Loading %s" % DB_FILE)
        (version, slices, deaddb) = pickle.load(f)
        f.close()
        # Check version of data file
        if version != "$Id$":
            logger.log("bwmon: Not using old version '%s' data file %s" % (version, DB_FILE))
            raise Exception
    except Exception:
        version = "$Id$"
        slices = {}
        deaddb = {}

    # Get/set special slice IDs
    root_xid = bwlimit.get_xid("root")
    default_xid = bwlimit.get_xid("default")

    # Since root is required for sanity, its not in the API/plc database, so pass {}
    # to use defaults.
    if root_xid not in slices.keys():
        slices[root_xid] = Slice(root_xid, "root", {})
        slices[root_xid].reset({}, {})

    # Used by bwlimit.  pass {} since there is no rspec (like above).
    if default_xid not in slices.keys():
        slices[default_xid] = Slice(default_xid, "default", {})
        slices[default_xid].reset({}, {})

    live = {}
    # Get running slivers that should be on this node (from plc). {xid: name}
    # db keys on name, bwmon keys on xid.  db doesnt have xid either.
    for plcSliver in nmdbcopy.keys():
        live[bwlimit.get_xid(plcSliver)] = nmdbcopy[plcSliver]

    logger.verbose("bwmon: Found %s instantiated slices" % live.keys().__len__())
    logger.verbose("bwmon: Found %s slices in dat file" % slices.values().__len__())

    # Get actual running values from tc.
    # Update slice totals and bandwidth. {xid: {values}}
    kernelhtbs = gethtbs(root_xid, default_xid)
    logger.verbose("bwmon: Found %s running HTBs" % kernelhtbs.keys().__len__())

    # The dat file has HTBs for slices, but the HTBs aren't running
    nohtbslices =  set(slices.keys()) - set(kernelhtbs.keys())
    logger.verbose( "bwmon: Found %s slices in dat but not running." % nohtbslices.__len__())
    # Reset tc counts.
    for nohtbslice in nohtbslices:
        if live.has_key(nohtbslice):
            slices[nohtbslice].reset( {}, live[nohtbslice]['_rspec'] )
        else:
            logger.log("bwmon: Removing abondoned slice %s from dat." % nohtbslice)
            del slices[nohtbslice]

    # The dat file doesnt have HTB for the slice but kern has HTB
    slicesnodat = set(kernelhtbs.keys()) - set(slices.keys())
    logger.verbose( "bwmon: Found %s slices with HTBs but not in dat" % slicesnodat.__len__())
    for slicenodat in slicesnodat:
        # But slice is running
        if live.has_key(slicenodat):
            # init the slice.  which means start accounting over since kernel
            # htb was already there.
            slices[slicenodat] = Slice(slicenodat,
                live[slicenodat]['name'],
                live[slicenodat]['_rspec'])

    # Get new slices.
    # Slices in GetSlivers but not running HTBs
    newslicesxids = set(live.keys()) - set(kernelhtbs.keys())
    logger.verbose("bwmon: Found %s new slices" % newslicesxids.__len__())

    # Setup new slices
    for newslice in newslicesxids:
        # Delegated slices dont have xids (which are uids) since they haven't been
        # instantiated yet.
        if newslice != None and live[newslice].has_key('_rspec') == True:
            # Check to see if we recently deleted this slice.
            if live[newslice]['name'] not in deaddb.keys():
                logger.log( "bwmon: new slice %s" % live[newslice]['name'] )
                # _rspec is the computed rspec:  NM retrieved data from PLC, computed loans
                # and made a dict of computed values.
                slices[newslice] = Slice(newslice, live[newslice]['name'], live[newslice]['_rspec'])
                slices[newslice].reset( {}, live[newslice]['_rspec'] )
            # Double check time for dead slice in deaddb is within 24hr recording period.
            elif (time.time() <= (deaddb[live[newslice]['name']]['slice'].time + period)):
                deadslice = deaddb[live[newslice]['name']]
                logger.log("bwmon: Reinstantiating deleted slice %s" % live[newslice]['name'])
                slices[newslice] = deadslice['slice']
                slices[newslice].xid = newslice
                # Start the HTB
                newvals = {"maxrate": deadslice['slice'].MaxRate * 1000,
                            "minrate": deadslice['slice'].MinRate * 1000,
                            "maxexemptrate": deadslice['slice'].Maxi2Rate * 1000,
                            "usedbytes": deadslice['htb']['usedbytes'] * 1000,
                            "usedi2bytes": deadslice['htb']['usedi2bytes'],
                            "share":deadslice['htb']['share']}
                slices[newslice].reset(newvals, live[newslice]['_rspec'])
                # Bring up to date
                slices[newslice].update(newvals, live[newslice]['_rspec'])
                # Since the slice has been reinitialed, remove from dead database.
                del deaddb[deadslice['slice'].name]
                del newvals
        else:
            logger.log("bwmon: Slice %s doesn't have xid.  Skipping." % live[newslice]['name'])

    # Move dead slices that exist in the pickle file, but
    # aren't instantiated by PLC into the dead dict until
    # recording period is over.  This is to avoid the case where a slice is dynamically created
    # and destroyed then recreated to get around byte limits.
    deadxids = set(slices.keys()) - set(live.keys())
    logger.verbose("bwmon: Found %s dead slices" % (deadxids.__len__() - 2))
    for deadxid in deadxids:
        if deadxid == root_xid or deadxid == default_xid:
            continue
        logger.log("bwmon: removing dead slice %s " % deadxid)
        if slices.has_key(deadxid) and kernelhtbs.has_key(deadxid):
            # add slice (by name) to deaddb
            logger.log("bwmon: Saving bandwidth totals for %s." % slices[deadxid].name)
            deaddb[slices[deadxid].name] = {'slice': slices[deadxid], 'htb': kernelhtbs[deadxid]}
            del slices[deadxid]
        if kernelhtbs.has_key(deadxid):
            logger.verbose("bwmon: Removing HTB for %s." % deadxid)
            bwlimit.off(deadxid, dev = dev_default)

    # Clean up deaddb
    for deadslice in deaddb.keys():
        if (time.time() >= (deaddb[deadslice]['slice'].time + period)):
            logger.log("bwmon: Removing dead slice %s from dat." \
                        % deaddb[deadslice]['slice'].name)
            del deaddb[deadslice]

    # Get actual running values from tc since we've added and removed buckets.
    # Update slice totals and bandwidth. {xid: {values}}
    kernelhtbs = gethtbs(root_xid, default_xid)
    logger.verbose("bwmon: now %s running HTBs" % kernelhtbs.keys().__len__())

    # Update all byte limites on all slices
    for (xid, slice) in slices.iteritems():
        # Monitor only the specified slices
        if xid == root_xid or xid == default_xid: continue
        if names and name not in names:
            continue

        if (time.time() >= (slice.time + period)) or \
            (kernelhtbs[xid]['usedbytes'] < slice.bytes) or \
            (kernelhtbs[xid]['usedi2bytes'] < slice.i2bytes):
            # Reset to defaults every 24 hours or if it appears
            # that the byte counters have overflowed (or, more
            # likely, the node was restarted or the HTB buckets
            # were re-initialized).
            slice.reset(kernelhtbs[xid], live[xid]['_rspec'])
        elif ENABLE:
            logger.verbose("bwmon: Updating slice %s" % slice.name)
            # Update byte counts
            slice.update(kernelhtbs[xid], live[xid]['_rspec'])

    logger.verbose("bwmon: Saving %s slices in %s" % (slices.keys().__len__(),DB_FILE))
    f = open(DB_FILE, "w")
    pickle.dump((version, slices, deaddb), f)
    f.close()

# doesnt use generic default interface because this runs as its own thread.
# changing the config variable will not have an effect since GetSlivers: pass
def getDefaults(nmdbcopy):
    '''
    Get defaults from default slice's slice attributes.
    '''
    status = True
    # default slice
    dfltslice = nmdbcopy.get(Config().PLC_SLICE_PREFIX+"_default")
    if dfltslice:
        if dfltslice['rspec']['net_max_rate'] == -1:
            allOff()
            status = False
    return status


def allOff():
    """
    Turn off all slice HTBs
    """
    # Get/set special slice IDs
    root_xid = bwlimit.get_xid("root")
    default_xid = bwlimit.get_xid("default")
    kernelhtbs = gethtbs(root_xid, default_xid)
    if len(kernelhtbs):
        logger.log("bwmon: Disabling all running HTBs.")
        for htb in kernelhtbs.keys(): bwlimit.off(htb, dev = dev_default)


lock = threading.Event()
def run():
    """
    When run as a thread, wait for event, lock db, deep copy it, release it,
    run bwmon.GetSlivers(), then go back to waiting.
    """
    logger.verbose("bwmon: Thread started")
    while True:
        lock.wait()
        logger.verbose("bwmon: Event received.  Running.")
        database.db_lock.acquire()
        nmdbcopy = copy.deepcopy(database.db)
        database.db_lock.release()
        try:
            if getDefaults(nmdbcopy) and len(bwlimit.tc("class show dev %s" % dev_default)) > 0:
                # class show to check if net:InitNodeLimit:bwlimit.init has run.
                sync(nmdbcopy)
            else: logger.log("bwmon: BW limits DISABLED.")
        except: logger.log_exc("bwmon failed")
        lock.clear()

def start(*args):
    tools.as_daemon_thread(run)

def GetSlivers(*args):
    logger.verbose ("bwmon: triggering dummy GetSlivers")
    pass
