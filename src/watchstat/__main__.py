import os
import sys
import argparse
import subprocess

from . import stat_info, rstat_info, watchstat


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
        path = os.path.realpath(path)
        if path not in watchdict:
            watchdict[path] = list()
        watchdict[path].append(stat_index)
        setattr(ns, self.dest, watchdict)


def parse_args(args):
    global stat_info
    p = argparse.ArgumentParser(
        description="Execute a command whenever a file's status changes.",
        epilog="If no options are selected, default is to watch mtime.",
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


def quote_argv(argv):
    try:
        from six.moves import shlex_quote, map
    except Exception:
        from shlex import quote as shlex_quote

    return " ".join(map(shlex_quote, argv))


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


def main(*args):
    global stat_info
    opts = parse_args(args)

    argv = [opts.command] + (opts.args or [])
    command_callback = make_command_callback(argv, opts.interp, opts.force)

    # If we're in verbose mode, add some output to the callback.
    callback = command_callback
    if opts.verbose > 0:

        def callback(diff_fields, last_stat, next_stat):
            sys.stderr.write("running " + quote_argv(argv) + "\n")

            # For extra verbosity, dump what differed.
            if opts.verbose > 1:
                for index in diff_fields:
                    opt, field, desc = stat_info[index]
                    old, new = last_stat[index], next_stat[index]
                    sys.stderr.write(
                        "st_{0} changed from {1!r} to {2!r}\n".format(
                            field, old, new
                        )
                    )

            result = command_callback(diff_fields, last_stat, next_stat)
            sys.stderr.write("callback returned {0!r}\n".format(result))
            return result

    # With --initial-run, run the command before beginning the watch.
    if opts.initial_run:
        callback(set(), None, os.stat(opts.path))

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
    sys.exit(main(*sys.argv[1:]))
