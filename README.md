# watchstat

Execute a command whenever a file's status changes.

## Installation

May be installed via `pip install watchstat`.

## Usage

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

## Examples

Examples are shown using `bash` syntax to perform different behaviors based on
the exit status of `watchstat`.

* Re-compile a file whenever it is changed:

  ```sh
  watchstat --force -m test.c -- gcc -Wall -pedantic test.c -o test
  ```

  By default, `watchstat` cancels if the command fails, so to continue even
  after a compile error we use `--force` (`-f`) which implies `--retry` and
  `-limit=0` (retry forever). To exit `watchstat` gracefully, issue an interrupt
  with Ctrl+C.

* Compile a file if it changes in the next 5 seconds:

  ```sh
  if ! watchstat -m test.c --timeout 5 -- gcc test.c -o test 2>/dev/null; then
    echo "compile errors detected"
  fi
  ```

  - If the file does not change within 5 seconds, nothing is done.
  - If the file does change, the gcc command is run.
  - If the file changes and gcc runs but fails, "compile errors detected"
    is echoed.

* Echo whether a file changes in the next five seconds:

  ```sh
  if ! watchstat -m test.c --softtimeout 5 echo "File updated"; then
    echo "Timed out"
  fi
  ```

  - If the file is changed in the next 5 seconds, echoes "File updated".
  - If the file is not changed in the next 5 seconds, echoes "Timed out".

* Display the contents of a file when it is created:

  ```sh
  watchstat --retry -c pid.txt cat pid.txt
  ```

  Without `--retry` (`-r`), `watchstat` would fail if the file doesn't exist
  after the first poll time interval.

* A more descriptive echo when the file size changes using interpolation:

  ```sh
  $ watchstat -r -0 -s resizeme.txt -I% echo "Size of %path% is %size% bytes"
  Size of /home/user/resizeme.txt is 0 bytes
  Size of /home/user/resizeme.txt is 118 bytes
  ```

  With `--initial-run` (`-0`), the message is also displayed *now*
  (as soon as `watchstat` runs).

* Note a pretty mtime every time a file changes using shell constructs,
  with a poll time of only 5 seconds:

  ```sh
  $ watchstat -l0 -t5000 -m README.md -IX \
    -- bash -c date -r "XpathX" +"$(basename XpathX) changed at %F-%T.%N"
  README.md changed at 2021-03-19-13:53:15.791771219
  README.md changed at 2021-03-19-13:53:32.801771159
  ```
