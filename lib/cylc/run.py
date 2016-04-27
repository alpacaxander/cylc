#!/usr/bin/env python

# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2016 NIWA
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

"""Provide the main function for "cylc run" and "cylc restart"."""

import re
import sys

from cylc.daemonize import daemonize
from cylc.scheduler import SchedulerStop, SchedulerError
from cylc.cfgspec.globalcfg import GLOBAL_CFG
import cylc.flags
from cylc.version import CYLC_VERSION


def print_blurb():
    logo = (
        "            ,_,       \n"
        "            | |       \n"
        ",_____,_, ,_| |_____, \n"
        "| ,___| | | | | ,___| \n"
        "| |___| |_| | | |___, \n"
        "\_____\___, |_\_____| \n"
        "      ,___| |         \n"
        "      \_____|         \n"
    )
    license = """
The Cylc Suite Engine [%s]
Copyright (C) 2008-2016 NIWA
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
This program comes with ABSOLUTELY NO WARRANTY;
see `cylc warranty`.  It is free software, you
are welcome to redistribute it under certain
conditions; see `cylc conditions`.

  """ % CYLC_VERSION

    logo_lines = logo.splitlines()
    license_lines = license.splitlines()
    lmax = max(len(line) for line in license_lines)
    for i in range(len(logo_lines)):
        print logo_lines[i], ('{0: ^%s}' % lmax).format(license_lines[i])
    print


def main(name, start):
    # Parse the command line:
    server = start()

    # Print copyright and license information
    print_blurb()

    # Create run directory tree and get port.
    try:
        GLOBAL_CFG.create_cylc_run_tree(server.suite)
        server.configure_pyro()
    except Exception as exc:
        if cylc.flags.debug:
            raise
        else:
            sys.exit(exc)

    # Daemonize the suite
    if not server.options.no_detach and not cylc.flags.debug:
        daemonize(server)

    try:
        server.configure()
        if server.options.profile_mode:
            import cProfile
            import pstats
            prof = cProfile.Profile()
            prof.enable()
        server.run()
    except SchedulerStop, x:
        # deliberate stop
        print str(x)
        server.shutdown()

    except SchedulerError, x:
        print >> sys.stderr, str(x)
        server.shutdown()
        sys.exit(1)

    except KeyboardInterrupt as x:
        import traceback
        try:
            server.shutdown(str(x))
        except Exception as y:
            # In case of exceptions in the shutdown method itself.
            traceback.print_exc(y)
            sys.exit(1)

    except (KeyboardInterrupt, Exception) as x:
        import traceback
        traceback.print_exc(x)
        print >> sys.stderr, "ERROR CAUGHT: cleaning up before exit"
        try:
            server.shutdown('ERROR: ' + str(x))
        except Exception, y:
            # In case of exceptions in the shutdown method itself
            traceback.print_exc(y)
        if cylc.flags.debug:
            raise
        else:
            print >> sys.stderr, "THE ERROR WAS:"
            print >> sys.stderr, x
            print >> sys.stderr, "use --debug to turn on exception tracebacks)"
            sys.exit(1)

    else:
        # main loop ends (not used?)
        server.shutdown()

    if server.options.profile_mode:
        prof.disable()
        import StringIO
        string_stream = StringIO.StringIO()
        stats = pstats.Stats(prof, stream=string_stream)
        stats.sort_stats('cumulative')
        stats.print_stats()
        print string_stream.getvalue()
