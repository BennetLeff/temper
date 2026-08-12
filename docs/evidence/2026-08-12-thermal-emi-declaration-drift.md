<!-- provenance: commit=bf765eb89616d1f3c7cc5f6834658f280c48d27e branch=fix/thermal-emi-config-drift worktree=/home/bennet/Desktop/temper-thermal-emi-drift dirty=true (this doc + the fixes it describes) -->

# Thermal/EMI declaration drift: `U_RTD`/`U_MCU`/`TH_HEATSINK` reconnected, `R_SNUB`/`C_SNUB`/`C_VCC1` genuinely unresolvable, and the board violates three of the reconnected constraints

## Verdict

**Mostly a rename problem, not a deletion problem — and now fixed as far as
renaming can fix it.** Of `thermal_management.yaml`'s 13 constraints, 9 of
their component references now resolve to real board designators (`U_RTD`
&rarr; `U9`, `U_MCU` &rarr; `U27`, `TH_HEATSINK` &rarr; `R60`, `R_GATE_HIGH`
&rarr; `R23`, `C_VCC2` &rarr; `C17`, `C_BUS1`/`C_BUS2` &rarr; `C2`/`C3`,
already known). Three references are **not** a rename: `R_SNUB`/`C_SNUB`
name a real circuit (a relay-contact arc snubber) that is a different
concept from the IGBT switching snubber the file describes, and `C_VCC1`
names a component that doesn't exist in this half-bridge topology (only the
high side floats and needs a bootstrap cap). `Q1`/`Q2`, which nine of the
thirteen constraints depend on, are real board designators but the **wrong
components** (small relay-driver transistors, not the TO-247 IGBTs) — this
was already known and correctly left unresolved by a prior reconciliation
(`packages/temper-placer/configs/temper_constraints.references.yaml`);
this investigation did not change that call.

The gate that should have caught this (`scripts/check_pcl_config_board_correspondence.py`,
"Gate 1") never ran against `thermal_management.yaml` at all — not because
it was skipped, but because it **hard-errored** before checking a single
reference: the gate required a non-empty `zones:` list to run, and
`thermal_management.yaml`, a component-only PCL file, has none. That is
fixed here (zones are now optional), and the gate is now wired into CI
against this file (advisory, same as the existing Gate 1 step for
`temper_induction_cooker.yaml`).

**Measured against the real board using the correct components** (the
IGBTs, `U5`/`U6`, not the wrong `Q1`/`Q2`; see below), **the board violates
three of the reconnectable thermal constraints**: the two IGBTs are not
aligned or edge-mounted together for a shared heatsink (76.35mm apart on
the axis the constraint checks, against a 1.0mm tolerance; one IGBT sits
~21mm from the relevant board edge against a 5mm default tolerance, the
other ~95mm away), the heatsink NTC is nowhere near either IGBT (122–213mm
away against a declared 10mm adjacency), and the high-side gate resistor
sits only 3.13mm from the bootstrap cap it is supposed to be kept &ge;8mm
away from. Six other reconnected constraints (RTD/MCU separation, bus-cap
separation) are comfortably satisfied — mostly because the board is large
(152&times;234mm) and these components ended up far apart anyway, not
because anyone verified the 40mm/25mm/15mm figures against this layout.
These are findings for the hardware owner, not something this PR
"resolves" by loosening the numbers.

## What was asked, and what this document covers

