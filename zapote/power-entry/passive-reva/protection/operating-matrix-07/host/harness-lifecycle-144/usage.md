# Command guard usage

`command_guard.py` is a small lifecycle and metadata guard for future campaign
commands. It is not an electrical checker and must not be used to rerun or
overwrite frozen campaign outputs.

Hash only an explicitly enumerated regular file list:

```sh
python3 host/harness-lifecycle-144/command_guard.py hash path/to/file path/to/other-file
```

Each input is opened with `O_NONBLOCK|O_NOFOLLOW`, checked with `fstat` before
reading, and rejected unless it is a regular file. FIFOs, directories, and
symlinks fail promptly. Do not pass a shell wildcard that could include a FIFO.

Run a future command with a fresh receipt and explicit working directory:

```sh
python3 host/harness-lifecycle-144/command_guard.py run \
  --timeout 3600 --receipt run-receipt.json --cwd /absolute/workdir -- \
  /absolute/path/to/program arg1 arg2
```

The executable is preflighted before spawn. The command runs in a dedicated
session/process group with inherited standard streams, so no parent-owned pipe
keeps readers alive. Success, failure, timeout, and SIGINT/SIGTERM interruption
are recorded in the receipt. On every completion path, including a leader that exits before its children, the remaining group receives bounded
SIGTERM then SIGKILL escalation; the leader is waited before the guard exits.
Receipts use exclusive creation and are never overwritten.

This helper does not guarantee cleanup after SIGKILL, host crashes, or children
that call `setsid()` to leave the process group. Keep the frozen runner45 and
postcapture scripts unchanged; use this guard around future launch and archive-analysis commands with fresh output locations.
The executable path is resolved before changing the child working directory.
CLI exit 124 denotes timeout, 128+signal denotes interruption, 125 denotes
a guard error, and ordinary command exit codes are preserved.
The receipt keeps the original child return code separately.
