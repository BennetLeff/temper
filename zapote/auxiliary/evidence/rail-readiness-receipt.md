# Auxiliary R1 rail and load readiness receipt

Date: 2026-09-23. Source revision: isolated `codex/zapote-aux-u3-readiness` base `afb8b9e31`; seven Rev38 source-file hashes are pinned in [rail-readiness-sources.tsv](rail-readiness-sources.tsv). The active Rev38 worktree was neither changed nor used as an accepted source. Runtime: host `rustc` standalone edition 2021; `shasum -a 256` checks actual committed source bytes. No native source, supply article, assembled PCB or powered fixture is claimed.

## Result

The [inventory](rail-readiness-inventory.tsv) contains **seven proposed rail sources and 22 named loads**, retaining HOT `AUX15_SOURCE`, protected AUX, HOT logic5, SELV 15/3V3, isolated low-side bias, and fan rail as distinct outputs/returns. The source-input graph requires HOT and SELV source inputs to exist before PFC RUN; protected AUX and HOT logic5 must remain downstream of a dedicated branch and cutoff. The six direct AUX passive branches are mandatory IDs, not inferred from a subtotal. A consumer with no load waveform is `UNKNOWN`; source, protection and insulation selections remain unknown or candidate. The gate result is **INDETERMINATE**, with 151 missing envelope or selection fields. It grants no source-current or voltage adequacy conclusion, no selected source, and no standalone U3 construction acceptance.

The restart state machine in the gate is a *requirement model*. It clears ARM and permit on rail loss, brownout, source hiccup or cutoff; rail recovery alone cannot arm or run. It is not a measurement of Rev38's retained latch, ENA pin, switch current, or both-stage stop behavior. The HOT0↔SELV and `HV_RETURN` boundaries are inventory constraints, not insulation or return-path proof. A 50 °C H1 static voltage screen and H2 feedback-only margin from the U2 comparison cannot override missing total load/startup/fault envelopes.

## Replay

From repository root:

```sh
rustfmt --check zapote/auxiliary/evidence/rail_readiness.rs
rustc --edition=2021 --test zapote/auxiliary/evidence/rail_readiness.rs -o /tmp/zapote-aux-rail-readiness-tests
/tmp/zapote-aux-rail-readiness-tests
rustc --edition=2021 zapote/auxiliary/evidence/rail_readiness.rs -o /tmp/zapote-aux-rail-readiness
/tmp/zapote-aux-rail-readiness .
```

On this snapshot, **11 tests passed**: source lock mutation; domain/return crossing; direct AUX branch omission; PFC RUN startup dependency; cutoff bypass; fan return mismatch; zero substituted for unknown pulse demand; incomplete passive subtotal; rail recovery without ARM; and brownout clearing a live permit. The CLI found no structural rejection and reported `INDETERMINATE` with 151 unknown fields. Any stale pinned source bytes, missing source lock, malformed table, graph violation or unregistered row produces `REJECTED` (exit 2). These negative controls verify the declared inventory/gate, not a generated native netlist.

## Next construction gate

Before selecting H1/H2 or any SELV/isolated-bias/fan producer: obtain complete worst-case steady, concurrent startup, pulse, dropout and fault waveforms for all loads at one frozen Rev38 revision; exact branch fusing/inrush/conductor and module AC pins; cutoff path drop/output peak with chosen FETs/shunt; local thermal envelope; fan variant and startup/stall data; and reviewed HOT/SELV/HV_RETURN insulation and grounding. Then construct selected Atopile source and validate generated netlist/native board and powered default-off/restart behavior under the separate U3/physical acceptance process. The mains-disconnected P1 rail-order fixture remains a lab-only candidate.
