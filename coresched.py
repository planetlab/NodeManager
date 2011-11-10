# $Id$
# $URL$

"""Whole core scheduling

"""

import logger
import os

glo_coresched_simulate = False

class CoreSched:
    """ Whole-core scheduler

        The main entrypoint is adjustCores(self, slivers) which takes a
        dictionary of sliver records. The cpu_cores field is pulled from the
        effective rspec (rec["_rspec"]) for each sliver.

        If cpu_cores > 0 for a sliver, then that sliver will reserve one or
        more of the cpu_cores on the machine.

        One core is always left unreserved for system slices.
    """

    def __init__(self, cgroup_var_name="cpuset.cpus", slice_attr_name="cpu_cores"):
        self.cpus = []
        self.cgroup_var_name = cgroup_var_name
        self.slice_attr_name = slice_attr_name
        self.cgroup_mem_name = "cpuset.mems"
        self.mems=[]
        self.mems_map={}
        self.cpu_siblings={}

    def get_cgroup_var(self, name=None, filename=None):
        """ decode cpuset.cpus or cpuset.mems into a list of units that can
            be reserved.
        """

        assert(filename!=None or name!=None)

        if filename==None:
            filename="/dev/cgroup/" + name

        data = open(filename).readline().strip()

        if not data:
           return []

        units = []

        # cpuset.cpus could be something as arbitrary as:
        #    0,1,2-3,4,5-6
        # deal with commas and ranges
        for part in data.split(","):
            unitRange = part.split("-")
            if len(unitRange) == 1:
                unitRange = (unitRange[0], unitRange[0])
            for i in range(int(unitRange[0]), int(unitRange[1])+1):
                if not i in units:
                    units.append(i)

        return units

    def get_cpus(self):
        """ return a list of available cpu identifiers: [0,1,2,3...]
        """

        # the cpus never change, so if it's already been computed then don't
        # worry about it.
        if self.cpus!=[]:
            return self.cpus

        self.cpus = self.get_cgroup_var(self.cgroup_var_name)

        self.cpu_siblings = {}
        for item in self.cpus:
           self.cpu_siblings[item] = self.get_core_siblings(item)

        return self.cpus

    def find_cpu_mostsiblings(self, cpus):
        bestCount = -1
        bestCpu = -1
        for cpu in cpus:
            count = 0
            for candidate in self.cpu_siblings[cpu]:
                if candidate in cpus:
                    count = count + 1
                if (count > bestCount):
                    bestCount = count
                    bestCpu = cpu

        assert(bestCpu >= 0)
        return bestCpu


    def find_compatible_cpu(self, cpus, compatCpu):
        if compatCpu==None:
           return self.find_cpu_mostsiblings(cpus)

        # find a sibling if we can
        bestDelta = None
        bestCpu = None
        for cpu in cpus:
           if compatCpu in self.cpu_siblings[cpu]:
               return cpu

        return self.find_cpu_mostsiblings(cpus)

    def get_cgroups (self):
        """ return a list of cgroups
            this might change as vservers are instantiated, so always compute
            it dynamically.
        """
        cgroups = []
        filenames = os.listdir("/dev/cgroup")
        for filename in filenames:
            if os.path.isdir(os.path.join("/dev/cgroup", filename)):
                cgroups.append(filename)
        return cgroups

    def decodeCoreSpec (self, cores):
        """ Decode the value of the core attribute. It's a number, followed by
            an optional letter "b" to indicate besteffort cores should also
            be supplied.
        """
        bestEffort = False

        if cores.endswith("b"):
           cores = cores[:-1]
           bestEffort = True

        try:
            cores = int(cores)
        except ValueError:
            cores = 0

        return (cores, bestEffort)

    def adjustCores (self, slivers):
        """ slivers is a dict of {sliver_name: rec}
                rec is a dict of attributes
                    rec['_rspec'] is the effective rspec
        """

        cpus = self.get_cpus()[:]
        mems = self.get_mems()[:]

        memSchedule=True
        if (len(mems) != len(cpus)):
            logger.log("CoreSched fewer mems than " + self.cgroup_var_name + "; mem scheduling disabled")
            memSchedule=False

        logger.log("CoreSched (" + self.cgroup_var_name + "): available units: " + str(cpus))

        reservations = {}
        mem_reservations = {}

        # allocate the cores to the slivers that have them reserved
        # TODO: Need to sort this from biggest cpu_cores to smallest
        for name, rec in slivers.iteritems():
            rspec = rec["_rspec"]
            cores = rspec.get(self.slice_attr_name, 0)
            (cores, bestEffort) = self.decodeCoreSpec(cores)

            lastCpu = None

            while (cores>0):
                # one cpu core reserved for best effort and system slices
                if len(cpus)<=1:
                    logger.log("CoreSched: ran out of units while scheduling sliver " + name)
                else:
                    cpu = self.find_compatible_cpu(cpus, lastCpu)
                    cpus.remove(cpu)
                    lastCpu = cpu

                    logger.log("CoreSched: allocating unit " + str(cpu) + " to slice " + name)
                    reservations[name] = reservations.get(name,[]) + [cpu]

                    # now find a memory node to go with the cpu
                    if memSchedule:
                        mem = self.find_associated_memnode(mems, cpu)
                        if mem != None:
                            mems.remove(mem)
                            logger.log("CoreSched: allocating memory node " + str(mem) + " to slice " + name)
                            mem_reservations[name] = mem_reservations.get(name,[]) + [mem]
                        else:
                            logger.log("CoreSched: failed to find memory node for cpu" + str(cpu))

                cores = cores-1

        # the leftovers go to everyone else
        logger.log("CoreSched: allocating unit " + str(cpus) + " to _default")
        reservations["_default"] = cpus[:]
        mem_reservations["_default"] = mems[:]

        # now check and see if any of our slices had the besteffort flag
        # set
        for name, rec in slivers.iteritems():
            rspec = rec["_rspec"]
            cores = rspec.get(self.slice_attr_name, 0)
            (cores, bestEffort) = self.decodeCoreSpec(cores)

            # if the bestEffort flag isn't set then we have nothing to do
            if not bestEffort:
                continue

            # note that if a reservation is [], then we don't need to add
            # bestEffort cores to it, since it is bestEffort by default.

            if reservations.get(name,[]) != []:
                reservations[name] = reservations[name] + reservations["_default"]
                mem_reservations[name] = mem_reservations.get(name,[]) + mem_reservations["_default"]
                logger.log("CoreSched: adding besteffort units to " + name + ". new units = " + str(reservations[name]))

        self.reserveUnits(self.cgroup_var_name, reservations)

        self.reserveUnits(self.cgroup_mem_name, mem_reservations)

    def reserveUnits (self, var_name, reservations):
        """ give a set of reservations (dictionary of slicename:cpuid_list),
            write those reservations to the appropriate cgroup files.

            reservations["_default"] is assumed to be the default reservation
            for slices that do not reserve cores. It's essentially the leftover
            cpu cores.
        """

        default = reservations["_default"]

        # set the default vserver cpuset. this will deal with any vservers
        # that might be created before the nodemanager has had a chance to
        # update the cpusets.
        self.reserveDefault(var_name, default)

        for cgroup in self.get_cgroups():
            if cgroup in reservations:
                cpus = reservations[cgroup]
                logger.log("CoreSched: reserving " + var_name + " on " + cgroup + ": " + str(cpus))
            else:
                # no log message for default; too much verbosity in the common case
                cpus = default

            if glo_coresched_simulate:
                print "R", "/dev/cgroup/" + cgroup + "/" + var_name, self.listToRange(cpus)
            else:
                file("/dev/cgroup/" + cgroup + "/" + var_name, "w").write( self.listToRange(cpus) + "\n" )

    def reserveDefault (self, var_name, cpus):
        if not os.path.exists("/etc/vservers/.defaults/cgroup"):
            os.makedirs("/etc/vservers/.defaults/cgroup")

        if glo_coresched_simulate:
            print "RDEF", "/etc/vservers/.defaults/cgroup/" + var_name, self.listToRange(cpus)
        else:
            file("/etc/vservers/.defaults/cgroup/" + var_name, "w").write( self.listToRange(cpus) + "\n" )

    def listToRange (self, list):
        """ take a list of items [1,2,3,5,...] and return it as a range: "1-3,5"
            for now, just comma-separate
        """
        return ",".join( [str(i) for i in list] )

    def get_mems(self):
        """ return a list of available cpu identifiers: [0,1,2,3...]
        """

        # the cpus never change, so if it's already been computed then don't
        # worry about it.
        if self.mems!=[]:
            return self.mems

        self.mems = self.get_cgroup_var(self.cgroup_mem_name)

        # build a mapping from memory nodes to the cpus they can be used with

        mems_map={}
        for item in self.mems:
           mems_map[item] = self.get_memnode_cpus(item)

        if (len(mems_map)>0):
            # when NUMA_EMU is enabled, only the last memory node will contain
            # the cpu_map. For example, if there were originally 2 nodes and
            # we used NUM_EMU to raise it to 12, then
            #    mems_map[0]=[]
            #    ...
            #    mems_map[4]=[]
            #    mems_map[5]=[1,3,5,7,9,11]
            #    mems_map[6]=[]
            #    ...
            #    mems_map[10]=[]
            #    mems_map[11]=[0,2,4,6,8,10]
            # so, we go from back to front, copying the entries as necessary.

            if mems_map[self.mems[0]] == []:
                work = []
                for item in reversed(self.mems):
                    if mems_map[item]!=[]:
                        work = mems_map[item]
                    else:  # mems_map[item]==[]
                        mems_map[item] = work

            self.mems_map = mems_map

        return self.mems

    def find_associated_memnode(self, mems, cpu):
        """ Given a list of memory nodes and a cpu, see if one of the nodes in
            the list can be used with that cpu.
        """
        for item in mems:
            if cpu in self.mems_map[item]:
                return item
        return None

    def get_memnode_cpus(self, index):
        """ for a given memory node, return the CPUs that it is associated
            with.
        """
        fn = "/sys/devices/system/node/node" + str(index) + "/cpulist"
        if not os.path.exists(fn):
            logger.log("CoreSched: failed to locate memory node" + fn)
            return []

        return self.get_cgroup_var(filename=fn)

    def get_core_siblings(self, index):
        # use core_siblings rather than core_siblings_list, as it's compatible
        # with older kernels
        fn = "/sys/devices/system/cpu/cpu" + str(index) + "/topology/core_siblings"
        if not os.path.exists(fn):
            return []
        siblings = []

        x = int(open(fn,"rt").readline().strip(),16)
        cpuid = 0
        while (x>0):
            if (x&1)!=0:
                siblings.append(cpuid)
            x = x >> 1
            cpuid += 1

        return siblings


