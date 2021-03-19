import os
import sys
import stat
import time
import errno


__version__ = (1, 0, 0)


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
                fields = ("st_mtime",)
            next_status = try_stat(path, retry)
            last_status = stats[path]

            # Don't invoke callback if the path does not exist.
            if next_status is not None:
                # See if any status fields differ.
                diff_fields = set()
                if last_status is not None:
                    for field_spec in fields:
                        try:
                            last_field = last_status[field_spec]
                            next_field = next_status[field_spec]
                        except (IndexError, TypeError):
                            last_field = getattr(last_status, field_spec)
                            next_field = getattr(next_status, field_spec)
                            field_spec = field_spec[3:] # strip "st_"
                        if last_field != next_field:
                            diff_fields.add(field_spec)

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