The placement-model expressiveness audit (`docs/brainstorms/2026-08-12-placement-model-expressiveness-gaps.md`,
PR #1068, gap #1) found that `thermal_management.yaml` and
`temper_induction_cooker.yaml` name `U_RTD`/`U_MCU`, which appear zero times
on `pcb/temper.kicad_pcb`, and that the covering CI gate is advisory and
undersells the blast radius. This document:

1. reconstructs what `thermal_management.yaml`'s 13 constraints intended
   (below, "Intent reconstruction"),
2. determines whether each is a rename, a real deletion, or a
   no-longer-valid assumption ("Per-constraint disposition"),
3. reconnects what can be reconnected and shows the result against the
   real board ("What was reconnected, and what the board does with it"),
4. makes the drift durably detectable ("The gate fix").

`temper_induction_cooker.yaml` (the EMI/zone config) is **not** re-fixed
here in the same depth: it already went through a partial reconciliation
(`454f71d92`, 2026-07-11) that disabled its own unresolvable constraints
with `DISABLED (config↔netlist drift)` comments and is already covered by
an existing, working Gate 1 step — its remaining defects (stale
100&times;150mm zone geometry against the real 152&times;234mm board,
`J_AC_IN`/`J_COIL`/`J_DEBUG` absent, `Q1`/`Q2` wrong components) are named
correctly by that gate's own docstring already. This document's new work
is `thermal_management.yaml`, which had no gate coverage of any kind.

## Method

- Grepped `pcb/temper.kicad_pcb`'s `Reference` properties for every
  designator `thermal_management.yaml` names; cross-checked against every
  designator's `Sheetpath` property (the board's own embedded
  atopile-instance-path identity, preserved across renumbering) to find
  the *real* current designator for each *concept* the config names, not
  just a same-string match.
- Read `elec/src/modules.ato`/`main.ato` for the source-of-truth circuit
  each sheetpath belongs to, to judge whether a resolved designator is the
  *right* component, not merely an existing one.
- Cross-checked every finding against
  `packages/temper-placer/configs/temper_constraints.references.yaml`,
  this repo's existing hand-reconciled alias manifest (re-derived
  2026-08-01 by the same sheetpath method, already covering
  `temper_induction_cooker.yaml`'s overlapping names) — where it already
  had an answer (`Q1`, `Q2`, `MAX31865`, `R_GATE_H`/`R_GATE_L`, `C_BOOT`),
  this investigation used it rather than re-deriving; where
  `thermal_management.yaml` used different spellings or new names for the
  same or adjacent concepts, this investigation extended it.
