# Revision 26: compiled AUX clamp insertion

Status: **source-derived review candidate, not a product circuit or hardware
qualification**. Date: 2026-09-22. This revision joins the corrected Revision
19 LT4363-1/FDB33N25 clamp to the Revision 11 Atopile PFC candidate at the
AUX boundary. It deliberately leaves Rev11's control implementation intact.
The result compiles as **150 instances** (the existing 136 plus the 14 clamp
parts); it does not adopt an AUX producer, 5 V buck, protocol receiver, or
manufacturing BOM. No PCB was changed.

## Source binding

The fresh [Atopile source candidate](source-candidate/ato.yaml) copies Rev11's
two `.ato` inputs and adds [the Rev19 clamp module](source-candidate/elec/src/aux_clamp_rev19.ato).
In the [top-level source](source-candidate/elec/src/power_entry_pfc_control_candidate.ato),
the external AUX connector now joins `AUX_RAW`. The clamp's input joins that
raw port; its output joins the former `aux_15v` net, renamed
`AUX_PROTECTED`. **Every original Rev11 AUX consumer remains on that same
protected net**: the PFC controller VCC, relay path, protection circuits and
their supporting loads. The return joins the existing HOT `PFC_BUS_MINUS`
domain. `SERVICE_RESET_N`, FLT and ENOUT remain explicit open boundaries; no
reset switch, observation test point or producer is silently installed.

The clamp module transcribes all 39 pins in the
[corrected Rev19 pin table](../interface-dynamics-19/clamp-expected.tsv),
including R7.1 and D1 anode on `GATE_DRV`, and uses Rev18's exact prototype
C2/C3/C4 capacitor identities. Resistor and C1 MPNs are explicitly
`TBD_REVIEW_ONLY`. Other Rev11 BOM gaps remain. The Atopile BOM carries the
three selected capacitor MPNs, but its netlist's `libsource` metadata can
alias by footprint; use the BOM and per-instance source for identities, not
the netlist's `libsource` field.

## Verification

Atopile 0.2.69 built the candidate offline using the recovered cached tool
route in [the environment record](build-environment.md). Two identical runs
produced byte-identical `default.net` and `default.csv` files; the second
build log is retained in [source-candidate/build.log](source-candidate/build.log).

The standalone [Rust netlist audit](audit_aux.rs) compared the compiled
candidate with the frozen Rev11 netlist and the independent Rev19 TSV. It
checked all 136 old component identities, the 14 new component identities,
the 39 clamp pins and their connectivity partition, unchanged old-pin
partitions except the source-header pin, exact `AUX_RAW` and
`AUX_PROTECTED` membership, HOT return, and the three intended open labels.
It passed. Three controls failed as intended: the former R7/D1 gate branch,
an altered source-header pin, and a renamed HOT return.

The existing [schematic generator](../../../../../scripts/gen_schematics.py)
made a [flat review schematic](native/power_entry_clamped.kicad_sch) using
[candidate-only layout settings](layout.json). Its export oracle verified
**398 pin assignments across 95 connected net groups** against the Atopile
netlist; regeneration and diff checking passed. The [A0 inspection render](native/renders/a0/power_entry_clamped_a0.pdf)
was visually examined to ensure all 150 placed symbols are present. The
generator's five-column grid crowds labels, particularly around the clamp;
this is a connectivity inspection artifact, **not a readable release
schematic**. The standalone [Rev19 clamp sheet](../interface-dynamics-19/clamp.kicad_sch)
remains the readable native circuit reference. The A0 file is a page-size
render derivative; the source-derived schematic itself is unchanged.

[KiCad ERC](native/erc.json) reports 327 warnings in the generated flat
candidate: 150 symbol-library configuration, 149 off-grid endpoints, 16
footprint-library lookups and 12 one-pin labels. The same generator/layout
applied to unchanged Rev11 reports 295 warnings: 136, 135, 15 and 9 in those
respective categories. The 32-warning delta is therefore 14 generated-symbol
warnings, 14 grid warnings, one footprint lookup and the three intended open
clamp ports. These are **not waived**. This generated sheet also types pins
generically, so ERC here cannot qualify electrical pin driving or replace the
Rev19 native fixture's pin-function review.

## Control and product boundary

The [control binding audit](control-binding.md) identifies the exact Rev11
retained RUN latch and final enable instances and recommends routing an
isolated maintained PERMIT into the existing input while a real HOT receiver
emits only a fresh validated ARM pulse. This avoids treating a reconnected
high command level as deliberate intent. It is **not implemented** in this
candidate: the isolation component, receiver, persistent session state,
watchdogs and pulse timing remain open. Rev16's contextual U6/U7 are not
copied into Rev11, avoiding duplicate RUN/enable authorities.

The engineering target remains safe latched shutdown and deliberate re-arm.
This build establishes **connectivity only**. It does not prove source fault
voltage, startup with a buck/load, driver-pin peak, MOSFET SOA, relay release,
gate discharge, residual bank energy, or no-restart behavior after a real AUX
fault or power cycle. The [Rev24 bench protocol](../interface-integration-24/bench-capture.md)
still needs an assembled isolated prototype; none was available for this work.

## Reproduce

From the worktree root, run the retained source and connectivity checks:

```sh
cd zapote/power-entry/passive-reva/protection/interface-integration-26/source-candidate
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/power_entry_pfc_control_candidate.ato:PowerEntryPfcClampedCandidate
cd /Users/bennet/Desktop/temper/worktrees/power-entry
rustc --edition=2021 \
  zapote/power-entry/passive-reva/protection/interface-integration-26/audit_aux.rs \
  -o /tmp/temper-rev26-audit-aux
/tmp/temper-rev26-audit-aux \
  zapote/power-entry/passive-reva/protection/interface-defaults-11/source-candidate/build/default.net \
  zapote/power-entry/passive-reva/protection/interface-integration-26/source-candidate/build/default.net \
  zapote/power-entry/passive-reva/protection/interface-dynamics-19/clamp-expected.tsv
```

From the worktree root, regenerate the flat schematic and verify the result
against the compiled netlist:

```sh
python3 scripts/gen_schematics.py \
  --netlist zapote/power-entry/passive-reva/protection/interface-integration-26/source-candidate/build/default.net \
  --bom-csv zapote/power-entry/passive-reva/protection/interface-integration-26/source-candidate/build/default.csv \
  --layout-config zapote/power-entry/passive-reva/protection/interface-integration-26/layout.json \
  --output-dir zapote/power-entry/passive-reva/protection/interface-integration-26/native
python3 scripts/gen_schematics.py --check \
  --netlist zapote/power-entry/passive-reva/protection/interface-integration-26/source-candidate/build/default.net \
  --bom-csv zapote/power-entry/passive-reva/protection/interface-integration-26/source-candidate/build/default.csv \
  --layout-config zapote/power-entry/passive-reva/protection/interface-integration-26/layout.json \
  --output-dir zapote/power-entry/passive-reva/protection/interface-integration-26/native
```

The retained output hashes and check outcomes are in [receipt.json](receipt.json).
The offline Atopile command depends on the temporary cache documented in
[build-environment.md](build-environment.md).
