#!/usr/bin/python
# 
# Bandwidth limit module for PlanetLab nodes. The intent is to use the
# Hierarchical Token Bucket (HTB) queueing discipline (qdisc) to allow
# slices to fairly share access to available node bandwidth. We
# currently define three classes of "available node bandwidth":
#
# 1. Available hardware bandwidth (bwmax): The maximum rate of the
# hardware.
#
# 2. Available capped bandwidth (bwcap): The maximum rate allowed to
# non-exempt destinations. By default, equal to bwmax, but may be
# lowered by PIs.
#
# 3. Available uncapped ("exempt") bandwidth: The difference between
# bwmax and what is currently being used of bwcap, or the maximum rate
# allowed to destinations exempt from caps (e.g., Internet2).
#
# All three classes of bandwidth are fairly shared according to the
# notion of "shares". For instance, if the node is capped at 5 Mbps,
# there are N slices, and each slice has 1 share, then each slice
# should get at least 5/N Mbps of bandwidth. How HTB is implemented
# makes this statement a little too simplistic. What it really means
# is that during any single time period, only a certain number of
# bytes can be sent onto the wire. Each slice is guaranteed that at
# least some small number of its bytes will be sent. Whatever is left
# over from the budget, is split in proportion to the number of shares
# each slice has.
#
# Even if the node is not capped at a particular limit (bwcap ==
# bwmax), this module enforces fair share access to bwmax. Also, if
# the node is capped at a particular limit, rules may optionally be
# defined that classify certain packets into the "exempt" class. This
# class receives whatever bandwidth is leftover between bwcap and
# bwmax; slices fairly share this bandwidth as well.
#
# The root context is exempt from sharing and can send as much as it
# needs to.
#
# Some relevant URLs:
#
# 1. http://lartc.org/howto               for how to use tc
# 2. http://luxik.cdi.cz/~devik/qos/htb/  for info on HTB
#
# Andy Bavier <acb@cs.princeton.edu>
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id: bwlimit.py,v 1.15 2007/02/07 04:21:11 mlhuang Exp $
#

import sys, os, re, getopt
import pwd


# Where the tc binary lives
TC = "/sbin/tc"

# Default interface
dev = "eth0"

# Verbosity level
verbose = 0

# bwmin should be small enough that it can be considered negligibly
# slow compared to the hardware. 8 bits/second appears to be the
# smallest value supported by tc.
bwmin = 1000

# bwmax should be large enough that it can be considered at least as
# fast as the hardware.
bwmax = 1000*1000*1000

# quantum is the maximum number of bytes that can be borrowed by a
# share (or slice, if each slice gets 1 share) in one time period
# (with HZ=1000, 1 ms). If multiple slices are competing for bandwidth
# above their guarantees, and each is attempting to borrow up to the
# node bandwidth cap, quantums control how the excess bandwidth is
# distributed. Slices with 2 shares will borrow twice the amount in
# one time period as slices with 1 share, so averaged over time, they
# will get twice as much of the excess bandwidth. The value should be
# as small as possible and at least 1 MTU. By default, it would be
# calculated as bwmin/10, but since we use such small a value for
# bwmin, it's better to just set it to a value safely above 1 Ethernet
# MTU.
quantum = 1600

# cburst is the maximum number of bytes that can be burst onto the
# wire in one time period (with HZ=1000, 1 ms). If multiple slices
# have data queued for transmission, cbursts control how long each
# slice can have the wire for. If not specified, it is set to the
# smallest possible value that would enable the slice's "ceil" rate
# (usually the node bandwidth cap), to be reached if a slice was able
# to borrow enough bandwidth to do so. For now, it's unclear how or if
# to relate this to the notion of shares, so just let tc set the
# default.
cburst = None

# There is another parameter that controls how bandwidth is allocated
# between slices on nodes that is outside the scope of HTB. We enforce
# a 16 GByte/day total limit on each slice, which works out to about
# 1.5mbit. If a slice exceeds this byte limit before the day finishes,
# it is capped at (i.e., its "ceil" rate is set to) the smaller of the
# node bandwidth cap or 1.5mbit. pl_mom is in charge of enforcing this
# rule and executes this script to override "ceil".