- Extracted real component positions from `pcb/temper.kicad_pcb`'s `(at x
  y)` fields and computed the actual distances the reconnected constraints
  declare, in Python, against the real 169-component board (never
  modified — see `git diff --stat` below for the actual file list).
- Ran `scripts/check_pcl_config_board_correspondence.py` before and after
  every change, saved verbatim below.

## Intent reconstruction

`thermal_management.yaml` was authored 2025-12-19
(`65134cfde`, "add pre-built constraint sets for induction cooker") as one
of four template PCL files, alongside `temper_induction_cooker.yaml`. It
has never been touched since — one commit, ever
(`git log --follow -- packages/temper-placer/configs/constraints/thermal_management.yaml`).

At that commit, the board's `Reference` set (`git show 65134cfde:pcb/temper.kicad_pcb`)
already did not exactly match this file's designators:

| thermal_management.yaml (Dec 2025 &amp; today) | Dec-2025 board had | Today's board has (real target) |
|---|---|---|
| `U_MCU` | `U_MCU` (exact match then) | `U27` |
| `U_RTD` | *(no match — board had `MAX31865` instead)* | `U9` |
| `R_GATE_HIGH`/`R_GATE_LOW` | `R_GATE_H`/`R_GATE_L` (close, not exact) | `R23`/`R27` |
| `C_VCC1`/`C_VCC2` | `C_VCC` (singular, not split) | no clean equivalent (see below) |
| `TH_HEATSINK` | *(no match at all)* | `R60` |
| `R_SNUB`/`C_SNUB` | *(no match at all)* | real components exist, wrong circuit (see below) |
| `Q1`, `Q2`, `C_BUS1`, `C_BUS2` | exact match | real refs, but see the `Q1`/`Q2` caveat below |

This matters for how to read the finding: **`thermal_management.yaml` was
never a precise snapshot of any single board revision.** It reads as a
template written from general TO-247/half-bridge/thermal-derating
know-how and lightly checked against the board of the day, not derived by
tooling from an exported netlist. The board was then regenerated from an
all-`U`-prefix placeholder skeleton to real `R`/`C`/`D`/`L`/`K`/`F`/`RT`/`RV`/`SW`
prefixes (`d5b8809c2`, 2026-07-16, "regenerate board with real designators")
and reconciled again since (93 designator changes, 7 components removed, 6
added — `docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md:39-45`),
compounding the original mismatch. The practical conclusion is the same
either way — the file needs reconnecting against the current board — but
it is worth recording that this was never purely a renumbering-caused
drift; part of it was always approximate.

The qualitative intent itself is real, though, and independently
documented outside this config:

- `docs/hardware/TEMPER_POWERSYNTH_REVIEW.md:141`: `MAX31865 | Driver zone,
  ≥40mm from Q1 | RTD accuracy` — the same 40mm figure, from an
  independent design-review table (a different tool's proposed layout, not
  derived from this PCL file).
- `docs/hardware/SAFETY_INTERLOCK_DESIGN.md:230-233`: `Sensor Location |
  IGBT heatsink | Direct thermal coupling` — the qualitative intent behind
  `TH_HEATSINK`'s adjacency constraint.
- `elec/src/modules.ato:1700-1728` (`RTDSensing` module docstring):
  documents the RTD/MCU domain's isolation intent in detail (unrelated to
  distance, but confirms `rtd_pan.adc` is the RTD interface component the
  config means).

**What is not independently derived anywhere in this repo**: the exact
numeric figures (40mm, 25mm, 15mm, 10mm, 8mm, 5mm). No heat-transfer
calculation, thermal-resistance datasheet lookup, or simulation backing
"<1°C error at 40mm" or "8mm keeps the bootstrap cap below its derating
threshold" was found. The 40mm figure recurs in one independent document
(above), which is evidence it isn't arbitrary, but neither source shows
the underlying math. Per the task's instruction not to fabricate a
requirement: these are recorded as **documented intent with an unverified
numeric derivation**, not as either fabricated or rigorously proven.

## Per-constraint disposition

Using `thermal_management.yaml`'s own line numbers:

| Lines | Constraint | Real board identity | Disposition |
|---|---|---|---|
| 20-25 | `on_side`: `[Q1, Q2]` top/flush | `Q1`→`power_in.q_relay_drv` (SOT-23), `Q2`→`discharge.q_dis_drv` (SOT-23) — **wrong components**; real intent is `hb.power_loop.q_high`/`q_low` = **`U5`/`U6`** (`Package_TO_SOT_THT:TO-247-3_Vertical`, matching "TO-247 IGBT packages" verbatim) | Real, valid intent; **not renameable in the manifest** — `Q1`/`Q2` are live designators for different real parts, so aliasing them to `U5`/`U6` would silently redefine a real name (this repo's manifest deliberately refuses that; see "already tracked" in the audit). Measured against `U5`/`U6` below — **violated**. |
| 27-32 | `aligned`: `[Q1, Q2]` horizontal, tol 1.0mm | same as above (`U5`/`U6`) | Same as above — **violated**, badly. |
| 38-50 | `separated`: `Q1`/`Q2` vs `U_RTD` &ge;40mm | `U_RTD`→`U9` (`rtd_pan.adc`, MAX31865) | `U_RTD`→`U9` **reconnected**. `Q1`/`Q2` unresolved as above; measured against `U5`/`U6` — **satisfied**. |
| 52-64 | `separated`: `Q1`/`Q2` vs `U_MCU` &ge;25mm | `U_MCU`→`U27` (`mcu.mcu`, ESP32-S3) | `U_MCU`→`U27` **reconnected** (already in the manifest). `Q1`/`Q2` unresolved; measured against `U5`/`U6` — **satisfied**. |
| 70-75 | `separated`: `R_SNUB`/`C_SNUB` &ge;5mm | Real R/C snubber pairs exist (`discharge.r_snub1`/`r_snub2` = `R19`/`R20`, `discharge.c_snub1`/`c_snub2` = `C7`/`C8`) but are a **contact-arc snubber across the bus-discharge relay contacts** (`elec/src/modules.ato:1258-1341`), not an IGBT switching snubber. Two equally-unprivileged candidate pairs, wrong circuit either way. | **Not a rename.** Documented `unresolved_components`, not renamed. |
| 77-89 | `separated`: `R_GATE_HIGH`/`C_VCC2` &ge;8mm, `R_GATE_LOW`/`C_VCC1` &ge;8mm | `R_GATE_HIGH`→`R23` (`hb.gate_hs.rg_on`), `C_VCC2`→`C17` (`hb.gate_hs.boot_cap`, the file's own "# Bootstrap cap" comment — and the *only* bootstrap cap in the design). `R_GATE_LOW`→`R27` (`hb.gate_ls.rg_on`) but `C_VCC1` has **no real counterpart**: only the high side floats and needs a bootstrap cap; the low side references ground directly. | `R_GATE_HIGH`/`C_VCC2` **reconnected**; measured — **violated** (3.13mm, not &ge;8mm). `R_GATE_LOW`/`C_VCC1`: `R_GATE_LOW`→`R27` resolves but `C_VCC1` does not — **not a rename**, the pairing's premise (symmetric high/low bootstrap caps) doesn't hold in this topology. |
| 95-107 | `separated`: `C_BUS1`/`C_BUS2` vs `Q1`/`Q2` &ge;15mm | `C_BUS1`→`C2`, `C_BUS2`→`C3` (already in the manifest) | Bus-cap side **reconnected**. `Q1`/`Q2` unresolved; measured against `U5`/`U6` — **satisfied**. |
| 113-118 | `adjacent`: `Q1` vs `TH_HEATSINK` &le;10mm | `TH_HEATSINK`→`R60` (`safety.thermal.ntc`, THM-01, "lug-mount on heatsink" per `elec/src/modules.ato:2408-2415`) | `TH_HEATSINK`→`R60` **reconnected**. `Q1` unresolved; measured against both `U5` and `U6` (whichever is closer) — **violated**. |
| 120-124 | `on_side`: `[TH_HEATSINK]` top/flush | `TH_HEATSINK`→`R60` | **Reconnected**; resolves cleanly (this one doesn't depend on `Q1`/`Q2`). |

## What was reconnected, and what the board does with it

### Designator reconnections landed

`packages/temper-placer/configs/temper_constraints.references.yaml`
extended with `thermal_management.yaml`'s own spelling of already-verified
targets, plus one new target:

```yaml
component_aliases:
  U_RTD: U9        # rtd_pan.adc
  TH_HEATSINK: R60 # safety.thermal.ntc (THM-01)
  R_GATE_HIGH: R23 # hb.gate_hs.rg_on
  R_GATE_LOW: R27  # hb.gate_ls.rg_on
  C_VCC2: C17      # hb.gate_hs.boot_cap
