#!/usr/bin/env python

__version__ = '0.1.0'

import datetime
import gc
import optparse
import os
import signal
import sys

class NagiosCheck:
    """Subclass me and override `check()` to define your own Nagios
    check.

    See `examples/` for examples.

    You *must* override the following from your subclass:

    - `NagiosCheck.usage`:   Usage information for users.
    - `NagiosCheck.version`: The release version of your check.
    - `NagiosCheck.check()`: Actual check logic.

    """
    usage = '[options]'
    version = '0.1.0'

    def __init__(self):
        self.options = []
        self.parser = optparse.OptionParser(
          usage='%%prog %s' % self.usage,
          version='%%prog %s' % self.version)

        # All checks must implement the following options as per the 
        # Nagios plug-in development guidelines.
        self.parser.add_option(
          '-v', '--verbose', action='count', dest='verbosity')

    def add_option(self, short, long=None, argument=False, desc=None):
        option_strings = []
        kwargs = {}

        option_strings.append('-%s' % short)
        if long is not None:
            option_strings.append('--%s' % long)

        if argument is None:
            kwargs['action'] = 'store_true'
            kwargs['dest'] = short
        else:
            kwargs['dest'] = argument
        kwargs['help'] = desc

        self.parser.add_option(*option_strings, **kwargs)

    def check(self, opts, args):
        raise NotImplementedError('You forgot to override check()!')

    def expired(self):
        """Our parent has died.  Follow suit.

        Our parent has terminated, probably because a timeout had
        recently expired.  You can override this method to clean up
        after yourself, but do it quickly.  There is absolutely no
        guarantee that you will get anywhere useful before a `SIGKILL`
        comes hurtling down the pipe.

        """
        sys.exit(2)

    def run(self, argv=None):
        if argv is None:
            argv = sys.argv
        try:
            try:
                (opts, args) = self.parser.parse_args(argv[1:])

                self.verbosity = getattr(opts, 'verbosity') or 0
                if self.verbosity > 3:
                    self.verbosity = 3

                # When the NRPE server forks us (`popen(3)`) and its 
                # guardian process dies from `command_timeout` expiry, 
                # the process group should get `SIGTERM`'d.
                old_handler = signal.getsignal(signal.SIGTERM)
                signal.signal(signal.SIGTERM, _handle_sigterm)

                self.check(opts, args)

                signal.signal(signal.SIGTERM, old_handler)

                raise Status('unknown',
                  '%s.check() returned without raising %s.Status' %
                  (self.__class__.__name__, __name__))
            except Status, s:
                raise
            except Exception, e:
                raise Status('unknown',
                  'Unhandled Python exception: %r' % e)
            sys.exit(Status.EXIT_UNKNOWN)
        except Status, s:
            print s.output(self.verbosity)
            sys.exit(s.status)

class Status(Exception):
    """Stores check status.

    Usage:

    - Without perfdata::

        Status(nagioscheck.Status.EXIT_OK, 'Happy days')

    - This, less verbose, alternative is also acceptable::

        Status('ok', 'Happy days')

    Nagios perfdata is not (yet) supported.  (I don't use Nagios for
    performance monitoring.)

    """
    EXIT_OK = 0
    EXIT_WARNING = 1
    EXIT_CRITICAL = 2
    EXIT_UNKNOWN = 3

    def __init__(self, status, msg, perfdata=None):
        """Signal check status.

        Store either a single string or list of strings in `msg`.  If a
        list, the individual items should correspond to::

            msg[0]: A single line summary;
            msg[1]: Single line with additional information;
            msg[2]: Multi-line output for configuration debugging;
            msg[3]: Multi-line output for check script debugging.

        All four list elements are not mandatory.  Requests for verbose
        output will fall upwards until a suitable message is found.  For
        example, if `msg[0]` and `msg[2]` are defined, and output at
        verbosity level 1 (`msg[1]`) is requested, the string from
        `msg[0]` will be returned.

        `perfdata` is currently ignored.

        """
        # This contraption generates a dictionary of valid status 
        # constants from the `EXIT_*` class attributes defined at the 
        # very top of this class.  We use this dict for validation, and 
        # as a shortcut mechanism when a string is supplied as `status`.
        self.s_map = dict(
          map(lambda x: (x.replace('EXIT_', ''), getattr(Status, x),),
          filter(lambda x: x.startswith('EXIT_'), dir(Status))))
        # Or in other words...
        assert self.s_map['OK'] == 0
        # And now the inverse...
        self.i_map = dict((v, k) for k, v in self.s_map.iteritems())

        if isinstance(status, int):
            if status not in self.i_map.keys():
                raise ValueError('Invalid status code - see %s.%s' %
                  (__name__, self.__class__.__name__))
            self.status = status
        elif isinstance(status, str):
            if status.upper() not in self.s_map.keys():
                raise ValueError('Invalid status code - see %s.%s' %
                  (__name__, self.__class__.__name__))
            self.status = self.s_map[status.upper()]
        else:
            raise TypeError(
              'Expected an int or str as status, but got %r instead' %
              status)

        self.msg = []
        if isinstance(msg, str):
            self.msg.append(msg)
        elif isinstance(msg, list) or isinstance(msg, tuple):
            for i in range(4):
                try:
                    self.msg.append(str(msg[i]))
                except IndexError:
                    self.msg.append(None)

        self.perfdata = perfdata

    def __repr__(self):
        return '%s.%s(status=%r, msg=%r, perfdata=%r)' % (
          self.__module__, self.__class__.__name__,
          self.status, self.msg, self.perfdata)

    def __str__(self):
        return self.output()

    def output(self, verbosity=0):
        if verbosity not in range(4):
            raise ValueError('Verbosity should be one of 0, 1, 2, or 3')
        while self.msg[verbosity] == None:
            verbosity -= 1
        return '%s: %s' % (self.i_map[self.status], self.msg[verbosity])

def _handle_sigterm(signum, frame):
    checks = filter(
      lambda o: isinstance(o, NagiosCheck), gc.get_objects())
    for check in checks:
        check.expired()

def prettyprint_seconds_elapsed(seconds):
    return str(datetime.timedelta(seconds=seconds))
