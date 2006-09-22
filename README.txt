THE NEW NODE MANAGER
====================

This is a very preliminary version of the new node manager.  Currently
it is set up to download slices.xml; however, not all of the
implemented functionality is accessible via slices.xml.

FILES
=====

accounts.py - Account management functionality generic between
delegate accounts and VServers.

api.py - XMLRPC interface to Node Manager functionality.  Runs on port
812, supports a Help() call with more information.

bwcap.py - Sets the bandwidth cap via the bwlimit module.  The bwlimit
calls are commented out because they've been giving me a bunch of
errors.

config.py - Configuration parameters.  You'll probably want to change
SA_HOSTNAME to the PLC address.

database.py - The dreaded NM database.  The main class defined is a
dict subclass, which both indexes and stores various records.  These
records include the sliver/delegate records, as well as the timestamp,
node bw cap, and any other crap PLC wants to put there.

delegate.py - Create and delete delegate accounts.  These accounts
have low space overhead (unlike a VServer) and serve to authenticate
remote NM users.

forward_api_calls.c - The forward_api_calls program proxies stdin to
the Unix domain socket /tmp/node_mgr_api, letting Node Manager take
advantage of ssh authentication.  It is intended for use as a shell on
a special delegate account.

logger.py - This is a very basic logger.

Makefile - For compiling forward_api_calls.

nm.py - The main program.

plc.py - Downloads and parses slices.xml, reads the node id file.

README.txt - Duh.

sliver.py - Handles all VServer functionality.

ticket.py - Not used at the moment; contains a demonstration of
xmlsec1.

tools.py - Various convenience functions for functionality provided by
Linux.

RUNNING
=======

Change SA_HOSTNAME in config.py and run nm.py.  No bootstrapping
required.

INTERNALS
=========

At the moment, the main thread loops forever, fetching slices.xml and
updating the database.  Other threads handle incoming API connections
(each connection is handled by a separate thread) and the database
dumper.  There is also one thread per account, which supervises
creation/deletion/resource initialization for that account.  The other
threads request operations by means of a queue.

Other than the queues, the threads synchronize by acquiring a global
database lock before reading/writing the database.  The database
itself is a collection of records, which are just Python dicts with
certain required fields.  The most important of these fields are
'timestamp', 'expiry', and 'record_key'.  'record_key' serves to
uniquely identify a particular record; the only naming conventions
followed are that account records have record_key <account
type>_<account name>; thus sliver princeton_sirius has record_key
'sliver_princeton_sirius'.

The two main features that will not be familiar from the old node
manager are delegates and loans.  Delegates, as described above, are
lightweight accounts whose sole purpose is to proxy NM API calls from
outside.  The current code makes a delegate account 'del_snoop' that's
allowed to spy on everyone's RSpec; you'll need to change the key in
plc.py order to use it.  Loans are resource transfers from one sliver
to another; the format for loans is a list of triples: recipient
sliver, resource type, amount.  Thus for princeton_sirius to give 20%
guaranteed CPU to princeton_eisentest, it would call

api.SetLoans(['princeton_eisentest', 'nm_cpu_guaranteed_share', 200])

provided, of course, that it has 200 guaranteed shares :)

POSTSCRIPT
==========

The log file will come in a great deal of use when attempting to
use/debug node manager; it lives at /var/log/pl_node_mgr.log.  If you
break the DB, you should kill the pickled copy, which lives at
<config.py:DB_FILE>.

I have been refactoring the code constantly in an attempt to keep the
amount of glue to a minimum; unfortunately comments quickly grow stale
in such an environment, and I have not yet made any attempt to comment
reasonably.  Until such time as I do, I'm on the hook for limited
support of this thing.  Please feel free to contact me at
deisenst@cs.princeton.edu.
