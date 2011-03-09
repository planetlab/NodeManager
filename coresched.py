# $Id$
# $URL$

"""Whole core scheduling

"""

import logger
import os

class CoreSched:
    """ Whole-core scheduler

        The main entrypoint is adjustCores(self, slivers) which takes a
        dictionary of sliver records. The cpu_cores field is pulled from the
        effective rspec (rec["_rspec"]) for each sliver.

        If cpu_cores > 0 for a sliver, then that sliver will reserve one or
        more of the cpu_cores on the machine.

        One core is always left unreserved for system slices.
    """

    def __init__(self):
        self.cpus = []

    def get_cpus(self):
        """ return a list of available cpu identifiers: [0,1,2,3...]
        """

        # the cpus never change, so if it's already been computed then don't
        # worry about it.
        if self.cpus!=[]:
            return self.cpus

        cpuset_cpus = open("/dev/cgroup/cpuset.cpus").readline().strip()

        # cpuset.cpus could be something as arbitrary as:
        #    0,1,2-3,4,5-6
        # deal with commas and ranges
        for part in cpuset_cpus.split(","):
            cpuRange = part.split("-")
            if len(cpuRange) == 1:
                cpuRange = (cpuRange[0], cpuRange[0])
            for i in range(int(cpuRange[0]), int(cpuRange[1])+1):
                if not i in self.cpus:
                    self.cpus.append(i)

            return self.cpus

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

    def adjustCores (self, slivers):
        """ slivers is a dict of {sliver_name: rec}
                rec is a dict of attributes
                    rec['_rspec'] is the effective rspec
        """

        logger.log("CoreSched: adjusting cores")

        cpus = self.get_cpus()[:]

        reservations = {}

        for name, rec in slivers.iteritems():
            rspec = rec["_rspec"]
            cores = rspec.get("cpu_cores", 0)
            while (cores>0):
                # one cpu core reserved for best effort and system slices
                if len(cpus)<=1:
                    logger.log("CoreSched: ran out of cpu cores while scheduling: " + name)
                else:
                    cpu = cpus.pop()
                    logger.log("CoreSched: allocating cpu " + str(cpu) + " to slice " + name)
                    reservations[name] = reservations.get(name,[]) + [cpu]

                cores = cores-1

        # the leftovers go to everyone else
        logger.log("CoreSched: allocating cpus " + str(cpus) + " to _default")
        reservations["_default"] = cpus[:]

        self.reserveCores(reservations)

    def reserveCores (self, reservations):
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
        self.reserveDefault(default)

        for cgroup in self.get_cgroups():
            cpus = reservations.get(cgroup, default)

            logger.log("CoreSched: reserving " + cgroup + " " + str(cpus))

            file("/dev/cgroup/" + cgroup + "/cpuset.cpus", "w").write( self.listToRange(cpus) + "\n" )

    def reserveDefault (self, cpus):
        if not os.path.exists("/etc/vservers/.defaults/cgroup"):
            os.makedirs("/etc/vservers/.defaults/cgroup")

        file("/etc/vservers/.defaults/cgroup/cpuset.cpus", "w").write( self.listToRange(cpus) + "\n" )

    def listToRange (self, list):
        """ take a list of items [1,2,3,5,...] and return it as a range: "1-3,5"
            for now, just comma-separate
        """
        return ",".join( [str(i) for i in list] )

# a little self-test
if __name__=="__main__":
    x = CoreSched()

    print "cpus:", x.listToRange(x.get_cpus())
    print "cgroups:", ",".join(x.get_cgroups())

    # a quick self-test for ScottLab slices sl_test1 and sl_test2
    #    sl_test1 = 1 core
    #    sl_test2 = 1 core

    rspec_sl_test1 = {"cpu_cores": 1}
    rec_sl_test1 = {"_rspec": rspec_sl_test1}

    rspec_sl_test2 = {"cpu_cores": 1}
    rec_sl_test2 = {"_rspec": rspec_sl_test2}

    slivers = {"sl_test1": rec_sl_test1, "sl_test2": rec_sl_test2}

    x.adjustCores(slivers)

