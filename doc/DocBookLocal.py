#!/usr/bin/env python

# PATHS to be set by the build system
# this is in ..
import api_calls
# in PLCAPI/doc
from DocBook import DocBook

def api_methods():
    api_function_list = []
    for func in dir(api_calls):
        try:
            f = api_calls.__getattribute__(func)
            if 'group' in f.__dict__.keys():
                api_function_list += [api_calls.__getattribute__(func)]
        except:
            pass
    return api_function_list

DocBook(api_methods ()).Process()
