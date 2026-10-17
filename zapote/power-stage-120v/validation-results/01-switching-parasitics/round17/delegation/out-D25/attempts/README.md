# Attempt history

The first register calculation aborted (SIGABRT, subprocess return signal 6).
That attempt is **INDETERMINATE** and supplies no passing result. Its exact
C source is retained as `register_check-attempt1.c`.

Cause identified from the preserved source: the independently transcribed
register decoder swapped RED input-select bit 11 with FED input-select bit 12,
and consequently expected `DT_CFG[16:8]=0x04800`. The pinned ESP32-S3 TRM
v1.8 register 36.23 (p1379) and `mcpwm_struct.h:415-423` put RED at bit 11
and FED at bit 12. They agree; this was an evidence-harness transcription
error, not a firmware or vendor-source contradiction. The actual LL functions
caused the assertion to reject the wrong expectation.

The second attempt corrected only that transcription to `0x05000`, recorded
all stdout in `register_check.txt`, and passed. No firmware was changed.
The runner now retains each probe's stderr under `cache/` before reporting a
nonzero result as INDETERMINATE. The first runner captured but did not print
or save the assertion's stderr, so no exact assertion-error text is claimed.

Initial observed tool result:

```text
subprocess.CalledProcessError: Command '[...]/cache/register_check' died with <Signals.SIGABRT: 6>.
```
