# First non-increasing timestamp spacing receipt

This is a read-only streaming Rust analysis of the finalized
`normal-tracked/trace.tsv.gz`. It stops after 32 rows following the first
non-increasing timestamp. The gzip producer exits with SIGPIPE (status 141)
when the analyzer stops; the analyzer exits 0 (`status.txt`). No simulation,
timestep setting, deduplication, or acceptance rule was changed.

Command:

```sh
gzip -dc ../../normal-tracked/trace.tsv.gz | ./analyze > excerpt.tsv 2> summary.txt
```

The analyzer reads 9,736,256 data rows and finds the first non-increasing pair
at data row 9,736,224 (file lines 9,736,224 and 9,736,225), matching the
tracked checker. Both decimal timestamps are exactly
`2.56990362212805523e-01`; parsing them as binary64 gives the same bits
`0x3fd07287b445d61f` and `delta_f64=0`. At this magnitude the adjacent binary64
spacing is `5.5511151231257827e-17 s`.

The local spacing is not a single abrupt duplicate in an otherwise coarse
sequence. In the final 14 advancing records before the duplicate, `dt` drops
from `3.44e-14` to `5.55e-17 s` (one local binary64 ULP), with intermediate
steps `1.54e-14`, `3.44e-15`, `1.11e-15`, `2.28e-15`, `5.00e-16`,
`9.99e-16`, `2.22e-16`, `4.44e-16`, `1.11e-16`, `2.22e-16`, and two more
one-ULP steps. The next two advancing records each move one ULP; later
steps grow to three and five ULP (1.665e-16 and 2.776e-16 s). This supports progressive solver-step
collapse to representable-time spacing followed by a same-time callback; it
does not identify the circuit event that caused the collapse.

`excerpt.tsv` retains 65 records: 32 before the bad row, the bad row,
and 32 after. `node-summary.txt` measures its first 64 records
(file lines 9,736,193–9,736,256). At the duplicate, q/en remain exactly 5 V and fault 0 V;
analog state still changes: `iVac +1.9603e-7 A`, `gate -7.6908e-15 V`,
`vcomp -4.4409e-16 V`, `icomp -2.2871e-13 V`, and the largest voltage-node
change is `acsrc/acn -1.2064e-10 V`. Over that 64-record window, gate spans 53.816 mV,
ICOMP spans 63.325 µV, and VCOMP spans 53.712 nV. This is a numerical
same-time callback with evolving analog state, rather than a repeated static
row; q/en/fault do not toggle at the first duplicate.

Artifacts:

- `analyze.rs`, `analyze`: streaming analyzer and locally compiled binary.
- `excerpt.tsv`: header, 31 records before the pair, the pair, and 32 after.
- `summary.txt`: first pair, binary64 bits/ULP, and minimum positive spacing.
- `node-summary.txt`: local dt and per-node duplicate/window changes.
- `status.txt`: expected `gzip=141 analyzer=0` early-stop status.
