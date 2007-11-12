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

clean:
	python setup.py clean
	rm -f forward_api_calls *.pyc build

.PHONY: all install clean

tags:
	find . '(' -name '*.py' -o -name '*.c' -o -name '*.spec' ')' | xargs etags 
