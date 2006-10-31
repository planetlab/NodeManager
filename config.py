#!/usr/bin/python
#
# Parses the PLC configuration file /etc/planetlab/plc_config, which
# is bootstrapped by Boot Manager, but managed by us.
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id$
#

class Config:
    """
    Parses Python configuration files; all variables in the file are
    assigned to class attributes.
    """

    def __init__(self, file = "/etc/planetlab/plc_config"):
        try:
            execfile(file, self.__dict__)
        except:
            raise Exception, "Could not parse " + file

        if int(self.PLC_API_PORT) == 443:
            uri = "https://"
        else:
            uri = "http://"

        uri += self.PLC_API_HOST + \
               ":" + str(self.PLC_API_PORT) + \
               "/" + self.PLC_API_PATH + "/"

        self.plc_api_uri = uri
