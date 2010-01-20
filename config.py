#!/usr/bin/python
#
# $Id$
# $URL$
#
# Parses the PLC configuration file /etc/planetlab/plc_config, which
# is bootstrapped by Boot Manager, but managed by us.
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id$
#

import os

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
            if hasattr(self, 'PLC_API_CA_SSL_CRT'):
                self.cacert = self.PLC_API_CA_SSL_CRT
            elif os.path.exists('/usr/boot/cacert.pem'):
                self.cacert = '/usr/boot/cacert.pem'
            else:
                raise Exception, "No boot server certificate bundle available"
        else:
            uri = "http://"
            self.cacert = None

        uri += self.PLC_API_HOST + \
               ":" + str(self.PLC_API_PORT) + \
               "/" + self.PLC_API_PATH + "/"

        self.plc_api_uri = uri


if __name__ == '__main__':
    from pprint import pprint
    pprint(Config().__dict__.items())