```

and three new documented-unresolved entries (`R_SNUB`, `C_SNUB`, `C_VCC1`
— full reasoning in the file, summarized in the table above).
`temper_constraints.references.yaml:71-92,117-134`.

### Measured against the real board (`pcb/temper.kicad_pcb`, 152&times;234mm, outline `(20,20)`–`(172,254)`)

Using the *correct* components where `Q1`/`Q2` is a stand-in for the real
IGBTs (`U5`=`hb.power_loop.q_high` at `(23.72, 233.25)`, `U6`=
`hb.power_loop.q_low` at `(100.07, 159.33)`):

| Constraint | Required | Measured | Result |
|---|---|---|---|
| `Q1`/`Q2` (→`U5`/`U6`) `separated` from `U_RTD` (`U9` at `(95.4, 249.94)`) &ge;40mm | 40mm | `U5`: 73.6mm, `U6`: 90.7mm | **satisfied** |
| `Q1`/`Q2` (→`U5`/`U6`) `separated` from `U_MCU` (`U27` at `(34.1, 47.96)`) &ge;25mm | 25mm | `U5`: 185.6mm, `U6`: 129.4mm | **satisfied** |
| `C_BUS1` (`C2` at `(93.48, 64.84)`) vs `Q1`(→`U5`) &ge;15mm | 15mm | 182.3mm | **satisfied** |
| `C_BUS2` (`C3` at `(87.36, 34.94)`) vs `Q2`(→`U6`) &ge;15mm | 15mm | 125.0mm | **satisfied** |
| `R_GATE_HIGH` (`R23` at `(46.14, 115.35)`) vs `C_VCC2` (`C17` at `(46.12, 118.48)`) &ge;8mm | 8mm | **3.13mm** | **VIOLATED** |
| `Q1`(→`U5`) `adjacent` `TH_HEATSINK` (`R60` at `(108.6, 37.6)`) &le;10mm | 10mm | `U5`: 213.3mm, `U6` (closer IGBT): 122.0mm | **VIOLATED** (by both candidates) |
| `[Q1,Q2]`(→`[U5,U6]`) `aligned` horizontal (X-axis&#8202;<sup>&dagger;</sup>, tol 1.0mm) | &le;1.0mm apart in X | `\|23.72 − 100.07\|` = 76.35mm | **VIOLATED** |
| `[Q1,Q2]`(→`[U5,U6]`) `on_side` top/flush (default 5mm from the board's +Y edge, y=254) | &le;5mm from edge | `U5`: ~20.75mm, `U6`: ~94.67mm (center-to-edge; both already exceed 5mm regardless of footprint half-height) | **VIOLATED** (both, `U6` badly) |

&dagger; `axis: horizontal` in this repo's PCL parses to `Axis::X`
(`packages/temper-design-bundle/src/pcl_parse.rs:379`: "`horizontal`/`h`
alias to X"), and the encoder compares `x_center`
(`packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/aligned.py:44-47`)
— i.e. this constraint checks the IGBTs' X-coordinates, not Y, despite the
"horizontal" name reading like a row/Y-match at first glance. Confirmed
against the actual handler code, not inferred from the name.

**Reading the result:** three of six checkable declared thermal margins
are honored — but the honored ones are the coarse separation ones on a
large board, where "the two heat sources ended up decently far apart"
happens almost for free. The three that fail are exactly the ones
requiring *placement coordination* (shared-heatsink alignment, sensor
proximity, gate-resistor-to-cap clearance) — the class of constraint that
needs an active solve to satisfy, not just board size. `U5` and `U6` sit
on opposite regions of the board (bottom-left corner vs. mid-board), not
adjacent for a shared external heatsink at all; per this file's own stated
rationale (lines 25, 32: "shared heatsink mounting... symmetrical thermal
design"), that rationale does not hold for the current layout. This is a
**finding for the hardware/placement owner**, not fixed here — per the
task's rule, a violated reconnected constraint is reported, not loosened.

### `Q1`/`Q2` themselves: correctly left unresolved

`Q1`/`Q2` are live board designators (SOT-23 relay-driver transistors),
just not the ones this config means. The existing manifest already
documents this precisely
(`temper_constraints.references.yaml:102-103`) and this investigation did
not change that call — aliasing `Q1`→`U5` in the manifest would let a
*different, later* config that legitimately means the real board's `Q1`
(the relay driver) silently resolve to the wrong component instead. This
is why the measured table above uses `U5`/`U6` directly rather than
through the alias mechanism — the reconnection for `Q1`/`Q2` is
structural (the config's `Q1`/`Q2` constraints cannot be safely
auto-resolved), not a fixable rename, so the gate correctly continues to
flag every constraint containing `Q1` or `Q2` as broken.

## The gate fix

### Why the existing gate didn't catch this

`scripts/check_pcl_config_board_correspondence.py` ("Gate 1") already does
real reference-resolution and zone-containment checking, and was already
correctly flagging `temper_induction_cooker.yaml`'s drift. But it was
**never invoked against `thermal_management.yaml` at all** —
`.github/workflows/python-tests.yml`'s Gate 1 step ran the script with no
`--config` flag, defaulting to `temper_induction_cooker.yaml` only. Worse,
even a manual `--config thermal_management.yaml` run would not have
worked: `load_pcl_config` (`scripts/check_pcl_config_board_correspondence.py:338-341`,
pre-fix) required a non-empty `zones:` list or raised a hard `GateError`
(exit 5, "gate could not run a trustworthy check") — and
`thermal_management.yaml` is a component-only PCL file with no `zones:`
key at all. Confirmed before any fix:

```
$ uv run python scripts/check_pcl_config_board_correspondence.py \
    --config packages/temper-placer/configs/constraints/thermal_management.yaml