# We support multiple bandwidth limits, by reserving the top nibble of
# the minor classid to be the "subclassid". Theoretically, we could
# support up to 15 subclasses, but for now, we only define two: the
# "default" subclass 1:10 that is capped at the node bandwidth cap (in
# this example, 5mbit) and the "exempt" subclass 1:20 that is capped
# at bwmax (i.e., not capped). The 1:1 parent class exists only to
# make the borrowing model work. All bandwidth above minimum
# guarantees is fairly shared (in this example, slice 2 is guaranteed
# at least 1mbit in addition to fair access to the rest), subject to
# the restrictions of the class hierarchy: namely, that the total
# bandwidth to non-exempt destinations should not exceed the node
# bandwidth cap.
#
#                         1:
#                         |
#                    1:1 (1gbit)
#           ______________|_____________
#          |                            |
#   1:10 (8bit, 5mbit)           1:20 (8bit, 1gbit)
#          |                            |
#  1:100 (8bit, 5mbit)                  |
#          |                            |
# 1:1000 (8bit, 5mbit),        1:2000 (8bit, 1gbit),
# 1:1001 (8bit, 5mbit),        1:2001 (8bit, 1gbit),
# 1:1002 (1mbit, 5mbit),       1:2002 (1mbit, 1gbit),
# ...                          ...
# 1:1FFF (8bit, 5mbit)         1:2FFF (8bit, 1gbit)
#
default_minor = 0x1000
exempt_minor = 0x2000

# root_xid is for the root context. The root context is exempt from
# fair sharing in both the default and exempt subclasses. The root
# context gets 5 shares by default.
root_xid = 0x0000
root_share = 5

# default_xid is for unclassifiable packets. Packets should not be
# classified here very often. They can be if a slice's HTB classes are
# deleted before its processes are. Each slice gets 1 share by
# default.
default_xid = 0x0FFF
default_share = 1

# See tc_util.c and http://physics.nist.gov/cuu/Units/binary.html. Be
# warned that older versions of tc interpret "kbps", "mbps", "mbit",
# and "kbit" to mean (in this system) "kibps", "mibps", "mibit", and
# "kibit" and that if an older version is installed, all rates will
# be off by a small fraction.
suffixes = {
    "":         1,
    "bit":      1,
    "kibit":    1024,
    "kbit":     1000,
    "mibit":    1024*1024,
    "mbit":     1000000,
    "gibit":    1024*1024*1024,
    "gbit":     1000000000,
    "tibit":    1024*1024*1024*1024,
    "tbit":     1000000000000,
    "bps":      8,
    "kibps":    8*1024,
    "kbps":     8000,
    "mibps":    8*1024*1024,
    "mbps":     8000000,
    "gibps":    8*1024*1024*1024,
    "gbps":     8000000000,
    "tibps":    8*1024*1024*1024*1024,
    "tbps":     8000000000000
}


def get_tc_rate(s):
    """
    Parses an integer or a tc rate string (e.g., 1.5mbit) into bits/second
    """

    if type(s) == int:
        return s
    m = re.match(r"([0-9.]+)(\D*)", s)
    if m is None:
        return -1
    suffix = m.group(2).lower()
    if suffixes.has_key(suffix):
        return int(float(m.group(1)) * suffixes[suffix])
    else:
        return -1

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

def format_tc_rate(rate):
    """
    Formats a bits/second rate into a tc rate string
    """

    if rate >= 1000000000 and (rate % 1000000000) == 0:
        return "%.0fgbit" % (rate / 1000000000.)
    elif rate >= 1000000 and (rate % 1000000) == 0:
        return "%.0fmbit" % (rate / 1000000.)
    elif rate >= 1000:
        return "%.0fkbit" % (rate / 1000.)
    else:
        return "%.0fbit" % rate


