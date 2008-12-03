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
    py_modules=[
        'accounts',
        'api',
        'api_calls',
        'bwmon',
        'conf_files',
        'config',
        'curlwrapper',
        'controller',
        'database',
        'iptables',
        'logger',
        'net',
        'nm',
        'plcapi',
        'safexmlrpc',
        'sliver_vs',
        'sm',
        'ticket',
        'tools',
        ],
    scripts = [
        'forward_api_calls',
        ],
    packages =[
        'plugins',
        ],
    )
