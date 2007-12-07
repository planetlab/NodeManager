#!/usr/bin/python
#
# Setup script for the Node Manager application
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id: setup.py,v 1.4 2006/11/28 21:36:06 mlhuang Exp $
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
    'bwmon',
    'iptables',
    ],
    scripts = [
    'forward_api_calls',
    ],
    )