# Parse /etc/planetlab/bwcap (or equivalent)
def read_bwcap(bwcap_file):
    bwcap = bwmax
    try:
        fp = open(bwcap_file, "r")
        line = fp.readline().strip()
        if line:
            bwcap = get_tc_rate(line)
    except:
        pass
    if bwcap == -1:
        bwcap = bwmax
    return bwcap


def get_bwcap(dev = dev):
    """
    Get the current (live) value of the node bandwidth cap
    """

    state = tc("-d class show dev %s" % dev)
    base_re = re.compile(r"class htb 1:10 parent 1:1 .*ceil ([^ ]+) .*")
    base_classes = filter(None, map(base_re.match, state))
    if not base_classes:
        return -1
    if len(base_classes) > 1:
        raise Exception, "unable to get current bwcap"
    return get_tc_rate(base_classes[0].group(1))


def get_slice(xid):
    """
    Get slice name ("princeton_mlh") from slice xid (500)
    """

    if xid == root_xid:
        return "root"
    if xid == default_xid:
        return "default"
    try:
        return pwd.getpwuid(xid).pw_name
    except KeyError:
        pass

    return None

def get_xid(slice):
    """
    Get slice xid ("princeton_mlh") from slice name ("500" or "princeton_mlh")
    """

    if slice == "root":
        return root_xid
    if slice == "default":
        return default_xid
    try:
        try:
            return int(slice)
        except ValueError:
            pass
        return pwd.getpwnam(slice).pw_uid
    except KeyError:
        pass

    return None

def run(cmd, input = None):
    """
    Shortcut for running a shell command
    """

    try:
        if verbose:
            sys.stderr.write("Executing: " + cmd + "\n")
        if input is None:
            fileobj = os.popen(cmd, "r")
            output = fileobj.readlines()
        else:
            fileobj = os.popen(cmd, "w")
            fileobj.write(input)
            output = None
        if fileobj.close() is None:
            return output
    except Exception, e:
        pass
    return None


def tc(cmd):
    """
    Shortcut for running a tc command
    """

    return run(TC + " " + cmd)


def stop(dev = dev):
    '''
    Turn off all queing.  Stops all slice HTBS and reverts to pfifo_fast (the default).
    '''
    try:
        for i in range(0,2):
            tc("qdisc del dev %s root" % dev)
    except: pass


def init(dev = dev, bwcap = bwmax):
    """
    (Re)initialize the bandwidth limits on this node
    """

    # Load the module used to manage exempt classes
    run("/sbin/modprobe ip_set_iphash")

    # Save current settings
    paramslist = get(None, dev)

    # Delete root qdisc 1: if it exists. This will also automatically
    # delete any child classes.
    for line in tc("qdisc show dev %s" % dev):
        # Search for the root qdisc 1:
        m = re.match(r"qdisc htb 1:", line)
        if m is not None:
            tc("qdisc del dev %s root handle 1:" % dev)
            break

    # Initialize HTB. The "default" clause specifies that if a packet
    # fails classification, it should go into the class with handle
    # 1FFF.
    tc("qdisc add dev %s root handle 1: htb default %x" % \
       (dev, default_minor | default_xid))

    # Set up a parent class from which all subclasses borrow.
    tc("class add dev %s parent 1: classid 1:1 htb rate %dbit" % \
       (dev, bwmax))

    # Set up a subclass that represents the node bandwidth cap. We
    # allow each slice to borrow up to this rate, so it is also
    # usually the "ceil" rate for each slice.
    tc("class add dev %s parent 1:1 classid 1:10 htb rate %dbit ceil %dbit" % \
       (dev, bwmin, bwcap))

    # Set up a subclass for DRL(Distributed Rate Limiting). 
    # DRL will directly modify that subclass implementing the site limits.
    tc("class add dev %s parent 1:10 classid 1:100 htb rate %dbit ceil %dbit" % \
       (dev, bwmin, bwcap))


    # Set up a subclass that represents "exemption" from the node
    # bandwidth cap. Once the node bandwidth cap is reached, bandwidth
    # to exempt destinations can still be fairly shared up to bwmax.
    tc("class add dev %s parent 1:1 classid 1:20 htb rate %dbit ceil %dbit" % \
       (dev, bwmin, bwmax))

    # Set up the root class (and tell VNET what it is). Packets sent
    # by root end up here and are capped at the node bandwidth
    # cap.
    #on(root_xid, dev, share = root_share)
    #try:
    #    file("/proc/sys/vnet/root_class", "w").write("%d" % ((1 << 16) | default_minor | root_xid))
    #except:
    #    pass

    # Set up the default class. Packets that fail classification end
    # up here.
    on(default_xid, dev, share = default_share)

    # Restore old settings
    for (xid, share,
         minrate, maxrate,
         minexemptrate, maxexemptrate,
         bytes, exemptbytes) in paramslist:
        if xid not in (root_xid, default_xid):
            on(xid, dev, share, minrate, maxrate, minexemptrate, maxexemptrate)