GATE RESULT: ERROR -- not PASSED, not a violation. The gate could not run a trustworthy check.
PCL config <-> board correspondence gate -- 0 constraint(s) and 0 zone(s) checked
1 TOOL ERROR(S)
  TOOL_ERROR packages/temper-placer/configs/constraints/thermal_management.yaml has no non-empty 'zones' list
```

This is why the original audit's framing ("its framing names zone drift
rather than the orphaned declarations") undersold the gap: the gate's
zone-containment property literally cannot see a config with no zones, and
its reference-resolution property, which is the one that would have
caught this, never got a chance to run.

### The fix

1. `scripts/check_pcl_config_board_correspondence.py`: `zones:` is now
   optional. Missing/absent normalizes to an empty list (Property 2
   trivially checks zero zones); a present-but-wrong-typed `zones:` key
   still fails closed as a tool error. `constraints:` is still required
   non-empty (unchanged) — a config with nothing to check either property
   against is still rejected.
2. Regression test updated: `test_config_with_no_zones` (which asserted
   the *old*, wrong behavior — tool error) replaced with
   `test_config_with_no_zones_is_not_vacuous` and
   `test_config_with_no_zones_and_clean_references_passes`
   (`scripts/tests/test_check_pcl_config_board_correspondence.py`).
3. `temper_constraints.references.yaml` extended (above).
4. New CI step, `.github/workflows/python-tests.yml`: "PCL config <-> board
   correspondence gate (Gate 1, thermal_management.yaml)", same
   `continue-on-error: true` advisory shape as the existing Gate 1 step,
   running the same script against `thermal_management.yaml`.
5. New pinned regression test,
   `TestRealRepoIntegration::test_real_repo_thermal_management_config_currently_violates`,
   asserting the exact current state (14 broken references, all with
   documented reasons) so any future change to this state — for better or
   worse — fails loudly instead of silently.

### Shown failing on the real historical defect, before wiring (task requirement)

Before the manifest extension (only the gate's zones-optional fix
applied, so the gate could run at all):

```
PCL config <-> board correspondence gate -- 13 constraint(s) and 0 zone(s) checked
=== PROPERTY 1: BROKEN COMPONENT REFERENCES: 21 ===
  ... U_RTD, R_SNUB, C_SNUB, R_GATE_HIGH, C_VCC2, R_GATE_LOW, C_VCC1, TH_HEATSINK (x2)
      all "not a board reference, not a known alias, and not listed as unresolved"
  ... Q1, Q2 (x9 occurrences each, one per constraint that names them)