# a little self-test
if __name__=="__main__":
    glo_coresched_simulate = True

    x = CoreSched()

    print "cgroups:", ",".join(x.get_cgroups())

    print "cpus:", x.listToRange(x.get_cpus())
    print "sibling map:"
    for item in x.get_cpus():
        print " ", item, ",".join([str(y) for y in x.cpu_siblings.get(item,[])])

    print "mems:", x.listToRange(x.get_mems())
    print "cpu to memory map:"
    for item in x.get_mems():
        print " ", item, ",".join([str(y) for y in x.mems_map.get(item,[])])

    rspec_sl_test1 = {"cpu_cores": "1"}
    rec_sl_test1 = {"_rspec": rspec_sl_test1}

    rspec_sl_test2 = {"cpu_cores": "5"}
    rec_sl_test2 = {"_rspec": rspec_sl_test2}

    rspec_sl_test3 = {"cpu_cores": "3b"}
    rec_sl_test3 = {"_rspec": rspec_sl_test3}

    #slivers = {"sl_test1": rec_sl_test1, "sl_test2": rec_sl_test2}

    slivers = {"arizona_beta": rec_sl_test1, "arizona_test101": rec_sl_test2, "pl_sirius": rec_sl_test3}

    #slivers = {"arizona_beta": rec_sl_test1, "arizona_logmon": rec_sl_test2, "arizona_owl": rec_sl_test3}

    x.adjustCores(slivers)

