#
# $Id$
#

"""network configuration"""

# system provided modules
import os, string, time, socket, modprobe

# local modules
import sioc, bwlimit, logger, iptables

def GetSlivers(plc, data):
    InitInterfaces(plc, data)
    InitNodeLimit(data)
    InitI2(plc, data)
    InitNAT(plc, data)

def InitNodeLimit(data):
    if not 'networks' in data: return

    # query running network interfaces
    devs = sioc.gifconf()
    ips = dict(zip(devs.values(), devs.keys()))
    macs = {}
    for dev in devs:
        macs[sioc.gifhwaddr(dev).lower()] = dev

    # XXX Exempt Internet2 destinations from node bwlimits
    # bwlimit.exempt_init('Internet2', internet2_ips)
    for network in data['networks']:
        # Get interface name preferably from MAC address, falling
        # back on IP address.
        hwaddr=network['mac']
        if hwaddr <> None: hwaddr=hwaddr.lower()
        if hwaddr in macs:
            dev = macs[network['mac']]
        elif network['ip'] in ips:
            dev = ips[network['ip']]
        else:
            logger.log('%s: no such interface with address %s/%s' % (network['hostname'], network['ip'], network['mac']))
            continue

        # Get current node cap
        try:
            old_bwlimit = bwlimit.get_bwcap(dev)
        except:
            old_bwlimit = None

        # Get desired node cap
        if network['bwlimit'] is None or network['bwlimit'] < 0:
            new_bwlimit = bwlimit.bwmax
        else:
            new_bwlimit = network['bwlimit']

        if old_bwlimit != new_bwlimit:
            # Reinitialize bandwidth limits
            bwlimit.init(dev, new_bwlimit)

            # XXX This should trigger an rspec refresh in case
            # some previously invalid sliver bwlimit is now valid
            # again, or vice-versa.

def InitI2(plc, data):
    if not 'groups' in data: return

    if "Internet2" in data['groups']:
        logger.log("This is an Internet2 node.  Setting rules.")
        i2nodes = []
        i2nodeids = plc.GetNodeGroups(["Internet2"])[0]['node_ids']
        for node in plc.GetNodeNetworks({"node_id": i2nodeids}, ["ip"]):
            # Get the IPs
            i2nodes.append(node['ip'])
        # this will create the set if it doesn't already exist
        # and add IPs that don't exist in the set rather than
        # just recreateing the set.
        bwlimit.exempt_init('Internet2', i2nodes)
        
        # set the iptables classification rule if it doesnt exist.
        cmd = '-A POSTROUTING -m set --set Internet2 dst -j CLASSIFY --set-class 0001:2000 --add-mark'
        rules = []
        ipt = os.popen("/sbin/iptables-save")
        for line in ipt.readlines(): rules.append(line.strip(" \n"))
        ipt.close()
        if cmd not in rules:
            logger.verbose("net:  Adding iptables rule for Internet2")
            os.popen("/sbin/iptables -t mangle " + cmd)

def InitNAT(plc, data):
    if not 'networks' in data: return
    
    # query running network interfaces
    devs = sioc.gifconf()
    ips = dict(zip(devs.values(), devs.keys()))
    macs = {}
    for dev in devs:
        macs[sioc.gifhwaddr(dev).lower()] = dev

    ipt = iptables.IPTables()
    for network in data['networks']:
        # Get interface name preferably from MAC address, falling
        # back on IP address.
        hwaddr=network['mac']
        if hwaddr <> None: hwaddr=hwaddr.lower()
        if hwaddr in macs:
            dev = macs[network['mac']]
        elif network['ip'] in ips:
            dev = ips[network['ip']]
        else:
            logger.log('%s: no such interface with address %s/%s' % (network['hostname'], network['ip'], network['mac']))
            continue

        try:
            settings = plc.GetNodeNetworkSettings({'nodenetwork_setting_id': network['nodenetwork_setting_ids']})
        except:
            continue

        for setting in settings:
            if setting['category'].upper() != 'FIREWALL':
                continue
            if setting['name'].upper() == 'EXTERNAL':
                # Enable NAT for this interface
                ipt.add_ext(dev)
            elif setting['name'].upper() == 'INTERNAL':
                ipt.add_int(dev)
            elif setting['name'].upper() == 'PF': # XXX Uglier code is hard to find...
                for pf in setting['value'].split("\n"):
                    fields = {}
                    for field in pf.split(","):
                        (key, val) = field.split("=", 2)
                        fields[key] = val
                    if 'new_dport' not in fields:
                        fields['new_dport'] = fields['dport']
                    if 'source' not in fields:
                        fields['source'] = "0.0.0.0/0"
                    ipt.add_pf(fields)
    ipt.commit()

