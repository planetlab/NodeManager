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

    def __init__(self, cgroup_var_name="cpuset.cpus", slice_attr_name="cpu_cores"):
        self.cpus = []
        self.cgroup_var_name = cgroup_var_name
        self.slice_attr_name = slice_attr_name

    def get_cgroup_var(self, name):
        """ decode cpuset.cpus or cpuset.mems into a list of units that can
            be reserved.
        """

        data = open("/dev/cgroup/" + name).readline().strip()

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

        logger.log("CoreSched (" + self.cgroup_var_name + "): available units: " + str(cpus))

        reservations = {}

        # allocate the cores to the slivers that have them reserved
        for name, rec in slivers.iteritems():
            rspec = rec["_rspec"]
            cores = rspec.get(self.slice_attr_name, 0)
            (cores, bestEffort) = self.decodeCoreSpec(cores)

            while (cores>0):
                # one cpu core reserved for best effort and system slices
                if len(cpus)<=1:
                    logger.log("CoreSched: ran out of units while scheduling sliver " + name)
                else:
                    cpu = cpus.pop()
                    logger.log("CoreSched: allocating unit " + str(cpu) + " to slice " + name)
                    reservations[name] = reservations.get(name,[]) + [cpu]

                cores = cores-1

        # the leftovers go to everyone else
        logger.log("CoreSched: allocating unit " + str(cpus) + " to _default")
        reservations["_default"] = cpus[:]

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
                logger.log("CoreSched: adding besteffort units to " + name + ". new units = " + str(reservations[name]))

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
            if cgroup in reservations:
                cpus = reservations[cgroup]
                logger.log("CoreSched: reserving " + self.cgroup_var_name + " on " + cgroup + ": " + str(cpus))
            else:
                # no log message for default; too much verbosity in the common case
                cpus = default

            file("/dev/cgroup/" + cgroup + "/" + self.cgroup_var_name, "w").write( self.listToRange(cpus) + "\n" )

    def reserveDefault (self, cpus):
        if not os.path.exists("/etc/vservers/.defaults/cgroup"):
            os.makedirs("/etc/vservers/.defaults/cgroup")

        file("/etc/vservers/.defaults/cgroup/" + self.cgroup_var_name, "w").write( self.listToRange(cpus) + "\n" )

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

