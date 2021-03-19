import os
import sys
import argparse
import subprocess

from . import stat_info, rstat_info, watchstat, Timeout, SoftTimeout

try:
    from StringIO import StringIO
except Exception:
    from io import StringIO


class WatchAction(argparse.Action):
    def __init__(self, *args, **kwargs):
        if kwargs.get("default") is None:
            kwargs["default"] = dict()
        argparse.Action.__init__(self, *args, **kwargs)

    def __call__(self, p, ns, path, opt):
        watchdict = getattr(ns, self.dest)
        sopt = opt.lstrip("-")
        if sopt not in rstat_info:
            raise RuntimeError("bad option for WatchAction")
        stat_index = rstat_info[sopt]
        stat_field = "st_" + stat_info[stat_index][1]
        path = os.path.realpath(path)
        if path not in watchdict:
            watchdict[path] = list()
        watchdict[path].append(stat_field)
        setattr(ns, self.dest, watchdict)


def parse_args(args):
    p = argparse.ArgumentParser(
        description="Execute a command whenever a file's status changes.",
    )

    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Echo to stderr whenever the trigger is hit. Repeatable.",
    )

    # Register an option for each stat field.
    stat_opts = p.add_argument_group("Status fields")
    for index in stat_info:
        opt, field, desc = stat_info[index]
        stat_opts.add_argument(
            "-" + opt,
            "--" + field,
            dest="watch",
            action=WatchAction,
            metavar="PATH",
            help="Watch PATH for " + desc,
        )

    g = p.add_argument_group("General options")
    g.add_argument(
        "-0",
        "--initial-run",
        action="store_true",
        help="Run the command once after the first stat."
        " This does not count towards the number of runs counted by -l."
        " The command is run once for each monitored path.",
    )
    g.add_argument(
        "-l",
        "--limit",
        type=int,
        metavar="N",
        help="Limit to N runs of command. 0 means no limit. Default 1.",
    )
    g.add_argument(
        "-t",
        "--interval",
        type=int,
        default=1000,
        metavar="N",
        help="Poll the status every N milliseconds (default %(default)s).",
    )
    g.add_argument(
        "--timeout",
        type=int,
        default=0,
        metavar="N",
        help="Exit (code 0) after N seconds.",
    )
    g.add_argument(
        "--softtimeout",
        type=int,
        default=0,
        metavar="N",
        help="Exit (code 3) after N seconds if the command has not been run.",
    )
    g.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Keep watching even if command fails. Implies -r and -l0.",
    )
    g.add_argument(
        "-r",
        "--retry",
        action="store_true",
        help="Keep watching even if file does not exist yet.",
    )
    g.add_argument(
        "-I",
        "--interp",
        metavar="DELIM",
        help="Interpolate command args by replacing DELIM|X|DELIM with values"
        " from the file's stat results. X is a short or long option name"
        " from 'Status fields' above, or the keyword 'path' to substitute"
        " the (real) path of the triggering file.",
    )

    g = p.add_argument_group("Positional arguments")
    g.add_argument("command", help="Command to run when status changes.")
    g.add_argument(
        "args",
        nargs="*",
        help="Args passed to command. Interpreted specially with -I.",
    )

    opts = p.parse_args(args)

    if opts.force:
        opts.retry = True
        if opts.limit is None:
            opts.limit = 0

    if opts.limit is None:
        opts.limit = 1

    if not opts.watch:
        p.error("no paths to watch")

    return opts


def find_tokens(string, delim):
    """Return an iterator over delim|key|delim tokens in string.

    Each item from the iterator is (offset, key) where offset is the offset
    of the start of the token in the string. (The end offset of the token can
    be computed as 'offset + len(key) + 2*len(delim)' if necessary).
    """
    delim_length = len(delim)
    # Start of the next token.
    delim_offset = string.find(delim)
    while delim_offset >= 0:
        # Start of the current token.
        token_offset = delim_offset

        # Start of the key within the token.
        key_offset = token_offset + delim_length

        # Find the next delimiter. This ends the token.
        delim_offset = string.find(delim, key_offset)

        # Error if there is no matching delimiter.
        if delim_offset < 0:
            raise ValueError("delimiter mismatch")

        # Extract the key from the string.
        # Ignore repeated delimiters (empty keys).
        if delim_offset != key_offset:
            yield token_offset, string[key_offset:delim_offset]

        # Find the start of the next delimiter pair.
        delim_offset = string.find(delim, delim_offset + delim_length)


