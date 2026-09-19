# Protection review correction evidence

Date: 2026-09-19. Base: `3eecc61de`; branch `codex/power-entry-pkgs-1-4`.
Agent runtime: Codex GPT-6 family / OpenAI. No physical instrumentation.
Result: **logic corrections and construction checks pass; protection INDETERMINATE**.

The offered worktree already contained the Infineon bridge/AUX integration in
source and poses. This review preserves that work and corrects the latch,
removes TVR14561, and withdraws unsupported startup/delay/clamp conclusions.
It does not route the new native board or modify the older maintained candidate.

## Results and scope

- `source-review-07/build-receipt.json`: Atopile 0.2.69 compiled/exported.
- `native-review-03`: fresh Rust/Python bridge emission, 119 components,
  unrouted board. Local project `{}` is required for project library resolution.
- `erc-with-project.json`: final native KiCad ERC, zero violations.
  `erc.json`/`erc-final.json` preserve intermediate drawing/library failures.
- `native-final.net.xml`: final native export. `native-nets.json` is its lossless
  connected-pin projection (each node is `[ref,pin]`). Normal Rust tests compare
  it with the compiled bridge and verify the protection pin connections.
- `rust-tests.txt`: initial 13 focused tests pass. `regression-tests.txt`:
  13 focused plus 10 existing campaign-ledger tests pass.
- `startup-corrected.csv`: nominal selected-capacitor energy 135.2648268 mJ;
  no startup time, peak or single-event guarantee. Old output is historical.
- `timed-sweep.csv`: byte-identical to the previous plant sweep. This does not
  model/qualify the newly selected complete protection circuit.
- `claims-check.txt`: no implemented violations in the three scoped claims;
  zero protection claims/promotions. This is not a general soundness verdict.
- `schematic.pdf`: visually reviewed final drawing. Numerical pin labels are
  intentional; obsolete reference-specific TEA names were removed.

`manifest.json` records exact reviewed bytes. Historical ledgers and receipts
are not rewritten or promoted. No KiCad DRC/common-board PASS is asserted for
this unrouted variant. ERC cannot establish ratings, timings or protection.

## Reproduction (repository root)

```sh
AR=zapote/power-entry/active-rectifier
cargo test --locked --offline --manifest-path zapote/Cargo.toml -p zapote-harness --test power_entry_protection_review --test campaign_ledgers
rustc --edition=2021 -O "$AR/experiments/f2-open/f2_open_timed.rs" -o /tmp/f2-review-timed
/tmp/f2-review-timed burst
/tmp/f2-review-timed > /tmp/f2-review-sweep.csv
cmp /tmp/f2-review-sweep.csv "$AR/experiments/f2-open/raw/timed-sweep.csv"
rustc --edition=2021 -O "$AR/experiments/f2-open/protection_logic.rs" -o /tmp/f2-review-logic
/tmp/f2-review-logic
cargo build --locked --offline --manifest-path zapote/Cargo.toml -p zapote-harness --bin zapote-claims
# Use zapote-claims from the configured Cargo target directory:
zapote-claims "$AR/evidence/protection-review-04/claims.json"
KICAD=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
"$KICAD" sch erc --severity-all --format json --output /tmp/f2-review-erc.json "$AR/native-review-03/section.kicad_sch"
"$KICAD" sch export netlist --format kicadxml --output /tmp/f2-review.net.xml "$AR/native-review-03/section.kicad_sch"
```

Source rebuild: `python3 "$AR/tools/build_source.py" /tmp/f2-review-source`.
Native rebuild: `python3 "$AR/tools/build_native.py" /tmp/f2-review-source /tmp/f2-review-native`,
then `python3 "$AR/tools/draw_schematic.py" --repo . --source /tmp/f2-review-source --output /tmp/f2-review-native --receipt /tmp/f2-review-drawing.json`.
Create `/tmp/f2-review-native/section.kicad_pro` containing `{}` before ERC.
The native builder requires a freshly built temper-design-bundle Python extension
and kiutils. This run rebuilt the Python feature via maturin in an isolated
`/tmp/f2-review-venv`, using the prescribed shared Cargo cache. The initial
`source-review-06` (cache permission) and `native-review-02` (missing kiutils)
failed before successful output and remain local failed-attempt directories.

## Source evidence

`sources/cd4013b.pdf` and `sources/cd40106b.pdf` are TI device datasheets;
`sources/thinking-tvr.pdf` is the THINKING TVR table used to reject TVR14561.
They establish the referenced logic/pin identities and published MOV figures,
not full-circuit performance. The selected bootstrap rail, device tolerances,
startup, complete gate-off budget, clamp duty and physical qualification remain
open as stated in `../../decisions/f2-open/PROTECTION-SELECTION.md`.

Tools: KiCad 10.0.4; rustc/cargo 1.92.0; Atopile 0.2.69.
Import-linter: 5 contracts kept, zero broken. `make regen` and
`make regen-check` passed; regeneration refreshed the existing plan count.
Remaining QR-DET/CLAMP/CAP work: https://github.com/BennetLeff/temper/issues/1609.