def get(xid = None, dev = dev):
    """
    Get the bandwidth limits and current byte totals for a
    particular slice xid as a tuple (xid, share, minrate, maxrate,
    minexemptrate, maxexemptrate, bytes, exemptbytes), or all classes
    as a list of such tuples.
    """

    if xid is None:
        ret = []
    else:
        ret = None

    rates = {}
    rate = None

    # ...
    # class htb 1:1000 parent 1:10 leaf 1000: prio 0 quantum 8000 rate 8bit ceil 10000Kbit ...
    #  Sent 6851486 bytes 49244 pkt (dropped 0, overlimits 0 requeues 0)
    # ...
    # class htb 1:2000 parent 1:20 leaf 2000: prio 0 quantum 8000 rate 8bit ceil 1000Mbit ...
    #  Sent 0 bytes 0 pkt (dropped 0, overlimits 0 requeues 0) 
    # ...
    for line in tc("-s -d class show dev %s" % dev):
        # Rate parameter line
        params = re.match(r"class htb 1:([0-9a-f]+) parent 1:(10|20)", line)
        # Statistics line
        stats = re.match(r".* Sent ([0-9]+) bytes", line)
        # Another class
        ignore = re.match(r"class htb", line)

        if params is not None:
            # Which class
            if params.group(2) == "10":
                min = 'min'
                max = 'max'
                bytes = 'bytes'
            else:
                min = 'minexempt'
                max = 'maxexempt'
                bytes = 'exemptbytes'

            # Slice ID
            id = int(params.group(1), 16) & 0x0FFF;

            if rates.has_key(id):
                rate = rates[id]
            else:
                rate = {'id': id}

            # Parse share
            rate['share'] = 1
            m = re.search(r"quantum (\d+)", line)
            if m is not None:
                rate['share'] = int(m.group(1)) / quantum

            # Parse minrate
            rate[min] = bwmin
            m = re.search(r"rate (\w+)", line)
            if m is not None:
                rate[min] = get_tc_rate(m.group(1))

            # Parse maxrate
            rate[max] = bwmax
            m = re.search(r"ceil (\w+)", line)
            if m is not None:
                rate[max] = get_tc_rate(m.group(1))

            # Which statistics to parse
            rate['stats'] = bytes

            rates[id] = rate

        elif stats is not None:
            if rate is not None:
                rate[rate['stats']] = int(stats.group(1))

        elif ignore is not None:
            rate = None

        # Keep parsing until we get everything
        if rate is not None and \
           rate.has_key('min') and rate.has_key('minexempt') and \
           rate.has_key('max') and rate.has_key('maxexempt') and \
           rate.has_key('bytes') and rate.has_key('exemptbytes'):
            params = (rate['id'], rate['share'],
                      rate['min'], rate['max'],
                      rate['minexempt'], rate['maxexempt'],
                      rate['bytes'], rate['exemptbytes'])
            if xid is None:
                # Return a list of parameters
                ret.append(params)
                rate = None
            elif xid == rate['id']:
                # Return the parameters for this class
                ret = params
                break

    return ret


