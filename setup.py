#!/usr/bin/python
#
# Setup script for the Node Manager application
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id: setup.py,v 1.1 2006/11/13 20:04:44 mlhuang Exp $
#

from distutils.core import setup

setup(
    py_modules=[
    'accounts',
    'api',
    'conf_files',
    'config',
    'curlwrapper',
    'database',
    'delegate',
    'logger',
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
    )
