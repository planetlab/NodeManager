#!/usr/bin/python -tt

# Author: Daniel Hokka Zakrisson <daniel@hozac.com>
# $Id$

import os
import logger
import subprocess

class IPTables:
    IPTABLES_RESTORE = "/sbin/iptables-restore"

    def __init__(self):
        self.extifs = []
        self.intifs = []
        self.pfs = []

    def add(self, table, chain, rule):
        self.rules[table][chain].append(rule)

    def add_ext(self, interface):
        self.extifs.append(interface)

    def add_int(self, interface):
        self.intifs.append(interface)

    def add_pf(self, pf):
        # XXX Should make sure the required fields are there
        self.pfs.append(pf)

    def commit(self):
        # XXX This should check for errors
        #     and make sure the new ruleset differs from the current one

        if (len(self.extifs) + len(self.intifs) + len(self.pfs)) == 0:
            return True

        restore = subprocess.Popen([self.IPTABLES_RESTORE, "--noflush"], stdin=subprocess.PIPE)
        restore.stdin.write("""*filter
:INPUT ACCEPT [0:0]
:FORWARD ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:LOGDROP - [0:0]
:SLICESPRE - [0:0]
:SLICES - [0:0]
:PORTFW - [0:0]

-F INPUT
-F FORWARD
-F OUTPUT

-A LOGDROP -j LOG
-A LOGDROP -j DROP
-A OUTPUT -j BLACKLIST
-A OUTPUT -m mark ! --mark 0/65535 -j SLICESPRE
-A FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
""")

        for int in self.intifs:
            for ext in self.extifs:
                restore.stdin.write("-A FORWARD -i %s -o %s -j ACCEPT\n" % (int, ext))
            restore.stdin.write("-A SLICESPRE -o %s -j SLICES\n" % int)

        restore.stdin.write("-A FORWARD -m state --state NEW -j PORTFW\n")
        for pf in self.pfs:
            rule = "-A PORTFW -p %s -d %s " % (pf['protocol'], pf['destination'])
            if 'interface' in pf:
                rule += "-i %s " % pf['interface']
            if 'source' in pf:
                rule += "-s %s " % pf['source']
            rule += "--dport %s" % pf['new_dport']
            restore.stdin.write(rule + "\n")

        restore.stdin.write("-A FORWARD -j LOGDROP\n")

        # This should have a way to add rules
        restore.stdin.write("-A SLICES -j LOGDROP\n")
        restore.stdin.write("""COMMIT
*nat
:PREROUTING ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:PORTFW - [0:0]
:MASQ - [0:0]

-F PREROUTING
-F POSTROUTING
-F OUTPUT
""")

        for ext in self.extifs:
            restore.stdin.write("-A MASQ -o %s -j MASQUERADE\n")

        for pf in self.pfs:
            rule = "-A PORTFW -p %s " % pf['protocol']
            if 'interface' in pf:
                rule += "-i %s " % pf['interface']
            if 'source' in pf:
                rule += "-s %s " % pf['source']
            rule += "--dport %s -j DNAT --to %s:%s" % (pf['dport'], pf['destination'],
                    pf['new_dport'])
            restore.stdin.write(rule + "\n")

        restore.stdin.write("COMMIT\n")
        restore.stdin.close()
        return restore.wait() == 0
