# LL05 independent review (event-aware-normal-v1)

Status: **not accepted; capture export is incomplete, so no normal-screen
verdict is available**.

This review is read-only. It covers only the parent-owned LL05 attempt under
`full-LL05-initialized/LL05` and does not restart the run, open its FIFO, or
alter any source/report file.

## Source binding

`case.json` declares LL05 at 120.000000000 V RMS and 187.407220031000 ohm.
The generated deck differs from the accepted baseline `cold.cir` in exactly
the two intended scalar substitutions:

```diff
-.param RFREQ=16.2k VAC_RMS=120 FLINE=60 VB_INIT=0 VD_INIT=0
-.param RLOAD=190 TSTOP=650m STEP=500n
+.param RFREQ=16.2k VAC_RMS=120.000000000 FLINE=60 VB_INIT=0 VD_INIT=0
+.param RLOAD=187.407220031000 TSTOP=650m STEP=500n
```

The five includes (`authored_logic_hysteretic.inc`, `clamp.inc`,
`protection.inc`, `standby.inc`, and `ucc28180-pwm-latch.inc`) compare
byte-for-byte with the accepted baseline. The aggregate include digest is
`c614d6bf0aad5a5a200cbbf46ce564d2dc7aa4e7b0a210a6afecc17b74abaf24`, and the
generated deck digest is
`f85b4a622d8bf303e3f2f1646bb2cc977b03d24b655d4b48a14abadb8677528f`.

## Capture and export state

The native host reached the requested endpoint and wrote metadata reporting
`solver_stopped`, `sim_s=0.650000000000000022`, 30,103,973 callback rows,
58 repeated timestamps, zero backwards steps, and `first_invalid=true`.
That metadata is diagnostic only and does not establish a usable trace.

The raw gzip is 783,985,070 bytes (SHA-256
`9613208d7ea7c0369167e6c2fb93c6fe3915e07be59671fe3e46d57a5cf0b5bd`), but
the parent observed `gzip -t` failure (`incomplete deflate`) and a binary
decompressed prefix rather than a complete native trace stream. The parent
runner and pigz were waiting on the FIFO drain with the native host already
gone; no writer was observable. The cause is not proven in this review.

Because the raw artifact is incomplete, the runner did not produce the
event-audit or event-metrics reports, a decoded row count, or a normalizer
report. Consequently there is no independently measured LL05 value for:

* event-aware bus/input/current/energy screens or their margins;
* equal-time group count, maximum group size, or boundary ambiguity;
* endpoint row/timestamp agreement beyond the host metadata;
* source-normalized output coverage.

The only recorded duplicate count is the host callback metadata value 58;
it is not a substitute for the raw15 event-audit result. No electrical screen
should be inferred from it, and no result should be promoted to
`complete_review_pending` acceptance.

The accepted baseline remains the policy reference (`event-aware-normal-v1`),
but LL05 has not supplied the complete 31-vector evidence needed to compare
against its 120 V baseline metrics. Preserve the raw file and failure logs for
transport diagnosis; rerun only after the parent resolves the incomplete
FIFO/gzip export cause.
