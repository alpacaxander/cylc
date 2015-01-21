#!/usr/bin/env python

# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2015 NIWA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

try:
    import Pyro.core
except ImportError, x:
    raise SystemExit("ERROR: Pyro is not installed")

import sys
from optparse import OptionParser
from suite_host import get_hostname
from time import sleep
from passphrase import passphrase
from owner import user
from port_file import port_retriever
import flags

class client( object ):
    def __init__( self, suite, pphrase=None, owner=user, host=get_hostname(),
            pyro_timeout=None, port=None ):
        self.suite = suite
        self.owner = owner
        self.host = host
        self.port = port
        if pyro_timeout:
            self.pyro_timeout = float(pyro_timeout)
        else:
            self.pyro_timeout = None
        self.pphrase = pphrase

    def get_proxy( self, target ):
        if self.port:
            if flags.verbose:
                print "Port number given:", self.port
        else:
            self.port = port_retriever( self.suite, self.host, self.owner ).get()

        # get a pyro proxy for the target object
        objname = self.owner + '.' + self.suite + '.' + target

        uri = 'PYROLOC://' + self.host + ':' + str(self.port) + '/' + objname
        # callers need to check for Pyro.NamingError if target object not found:
        proxy = Pyro.core.getProxyForURI(uri)

        proxy._setTimeout(self.pyro_timeout)

        if self.pphrase:
            proxy._setIdentification( self.pphrase )

        return proxy