def on(xid, dev = dev, share = None, minrate = None, maxrate = None, minexemptrate = None, maxexemptrate = None):
    """
    Apply specified bandwidth limit to the specified slice xid
    """

    # Get defaults from current state if available
    cap = get(xid, dev)
    if cap is not None:
        if share is None:
            share = cap[1]
        if minrate is None:
            minrate = cap[2]
        if maxrate is None:
            maxrate = cap[3]
        if minexemptrate is None:
            minexemptrate = cap[4]
        if maxexemptrate is None:
            maxexemptrate = cap[5]

    # Figure out what the current node bandwidth cap is
    bwcap = get_bwcap(dev)

    # Set defaults
    if share is None:
        share = default_share
    if minrate is None:
        minrate = bwmin
    else:
        minrate = get_tc_rate(minrate)
    if maxrate is None:
        maxrate = bwcap
    else:
        maxrate = get_tc_rate(maxrate)
    if minexemptrate is None:
        minexemptrate = minrate
    else:
        minexemptrate = get_tc_rate(minexemptrate)
    if maxexemptrate is None:
        maxexemptrate = bwmax
    else:
        maxexemptrate = get_tc_rate(maxexemptrate)

    # Sanity checks
    if maxrate < bwmin:
        maxrate = bwmin
    if maxrate > bwcap:
        maxrate = bwcap
    if minrate < bwmin:
        minrate = bwmin
    if minrate > maxrate:
        minrate = maxrate
    if maxexemptrate < bwmin:
        maxexemptrate = bwmin
    if maxexemptrate > bwmax:
        maxexemptrate = bwmax
    if minexemptrate < bwmin:
        minexemptrate = bwmin
    if minexemptrate > maxexemptrate:
        minexemptrate = maxexemptrate

    # Set up subclasses for the slice
    tc("class replace dev %s parent 1:100 classid 1:%x htb rate %dbit ceil %dbit quantum %d" % \
       (dev, default_minor | xid, minrate, maxrate, share * quantum))

    tc("class replace dev %s parent 1:20 classid 1:%x htb rate %dbit ceil %dbit quantum %d" % \
       (dev, exempt_minor | xid, minexemptrate, maxexemptrate, share * quantum))

    # Attach a FIFO to each subclass, which helps to throttle back
    # processes that are sending faster than the token buckets can
    # support.
    tc("qdisc replace dev %s parent 1:%x handle %x pfifo" % \
       (dev, default_minor | xid, default_minor | xid))

    tc("qdisc replace dev %s parent 1:%x handle %x pfifo" % \
       (dev, exempt_minor | xid, exempt_minor | xid))


def set(xid, share = None, minrate = None, maxrate = None, minexemptrate = None, maxexemptrate = None, dev = dev ):
    on(xid = xid, dev = dev, share = share,
       minrate = minrate, maxrate = maxrate,
       minexemptrate = minexemptrate, maxexemptrate = maxexemptrate)


# Remove class associated with specified slice xid. If further packets
# are seen from this slice, they will be classified into the default
# class 1:1FFF.
def off(xid, dev = dev):
    """
    Remove class associated with specified slice xid. If further
    packets are seen from this slice, they will be classified into the
    default class 1:1FFF.
    """

    cap = get(xid, dev)
    if cap is not None:
        tc("class del dev %s classid 1:%x" % (dev, default_minor | xid))
        tc("class del dev %s classid 1:%x" % (dev, exempt_minor | xid))


def exempt_init(group_name, node_ips):
    """
    Initialize the list of destinations exempt from the node bandwidth
    (burst) cap.
    """

    # Check of set exists
    set = run("/sbin/ipset -S " + group_name)
    if set == None:
        # Create a hashed IP set of all of these destinations
        lines = ["-N %s iphash" % group_name]
        add_cmd = "-A %s " % group_name
        lines += [(add_cmd + ip) for ip in node_ips]
        lines += ["COMMIT"]
        restore = "\n".join(lines) + "\n"
        run("/sbin/ipset -R", restore)
    else: # set exists
        # Check all hosts and add missing.
        for nodeip in node_ips:
            if not run("/sbin/ipset -T %s %s" % (group_name, nodeip)):
               run("/sbin/ipset -A %s %s" % (group_name, nodeip))