def interpolate_argument(string, delim, status, **extra_keys):
    """Interpolate a single argument string containing delim|X|delim tokens.

    Replaces such tokens with status[F], where F is the field corresponding
    to the stat key X. The delimiter can be escaped by repeating it.

    Raises ValueError if the string is invalid (i.e. mismatched delimiters).
    """
    # Result of interpolation.
    interp = StringIO()

    # Interpolate the string from the delimiters.
    last_offset = 0
    for offset, key in find_tokens(string, delim):
        # Copy the next portion containing no tokens.
        interp.write(string[last_offset:offset])

        # Interpolate the token.
        if key:
            if key.lower() in rstat_info:
                field = rstat_info[key]
                interp.write(repr(status[field]))
            elif key in extra_keys:
                interp.write(extra_keys[key.lower()])
            else:
                raise ValueError("bad stat key {0!r}".format(key))

        # Skip the token.
        last_offset = offset + len(key) + 2 * len(delim)

    # Copy the final portion containing no tokens.
    interp.write(string[last_offset:])
    return interp.getvalue()


def interpolate_argument_vector(argv, delim, status, **keys):
    """Interpolate stat values from argv with args containing delim|X|delim.

    Doesn't interpolate the command name (argv[0]).

    Extra keyword arguments are substituted directly if present.
    """
    return [argv[0]] + [
        interpolate_argument(arg, delim, status, **keys) for arg in argv[1:]
    ]


def make_command_callback(command_argv, interp=None, force=False):
    """
    Wrapper function to bind a callback function to the command-line options.
    """

    def command_callback(p, diff_fields, last_stat, next_stat):
        # Interpolate the arguments using the stat results if we want.
        argv = command_argv
        if interp:
            argv = interpolate_argument_vector(argv, interp, next_stat, path=p)

        # Run the command. Succeed if the command succeeds.
        # Ignore errors with --force.
        try:
            code = subprocess.call(argv)
        except OSError:
            if not force:
                raise
        return force or code == 0

    return command_callback


def quote_argv(argv):
    try:
        from shlex import quote
    except Exception:
        from pipes import quote

    return " ".join(map(quote, argv))


def main():
    opts = parse_args(sys.argv[1:])

    argv = [opts.command] + (opts.args or [])
    command_callback = make_command_callback(argv, opts.interp, opts.force)

    # If we're in verbose mode, add some output to the callback.
    callback = command_callback
    if opts.verbose > 0:

        def callback(p, diff_fields, last_stat, next_stat):
            sys.stderr.write("running " + quote_argv(argv) + "\n")

            # For extra verbosity, dump what differed.
            if opts.verbose > 1:
                for index in diff_fields:
                    try:
                        opt, field, desc = stat_info[index]
                    except KeyError:
                        index = rstat_info[index]
                        opt, field, desc = stat_info[index]
                    old, new = last_stat[index], next_stat[index]
                    sys.stderr.write(
                        "st_{0} changed from {1!r} to {2!r}\n".format(
                            field, old, new
                        )
                    )

            result = command_callback(p, diff_fields, last_stat, next_stat)
            sys.stderr.write("callback returned {0!r}\n".format(result))
            return result

    # With --initial-run, run the command before beginning the watch.
    if opts.initial_run:
        for path, watchlist in opts.watch.items():
            callback(path, set(watchlist), None, os.stat(path))

    try:
        watchstat(
            list(opts.watch.items()),
            callback,
            interval=opts.interval,
            limit=opts.limit,
            retry=opts.retry,
            softtimeout=opts.softtimeout,
            timeout=opts.timeout,
        )
    except KeyboardInterrupt:
        pass
    except SoftTimeout:
        return 3
    except Timeout:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
