# watchstat

Execute a command whenever a file's status changes.

May be installed via `pip install watchstat`.

Usage is as follows:

```
usage: __main__.py [-h] [-v] [-m PATH] [-a PATH] [-c PATH] [-d PATH] [-i PATH]
                   [-M PATH] [-n PATH] [-u PATH] [-g PATH] [-s PATH] [-0]
                   [-l N] [-t N] [--timeout N] [--softtimeout N] [-f] [-r]
                   [-I DELIM]
                   command [args [args ...]]

Execute a command whenever a file's status changes.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Echo to stderr whenever the trigger is hit.
                        Repeatable.

Status fields:
  -m PATH, --mtime PATH
                        Watch PATH for modification time
  -a PATH, --atime PATH
                        Watch PATH for access time
  -c PATH, --ctime PATH
                        Watch PATH for status time
  -d PATH, --dev PATH   Watch PATH for device ID
  -i PATH, --ino PATH   Watch PATH for inode number
  -M PATH, --mode PATH  Watch PATH for protection mode
  -n PATH, --nlink PATH
                        Watch PATH for number of hard links
  -u PATH, --uid PATH   Watch PATH for user ID of owner
  -g PATH, --gid PATH   Watch PATH for group ID of owner
  -s PATH, --size PATH  Watch PATH for total size

General options:
  -0, --initial-run     Run the command once after the first stat. This does
                        not count towards the number of runs counted by -l.
                        The command is run once for each monitored path.
  -l N, --limit N       Limit to N runs of command. 0 means no limit. Default
                        1.
  -t N, --interval N    Poll the status every N milliseconds (default 1000).
  --timeout N           Exit (code 0) after N seconds.
  --softtimeout N       Exit (code 3) after N seconds if the command has not
                        been run.
  -f, --force           Keep watching even if command fails. Implies -r and
                        -l0.
  -r, --retry           Keep watching even if file does not exist yet.
  -I DELIM, --interp DELIM
                        Interpolate command args by replacing DELIM|X|DELIM
                        with values from the file's stat results. X is a short
                        or long option name from 'Status fields' above, or the
                        keyword 'path' to substitute the (real) path of the
                        triggering file.

Positional arguments:
  command               Command to run when status changes.
  args                  Args passed to command. Interpreted specially with -I.
```
