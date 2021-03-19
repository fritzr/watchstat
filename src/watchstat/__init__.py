import os
import sys
import stat
import time
import errno

try:
    from six.moves import StringIO
except Exception:
    from io import StringIO


__version__ = (1, 0)

stat_info = {
    stat.ST_MTIME: ("m", "mtime", "modification time"),
    stat.ST_ATIME: ("a", "atime", "access time"),
    stat.ST_CTIME: ("c", "ctime", "status time"),
    stat.ST_DEV: ("d", "dev", "device ID"),
    stat.ST_INO: ("i", "ino", "inode number"),
    stat.ST_MODE: ("M", "mode", "protection mode"),
    stat.ST_NLINK: ("n", "nlink", "number of hard links"),
    stat.ST_UID: ("u", "uid", "user ID of owner"),
    stat.ST_GID: ("g", "gid", "group ID of owner"),
    stat.ST_SIZE: ("s", "size", "total size"),
}


def _reverse_stat_info(stat_info):
    rinfo = dict()
    for index in stat_info:
        opt, field, desc = stat_info[index]
        rinfo[opt] = rinfo[field] = index
    return rinfo


rstat_info = _reverse_stat_info(stat_info)


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
    global rstat_info

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


class Timeout(Exception):
    pass


class SoftTimeout(Timeout):
    pass


def try_stat(path, retry):
    """
    Try to stat a path (with os.stat).

    If the path does not exist, the result depends on `retry`.
    If `retry` is True, simply return None. Otherwise raise OSError.

    Other OSErrors (such as EPERM) will be raised regardless of `retry`.
    """
    try:
        return os.stat(path)
    except OSError as ose:
        if ose.errno != errno.ENOENT:
            raise
        if not retry:
            raise


def watchstat(
    watchlist,
    callback,
    interval=1000,
    limit=0,
    retry=False,
    softtimeout=None,
    timeout=None,
):
    """
    Watch paths and invoke callback when its os.stat results change.

    The `watchlist` is a sequence of pairs (`path`, `fields`).
    The `fields` should be a list of ST_* constants from the `stat` module.
    These fields will be checked for differences in the corresponding file.
    If `fields` is empty, check the modification time by default.

    The `callback` is a callable accepting four arguments:
    (path, diff, old, new). The `old` and `new` arguments are returned
    directly from os.stat. The `diff` argument is the sequence of field
    indexes which differ between old and new.

    If the callback returns False, the loop breaks early.
    Otherwise the loop continues if the callback returns None or a value
    comparable as non-zero (e.g. True). This is done so that the return
    statement can be omitted for simple callbacks which should always continue;
    otherwise, returning True/False means continue/break respectively.

    The `interval` is the number of milliseconds to wait between os.stat calls
    on the same path. By default, wait for 1000 ms (1 second).

    The `limit` is the maximum number of times to invoke callback.
    If the limit is broken this function will return.

    If `timeout` is non-zero, raise Timeout after the given number of seconds.
    If `softtimeout` is non-zero, raise SoftTimeout after the given number of
    seconds, but only if the command has not run yet.

    If `retry` is True, retry (once per interval) even if the path does not
    exist after a previous attempt.
    """
    now = time.time()
    softtimeout = now + softtimeout if softtimeout else sys.maxsize
    timeout = now + timeout if timeout else sys.maxsize

    ncalls = 0

    stats = dict((path, try_stat(path, retry)) for path, fields in watchlist)

    while (
        (limit <= 0 or ncalls < limit)
        and (ncalls > 0 or now < softtimeout)
        and now < timeout
    ):

        continu = True
        sleep_dur = min(softtimeout - now, timeout - now, interval / 1000.0)
        time.sleep(sleep_dur)
        now = time.time()
        if (ncalls == 0 and now >= softtimeout) or now >= timeout:
            break

        for path, fields in watchlist:
            if not fields:
                fields = (stat.ST_MTIME,)
            next_status = try_stat(path, retry)
            last_status = stats[path]

            # Don't invoke callback if the path does not exist.
            if next_status is not None:
                # See if any status fields differ.
                diff_fields = set()
                if last_status is not None:
                    for field_index in fields:
                        last_field = last_status[field_index]
                        next_field = next_status[field_index]
                        if last_field != next_field:
                            diff_fields.add(field_index)

                # Invoke callback if status differs or the path was just created.
                if last_status is None:
                    diff_fields = set(fields)
                if diff_fields:
                    ncalls += 1
                    continu = callback(
                        path, diff_fields, last_status, next_status
                    )
                    if continu is not None and not continu:
                        break

            stats[path] = next_status
            now = time.time()
            if (
                (limit > 0 and ncalls >= limit)
                or (ncalls == 0 and now >= softtimeout)
                or (now >= timeout)
            ):
                continu = False
                break

        if continu is not None and not continu:
            break
        now = time.time()

    if ncalls == 0 and now >= softtimeout:
        raise SoftTimeout()

    if now >= timeout:
        raise Timeout()

    return ncalls
