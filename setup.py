#!/usr/bin/python
#
# Setup script for the Node Manager application
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id: setup.py,v 1.5 2007/02/12 23:00:31 faiyaza Exp $
#

from distutils.core import setup, Extension

setup(
    ext_modules=[
    Extension('sioc', ['sioc.c']),
    ],
    py_modules=[
    'accounts',
    'api',
    'conf_files',
    'config',
    'curlwrapper',
    'database',
    'delegate',
    'logger',
    'net',
    'nm',
    'plcapi',
    'proper',
    'safexmlrpc',
    'sliver_vs',
    'sm',
    'ticket',
    'tools',
	'bwmon'
    ],
    scripts = [
    'forward_api_calls',
    ],
    )