def usage():
    bwcap_description = format_tc_rate(get_bwcap())
        
    print """
Usage:

%s [OPTION]... [COMMAND] [ARGUMENT]...

Options:
        -d device   Network interface (default: %s)
        -r rate         Node bandwidth cap (default: %s)
        -q quantum      Share multiplier (default: %d bytes)
        -n              Print rates in numeric bits per second
        -v              Enable verbose debug messages
        -h              This message

Commands:
        init
                (Re)initialize all bandwidth parameters
        on slice [share|-] [minrate|-] [maxrate|-] [minexemptrate|-] [maxexemptrate|-]
                Set bandwidth parameter(s) for the specified slice
        off slice
                Remove all bandwidth parameters for the specified slice
        get
                Get all bandwidth parameters for all slices
        get slice
                Get bandwidth parameters for the specified slice
""" % (sys.argv[0], dev, bwcap_description, quantum)
    sys.exit(1)
    

def main():
    global dev, quantum, verbose

    # Defaults
    numeric = False
    bwcap = None

    (opts, argv) = getopt.getopt(sys.argv[1:], "d:nr:q:vh")
    for (opt, optval) in opts:
        if opt == '-d':
            dev = optval
        elif opt == '-n':
            numeric = True
        elif opt == '-r':
            bwcap = get_tc_rate(optval)
        elif opt == '-q':
            quantum = int(optval)
        elif opt == '-v':
            verbose += 1
        elif opt == '-h':
            usage()

    if not bwcap:
        bwcap = get_bwcap(dev)

    if bwcap == -1:
        return 0

    if len(argv):
        if argv[0] == "init" or (argv[0] == "on" and len(argv) == 1):
            # (Re)initialize
            init(dev, get_tc_rate(bwcap))

        elif argv[0] == "get" or argv[0] == "show":
            # Show
            if len(argv) >= 2:
                # Show a particular slice
                xid = get_xid(argv[1])
                if xid is None:
                    sys.stderr.write("Error: Invalid slice name or context '%s'\n" % argv[1])
                    usage()
                params = get(xid, dev)
                if params is None:
                    paramslist = []
                else:
                    paramslist = [params]
            else:
                # Show all slices
                paramslist = get(None, dev)

            for (xid, share,
                 minrate, maxrate,
                 minexemptrate, maxexemptrate,
                 bytes, exemptbytes) in paramslist:
                slice = get_slice(xid)
                if slice is None:
                    # Orphaned (not associated with a slice) class
                    slice = "%d?" % xid
                if numeric:
                    print "%s %d %d %d %d %d %d %d" % \
                          (slice, share,
                           minrate, maxrate,
                           minexemptrate, maxexemptrate,
                           bytes, exemptbytes)
                else:
                    print "%s %d %s %s %s %s %s %s" % \
                          (slice, share,
                           format_tc_rate(minrate), format_tc_rate(maxrate),
                           format_tc_rate(minexemptrate), format_tc_rate(maxexemptrate),
                           format_bytes(bytes), format_bytes(exemptbytes))

        elif len(argv) >= 2:
            # slice, ...
            xid = get_xid(argv[1])
            if xid is None:
                sys.stderr.write("Error: Invalid slice name or context '%s'\n" % argv[1])
                usage()

            if argv[0] == "on" or argv[0] == "add" or argv[0] == "replace" or argv[0] == "set":
                # Enable cap
                args = []
                if len(argv) >= 3:
                    # ... share, minrate, maxrate, minexemptrate, maxexemptrate
                    casts = [int, get_tc_rate, get_tc_rate, get_tc_rate, get_tc_rate]
                    for i, arg in enumerate(argv[2:]):
                        if i >= len(casts):
                            break
                        if arg == "-":
                            args.append(None)
                        else:
                            args.append(casts[i](arg))
                on(xid, dev, *args)

            elif argv[0] == "off" or argv[0] == "del":
                # Disable cap
                off(xid, dev)

            else:
                usage()

        else:
            usage()


if __name__ == '__main__':
    main()