def InitInterfaces(plc, data):
    if not 'networks' in data: return

    sysconfig = "/etc/sysconfig/network-scripts"

    # query running network interfaces
    devs = sioc.gifconf()
    ips = dict(zip(devs.values(), devs.keys()))
    macs = {}
    for dev in devs:
        macs[sioc.gifhwaddr(dev).lower()] = dev

    # assume data['networks'] contains this node's NodeNetworks
    interfaces = {}
    interface = 1
    hostname = data.get('hostname',socket.gethostname())
    networks = data['networks']
    failedToGetSettings = False
    for network in networks:
    	logger.log('interface %d: %s'%(interface,network))
    	logger.log('macs = %s' % macs)
        logger.log('ips = %s' % ips)
        # Get interface name preferably from MAC address, falling back
        # on IP address.
        hwaddr=network['mac']
        if hwaddr <> None: hwaddr=hwaddr.lower()
        if hwaddr in macs:
            orig_ifname = macs[hwaddr]
        elif network['ip'] in ips:
            orig_ifname = ips[network['ip']]
        else:
            orig_ifname = None

	if orig_ifname:
       		logger.log('orig_ifname = %s' % orig_ifname)
	
        inter = {}
        inter['ONBOOT']='yes'
        inter['USERCTL']='no'
        if network['mac']:
            inter['HWADDR'] = network['mac']

        if network['method'] == "static":
            inter['BOOTPROTO'] = "static"
            inter['IPADDR'] = network['ip']
            inter['NETMASK'] = network['netmask']

        elif network['method'] == "dhcp":
            inter['BOOTPROTO'] = "dhcp"
            if network['hostname']:
                inter['DHCP_HOSTNAME'] = network['hostname']
            else:
                inter['DHCP_HOSTNAME'] = hostname 
            if not network['is_primary']:
                inter['DHCLIENTARGS'] = "-R subnet-mask"

        if len(network['nodenetwork_setting_ids']) > 0:
            try:
                settings = plc.GetNodeNetworkSettings({'nodenetwork_setting_id':
                                                       network['nodenetwork_setting_ids']})
            except:
                logger.log("FATAL: failed call GetNodeNetworkSettings({'nodenetwork_setting_id':{%s})"% \
                           network['nodenetwork_setting_ids'])
                failedToGetSettings = True
                continue # on to the next network

            for setting in settings:
                # to explicitly set interface name
                settingname = setting['name'].upper()
                if settingname in ('IFNAME','ALIAS','CFGOPTIONS','DRIVER'):
                    inter[settingname]=setting['value']
                else:
                    logger.log("WARNING: ignored setting named %s"%setting['name'])

        # support aliases to interfaces either by name or HWADDR
        if 'ALIAS' in inter:
            if 'HWADDR' in inter:
                hwaddr = inter['HWADDR'].lower()
                del inter['HWADDR']
                if hwaddr in macs:
                    hwifname = macs[hwaddr]
                    if ('IFNAME' in inter) and inter['IFNAME'] <> hwifname:
                        logger.log("WARNING: alias ifname (%s) and hwaddr ifname (%s) do not match"%\
                                       (inter['IFNAME'],hwifname))
                        inter['IFNAME'] = hwifname
                else:
                    logger.log('WARNING: mac addr %s for alias not found' %(hwaddr,alias))

            if 'IFNAME' in inter:
                # stupid RH /etc/sysconfig/network-scripts/ifup-aliases:new_interface()
                # checks if the "$DEVNUM" only consists of '^[0-9A-Za-z_]*$'. Need to make
                # our aliases compliant.
                parts = inter['ALIAS'].split('_')
                isValid=True
                for part in parts:
                    isValid=isValid and part.isalnum()

                if isValid:
                    interfaces["%s:%s" % (inter['IFNAME'],inter['ALIAS'])] = inter 
                else:
                    logger.log("WARNING: interface alias (%s) not a valid string for RH ifup-aliases"% inter['ALIAS'])
            else:
                logger.log("WARNING: interface alias (%s) not matched to an interface"% inter['ALIAS'])
            interface -= 1
        else:
            if ('IFNAME' not in inter) and not orig_ifname:
                ifname="eth%d" % (interface-1)
                # should check if $ifname is an eth already defines
                if os.path.exists("%s/ifcfg-%s"%(sysconfig,ifname)):
                    logger.log("WARNING: possibly blowing away %s configuration"%ifname)
            else:
		if ('IFNAME' not in inter) and orig_ifname:
                    ifname = orig_ifname
                else:
                    ifname = inter['IFNAME']
                interface -= 1
            interfaces[ifname] = inter
                
    m = modprobe.Modprobe()
    m.input("/etc/modprobe.conf")
    for (dev, inter) in interfaces.iteritems():
        # get the driver string "moduleName option1=a option2=b"
        driver=inter.get('DRIVER','')
        if driver <> '':
            driver=driver.split()
            kernelmodule=driver[0]
            m.aliasset(dev,kernelmodule)
            options=" ".join(driver[1:])
            if options <> '':
                m.optionsset(dev,options)
    m.output("/etc/modprobe.conf")

    # clean up after any ifcfg-$dev script that's no longer listed as
    # part of the NodeNetworks associated with this node

    # list all network-scripts
    files = os.listdir(sysconfig)

    # filter out the ifcfg-* files
    ifcfgs=[]
    for f in files:
        if f.find("ifcfg-") == 0:
            ifcfgs.append(f)

    # remove loopback (lo) from ifcfgs list
    lo = "ifcfg-lo"
    if lo in ifcfgs: ifcfgs.remove(lo)

    # remove known devices from icfgs list
    for (dev, inter) in interfaces.iteritems():
        ifcfg = 'ifcfg-'+dev
        if ifcfg in ifcfgs: ifcfgs.remove(ifcfg)

    # delete the remaining ifcfgs from 
    deletedSomething = False

    if not failedToGetSettings:
        for ifcfg in ifcfgs:
            dev = ifcfg[len('ifcfg-'):]
            path = "%s/ifcfg-%s" % (sysconfig,dev)
            logger.log("removing %s %s"%(dev,path))
            ifdown = os.popen("/sbin/ifdown %s" % dev)
            ifdown.close()
            deletedSomething=True
            os.unlink(path)

    # wait a bit for the one or more ifdowns to have taken effect
    if deletedSomething:
        time.sleep(2)

    # Process ifcg-$dev changes / additions
    newdevs = []
    for (dev, inter) in interfaces.iteritems():
        tmpnam = os.tmpnam()
        f = file(tmpnam, "w")
        f.write("# Autogenerated by NodeManager/net.py.... do not edit!\n")
        if 'DRIVER' in inter:
            f.write("# using %s driver for device %s\n" % (inter['DRIVER'],dev))
        f.write('DEVICE="%s"\n' % dev)
        
        # print the configuration values
        for (key, val) in inter.iteritems():
            if key not in ('IFNAME','ALIAS','CFGOPTIONS','DRIVER'):
                f.write('%s="%s"\n' % (key, val))

        # print the configuration specific option values (if any)
        if 'CFGOPTIONS' in inter:
            cfgoptions = inter['CFGOPTIONS']
            f.write('#CFGOPTIONS are %s\n' % cfgoptions)
            for cfgoption in cfgoptions.split():
                key,val = cfgoption.split('=')
                key=key.strip()
                key=key.upper()
                val=val.strip()
                f.write('%s="%s"\n' % (key,val))
        f.close()

        # compare whether two files are the same
        def comparefiles(a,b):
            try:
		logger.log("comparing %s with %s" % (a,b))
                if not os.path.exists(a): return False
                fb = open(a)
                buf_a = fb.read()
                fb.close()

                if not os.path.exists(b): return False
                fb = open(b)
                buf_b = fb.read()
                fb.close()

                return buf_a == buf_b
            except IOError, e:
                return False

        path = "%s/ifcfg-%s" % (sysconfig,dev)
        if not os.path.exists(path):
            logger.log('adding configuration for %s' % dev)
            # add ifcfg-$dev configuration file
            os.rename(tmpnam,path)
            os.chmod(path,0644)
            newdevs.append(dev)
            
        elif not comparefiles(tmpnam,path):
            logger.log('Configuration change for %s' % dev)
            logger.log('ifdown %s' % dev)
            # invoke ifdown for the old configuration
            p = os.popen("/sbin/ifdown %s" % dev)
            p.close()
            # wait a few secs for ifdown to complete
            time.sleep(2)

            logger.log('replacing configuration for %s' % dev)
            # replace ifcfg-$dev configuration file
            os.rename(tmpnam,path)
            os.chmod(path,0644)
            newdevs.append(dev)
        else:
            # tmpnam & path are identical
            os.unlink(tmpnam)

    for dev in newdevs:
        cfgvariables = {}
        fb = file("%s/ifcfg-%s"%(sysconfig,dev),"r")
        for line in fb.readlines():
            parts = line.split()
            if parts[0][0]=="#":continue
            if parts[0].find('='):
                name,value = parts[0].split('=')
                # clean up name & value
                name = name.strip()
                value = value.strip()
                value = value.strip("'")
                value = value.strip('"')
                cfgvariables[name]=value
        fb.close()

        def getvar(name):
            if name in cfgvariables:
                value=cfgvariables[name]
                value = value.lower()
                return value
            return ''

        # skip over device configs with ONBOOT=no
        if getvar("ONBOOT") == 'no': continue

        # don't bring up slave devices, the network scripts will
        # handle those correctly
        if getvar("SLAVE") == 'yes': continue

        logger.log('bringing up %s' % dev)
        p = os.popen("/sbin/ifup %s" % dev)
        # check for failure?
        p.close()

def start(options, config):
    pass