FAILED -- 21 broken reference(s), 0 zone(s) outside the board outline
```

**All 13 of 13 constraints in the file were broken** — every single
declared thermal margin in this board's only thermal-intent PCL file was
unenforceable, confirming the audit's claim in full.

After the manifest extension:

```
PCL config <-> board correspondence gate -- 13 constraint(s) and 0 zone(s) checked
=== PROPERTY 1: BROKEN COMPONENT REFERENCES: 14 ===
  ... Q1 (x7), Q2 (x6), R_SNUB, C_SNUB, C_VCC1 -- each now with a documented reason
FAILED -- 14 broken reference(s), 0 zone(s) outside the board outline
```

9 constraints now have every reference resolved (6 fully clean, 3 partly —
where `Q1`/`Q2` is still the blocker but the other operand now resolves).
The remaining 14 broken references are exactly the ones this
investigation determined are not safely renameable (`Q1`/`Q2` wrong
component, `R_SNUB`/`C_SNUB` wrong circuit, `C_VCC1` nonexistent) — none
are "unrecognized" any more. This before/after is captured as a permanent
regression test (`test_real_repo_thermal_management_config_currently_violates`),
not just this document's terminal output.

## What remains open (not fixed here, on purpose)

- **The three violated reconnected constraints** (heatsink alignment/
  edge-mount, heatsink-NTC adjacency, gate-resistor/bootstrap-cap
  clearance) are real findings about the current board, not bugs in this
  PR's scope to fix by moving components or loosening numbers.
- **`Q1`/`Q2` identity** — whether to ever alias them, rename the config's
  own field names (e.g. `Q_HS`/`Q_LS`) to something that can't collide
  with a real board designator, or leave them permanently manual — is a
  design decision for whoever owns this config, flagged, not decided
  here.
- **`R_SNUB`/`C_SNUB`/`C_VCC1`** — genuinely require a hardware-completeness
  decision (does this design need an IGBT-side switching snubber and a
  low-side gate-drive decoupling cap it doesn't currently have, or should
  the constraints be deleted as describing a circuit this design never
  built), not a placement-config fix.
- **The manifest-autodiscovery path bug** (found, not fixed): both call
  sites in `packages/temper-placer/src/temper_placer/cli/__init__.py`
  (lines ~530 and ~701) derive the alias-manifest path as
  `config.with_suffix(".references.yaml")`, which for
  `configs/constraints/temper_induction_cooker.yaml` looks for
  `configs/constraints/temper_induction_cooker.references.yaml` — a file
  that does not exist. The real manifest lives at
  `configs/temper_constraints.references.yaml` (different directory,
  different name). `manifest_path.exists()` is therefore `False` on every
  real CLI invocation, so this manifest — despite being real, hand-
  reconciled, and consumed by both the gate and the encoder's alias-
  resolution machinery — is **never actually loaded during a live CLI
  solve** unless a caller passes the correct path some other way. This
  deepens gap #1's core finding (no live check reaches the real solve) but
  is a distinct bug in a different subsystem (CLI argument wiring, not
  the PCL config or the correspondence gate) and was not fixed here to
  keep this change reviewable; flagged for separate follow-up.

## Files changed

```
$ git diff --stat bf765eb89   # this branch's fork point (origin/main has advanced
                               # since, with unrelated merges -- diffing against
                               # today's origin/main tip would show that noise too)
.github/workflows/python-tests.yml                                        | 28 +++++++++
.../configs/temper_constraints.references.yaml                            | 37 ++++++++++++
.../tests/io/test_reference_aliases.py                                    | 10 ++++
.../io/test_reference_aliases_rust_differential.py                       |  2 +-
scripts/check_pcl_config_board_correspondence.py                          | 20 ++++++-
.../test_check_pcl_config_board_correspondence.py                         | 69 +++++++++++++++++++++-
6 files changed, 160 insertions(+), 6 deletions(-)
```

`pcb/temper.kicad_pcb` was not modified (checked: not in the diff above).
