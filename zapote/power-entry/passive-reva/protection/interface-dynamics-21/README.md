# Revision 21: TPS54202 model import check

Date: 2026-09-22. This is a bounded attempt to replace the Revision 20 fixed
130 Ω AUX load with a manufacturer converter model. **No converter startup
waveform was obtained.** Revision 11 remains the latest compiled power-entry
candidate; this check does not add a TPS54202 to it.

## Source and identity

TI's [TPS54202 product page](https://www.ti.com/product/TPS54202) lists one
"TPS54202 Unencrypted PSpice Transient Model Package (Rev. C)" as
`SLVMBJ5C.ZIP`. The package was fetched on 2026-09-22 through
`https://www.ti.com/lit/zip/SLVMBJ5` (redirecting to TI's
`slvmbj5c.zip`). The received ZIP SHA-256 is
`39e524bc2cc9a71a22e8afb753ccc5f2f8ee16ca0f491763b52ba1eb9c16271b`.
Its sole `.LIB` member, `TPS54202_PSPICE_TRANS/TPS54202_TRANS.LIB`, is 96,538
bytes and has SHA-256
`2410b7f6f64162ffe6c3ca94565396870aa55e4cafbeccd2382bc2471d933d3d`.
These hashes identify the retrieved bytes; the ZIP and library are not copied
into this experiment directory.

The library header says `**$ENCRYPTED_LIB`, identifies PSpice 16.2.0p001 and
a 2017-12-07 model release, and says temperature effects are not modeled.
The named `TPS54202_TRANS` subcircuit contains a `$CDNENCSTART` block, as do
43 other sections of the library. The downloaded contents therefore conflict
with the product page's "Unencrypted" label. This observation does not show
whether TI's intended PSpice installation can execute the model.

## Import smoke and result

[The smoke deck](tps54202-model-smoke.cir) references the official subcircuit,
with a valid 3 V enable stimulus and minimal external buck elements. The goal
is only to test import/parsing. The `.include` path points to the library
extracted in `/tmp`; to repeat the check, download the identified ZIP and run:

```sh
unzip -p SLVMBJ5.zip TPS54202_PSPICE_TRANS/TPS54202_TRANS.LIB > /tmp/TPS54202_TRANS.LIB
shasum -a 256 /tmp/TPS54202_TRANS.LIB
run_ltspice -b tps54202-model-smoke.cir
```

`run_ltspice` here was the signed ADI LTspice 26.0.2 executable documented in
the [Revision 20 model receipt](../interface-dynamics-20/README.md). It exited
with code **1** in under six seconds. [Its simulation log](tps54202-model-smoke.log)
starts with `Expected device instantiation or directive here` at
`$CDNENCSTART` in the TI library and then reports errors on opaque encrypted
lines. [The process output](tps54202-model-smoke.stdout.log) is retained
separately. There is no successful transient or raw waveform. The fixture's
other component values were never exercised, so they must not be read as a
converter implementation or a load estimate.

TI's [current data sheet](https://www.ti.com/lit/ds/symlink/tps54202.pdf)
gives a typical internal soft-start time, but neither that value nor this
failed import determines the assembled AUX input-current waveform. The
[TPS54202 EVM guide](https://www.ti.com/lit/ug/slvuap3a/slvuap3a.pdf)
shows startup for its 24 V input and 5 Ω output load; its output-ramp plots
cannot be transferred to this candidate's 15 V rail and different load. The
[Revision 20 input audit](../interface-dynamics-20/input-provenance.md) remains
the boundary for source impedance, fault waveform and continuity claims.

## Next usable evidence

If this converter is selected, obtain a genuinely runnable official model in
a supported simulator, or measure its VIN input current and 5 V startup on
the chosen source and output network, including enable sequencing and load
steps. Keep the temperature limitation separate from electrical startup
results. This check does not justify substituting an arbitrary behavioral buck
model or treating the fixed resistor as the physical load.
