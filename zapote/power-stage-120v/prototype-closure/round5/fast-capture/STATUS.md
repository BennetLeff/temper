# OPTIONAL_BENCH_RESEARCH — stopped by user direction

The user removed FPGA capture from the required cooker architecture. This
folder preserves optional bench-measurement research only. It does not create a
product dependency, release gate, safety credit, controller pin requirement or
independent contact-feedback decoder.

**Current result: functional RTL tests PASS; FPGA 80 MHz timing FAIL.**

- Icarus Verilog12.0:18 real92-byte SPI vectors,39 independent age-provenance
  checks;5/10MHz ideal-pin phase sweeps; valid frequency boundaries and invalid
  periods; local-timer overflow; coherent frozen packets; phase0/1/near-wrap;
  counter/sequence wrap; startup, stale, abort, overlong-read, overlap and
  stopped-clock rejection.
- The unchanged C receiver and bridge planner accept those18 vectors under
  address/undefined-behavior sanitizers.92 single-byte corruption locations,
  invalid fields, deadline, repeated sequence and fault-latch checks pass.
- Custom ORNOT/ANDNOT LUT mapping passes every truth-table input against the
  Yosys iCE40 simulation primitive.
- Yosys0.69 completes iCE40 synthesis and `check -assert` with zero reported
  structural problems. Five register-array replacement warnings and one limited
  tri-state-support warning are retained in the log.
- nextpnr-ice40 maps the selected CT256 pins and fits3747/7680 logic cells(48%).
  The final routed estimate is **79.63MHz, FAIL against80.00MHz**. No timing
  exception, relaxed target or passing declaration was applied. There is no
  working-hardware result, no qualified bitstream and no physical PCB here.

Proposed ESP GPIO14/reset and GPIO38/fault assignments are **withdrawn as product
recommendations**. Existing SPI/pin references are a historical bench interface
candidate only. Any future experiment requires a separate bench-controller
wiring decision. The conditioning CSV is an unrouted circuit proposal, not a
manufacturing package or required change to the cooker.

No further FPGA optimization, synthesis, routing or firmware integration is
being performed. Existing sources, logs and vectors are preserved for review.
`artifact-sha256.txt` hashes the current research sources and review outputs;
it excludes transient executables, synthesis netlists and configuration images.
Historical failed-route logs document intermediate attempts, whose intermediate
RTL versions were not separately retained; only the final source is replayable.
