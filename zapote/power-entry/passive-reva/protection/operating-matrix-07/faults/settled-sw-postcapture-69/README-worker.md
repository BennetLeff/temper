# SW-SHORT bounded post-capture packet

Candidate wrapper only; it launches no solver and does not decode while being
prepared. The fixed input is
`faults/settled-sw-short-59/full-SW-SHORT`; output is the no-clobber
`faults/settled-sw-postcapture-69/full-SW-SHORT` directory.

Before opening the gzip, `run.sh` requires the terminal runner/monitor exit
records plus the completed stage-1 capture, native fault42 export, and result
receipts. A nonzero runner result is retained as a legitimate switch-short
validator/gap outcome; validator success is never required to run diagnostics.
The stage-1/export/raw size and SHA-256 must agree. Source closure and all
tool hashes are checked, and the raw hash is checked again after every pass.

Passes are the full42 prefault selector at `.65`, event-aware normal15 audit,
event metrics using the selector's exact `last_selected_time_s`, and phase43
crest evidence with `--end-s .662`, expected edge `.6541666666667`, local
interval `[.65,.6583333333333]`, and tolerance `.01`. All child exit arrays,
stderr, selector reports, row counts, endpoints, and raw hashes are retained.
No legacy checker is included. This case can never be reported as a protection
`PASS`; node/detector precedence and `PROTECTION_GAP` remain parent review
concerns.

