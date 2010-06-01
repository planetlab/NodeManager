#
# Node Manager Makefile
#
# David Eisenstat <deisenst@cs.princeton.edu>
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id: Makefile,v 1.2 2006/11/13 20:04:44 mlhuang Exp $
#

# autoconf compatible variables
datadir := /usr/share
bindir := /usr/bin

all: forward_api_calls
	python setup.py build

forward_api_calls: forward_api_calls.c
	$(CC) -Wall -Os -o $@ $?
	strip $@

install:
	python setup.py install \
	    --install-purelib=$(DESTDIR)/$(datadir)/NodeManager \
	    --install-platlib=$(DESTDIR)/$(datadir)/NodeManager \
	    --install-scripts=$(DESTDIR)/$(bindir)
	install -m 444 README $(DESTDIR)/$(datadir)/NodeManager

clean:
	python setup.py clean
	rm -f forward_api_calls *.pyc build

.PHONY: all install clean

##########
tags:
	(find . '(' -name '*.py' -o -name '*.c' -o -name '*.spec' ')' ; ls initscripts/*) | xargs etags 

.PHONY: tags

########## sync
# for use with the test framework; push local stuff on a test node
# make sync NODE=vnode01.inria.fr
# specify TESTMASTER and BUILD if the key is not available yet

LOCAL_RSYNC_EXCLUDES	:= --exclude '*.pyc' 
RSYNC_EXCLUDES		:= --exclude .svn --exclude CVS --exclude '*~' --exclude TAGS $(LOCAL_RSYNC_EXCLUDES)
RSYNC_COND_DRY_RUN	:= $(if $(findstring n,$(MAKEFLAGS)),--dry-run,)
RSYNC			:= rsync -e "ssh -i $(NODE).key.rsa" -a -v $(RSYNC_COND_DRY_RUN) $(RSYNC_EXCLUDES)

ifdef NODE
NODEURL:=root@$(NODE):/
endif

sync: $(NODE).key.rsa
ifeq (,$(NODEURL))
	@echo "sync: You must define NODE on the command line"
	@echo "  e.g. make sync NODE=vnode01.inria.fr"
	@exit 1
else
	+$(RSYNC) ./ $(NODEURL)/usr/share/NodeManager/
	+$(RSYNC) ./initscripts/nm $(NODEURL)/etc/init.d/nm
endif

### fetching the key

TESTMASTER ?= testmaster.onelab.eu

ifdef BUILD
KEYURL:=root@$(TESTMASTER):$(BUILD)/keys/key1.rsa
endif

key: $(NODE).key.rsa

$(NODE).key.rsa:
ifeq (,$(KEYURL))
	@echo "sync: fetching $@ - You must define TESTMASTER, BUILD and NODE on the command line"
	@echo "  e.g. make sync TESTMASTER=testmaster.onelab.eu BUILD=2010.01.22--1l-f8-32 NODE=vnode01.inria.fr"
	@echo "  note that for now all test builds use the same key, so any BUILD would do"
	@exit 1
else
	@echo "FETCHING key"
	+scp $(KEYURL) $@
endif

### utility - find out the node name for a given BUILD

ifdef BUILD
NODEIPCOMMAND:=ssh root@$(TESTMASTER) cat $(BUILD)/arg-ips-node
endif

nodename:
ifeq (,$(NODEIPCOMMAND))
	@echo "nodename: You must define TESTMASTER and BUILD on the command line"
else
	$(NODEIPCOMMAND)
endif
