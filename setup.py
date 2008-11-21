#!/usr/bin/python
#
# Setup script for the Node Manager application
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id$
#

from distutils.core import setup, Extension

setup(
    ext_modules=[
    Extension('sioc', ['sioc.c']),
    ],
    py_modules=[
    'accounts',
    'api',
    'api_calls',
    'conf_files',
    'config',
    'curlwrapper',
    'database',
    'controller',
    'logger',
    'net',
    'nm',
    'plcapi',
    'vsys',
    'safexmlrpc',
    'sliver_vs',
    'sm',
    'ticket',
    'tools',
    'bwmon',
    'codemux',
    'iptables',
    ],
    scripts = [
    'forward_api_calls',
    ],
    )
