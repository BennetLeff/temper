<!-- provenance: commit=9b666d3be3eaf09e398a52f546da8ec5917c41dd dirty=true (branch fix/reconcile-creepage-requirement; base = PR #442's baseRefOid; doc states no self-measured commit in prose) -->

# Creepage requirement reconciliation: DC_BUS<->LV_CONTROL (and siblings) were checked against the wrong Table 16 row

## Verdict, up front

The validator was **too lenient**, not the spec. `IEC60335_REQUIREMENTS` in
`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`
checked every REINFORCED HV<->SELV/ISOLATED boundary's creepage against IEC
60335-1 Table 16's **300V** row (8.0mm) when every one of those boundaries'
own working voltage — DC_BUS (400V peak/transient), MAINS (340V
peak/transient), Gate Drive Isolated (355V peak-to-earth) — exceeds 300V.
IEC 60664-1/60335-1 tables are not interpolated: a working voltage between
two tabulated rows takes the *next row up*. All three round up to the same
**400V** row (10.0mm reinforced, not 8.0mm). The corresponding BASIC-tier
entries had the same defect (4.0mm instead of 5.0mm). This was not isolated
to DC_BUS<->LV_CONTROL — it affected every REINFORCED and BASIC row in the
matrix that involves a >300V domain (all of them except the LV_CONTROL
functional row, which is correctly unaffected at low voltage).

Fixed by raising `min_creepage_mm`/`design_value_mm` in every affected row.
`min_clearance_mm` was **not** changed: it was already conservative relative
to the corrected voltage row (see "Clearance was not touched" below). REQ-SAFE-01
violations on the real board go from **76 to 98** as a direct, intended
consequence — the corrected validator finds more of what was already there.

## 1. What is the correct working voltage for DC_BUS<->LV_CONTROL?

Three numbers matter here, all traceable to `elec/src/main.ato` and one
already-completed investigation (`docs/hardware/SELV_ISOLATION_REDESIGN.md`):

- **Nominal, full-bus differential: 340V.** `main.ato:12` ("DC Bus (340V)"),
  `main.ato:65-66`:
  ```
  v_bus_nominal: voltage = 340V
  assert v_bus_nominal within 280V to 380V  # Doubler output range
  ```
  This is the doubler's rated output — `dc_bus_plus - dc_bus_minus`.
- **Worst-case (non-fault) bus: up to 380V**, the top of that same asserted
  tolerance band (ripple + line-high combined; `main.ato:68-69` adds up to
  20V ripple on top).
- **Absolute max / transient: 400V.** `main.ato:50` (`v_bus_abs_max = 400V`),
  `main.ato:601` (`assert v_bus_max <= 400V`), and `constraints.ato:7,34`
  (`v_max = 400V`, the component voltage-rating ceiling used throughout the
  design). `v_ovp_trip = 390V` (`main.ato:636`) sits just under this ceiling
  by design (`assert v_ovp_trip < v_cap_max`, `assert v_ovp_trip > v_bus_max`).

**The half-bus question, considered and rejected as the basis for this
check.** `SELV_ISOLATION_REDESIGN.md` §5 established that `dc_bus_plus`
alone (the node most naively read as "the DC bus") is +170V nominal, not
340V — `dc_bus_plus - dc_bus_minus` is what spans the full 340V. It would be
a mistake to read that as "so the working voltage for creepage is 170V,
not 340V+": the validator's `VoltageDomain.DC_BUS` is one bucket covering
*every* net `elec/domain_manifest.yaml` declares HV that isn't literally
`ac_l`/`ac_n` (confirmed:
`packages/temper-placer/tests/requirements/safety/_real_board_fixture.py:44-60`)
— `dc_bus_plus`, `dc_bus_minus`/`DC_BUS_RTN`, `SW_NODE`, the CMC winding
taps (`w1_1`/`w1_2`, at raw AC potential), `+15V_LS`, `GATE_HS`/`GATE_LS`,
etc. A single clearance/creepage figure has to protect against whichever
member of that bucket sits closest to LV_CONTROL copper, not just the
lowest-potential one. This is exactly what
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §2.1's own domain table already
encodes for Domain B ("DC Bus"): **Working Voltage 170-340V DC, Peak/Transient
400V, Hazardous** — a *range*, because the domain contains nodes across that
whole span, with 400V as the ceiling any of them can present. That
domain-level ceiling, not the single lowest node in the domain, is the
correct basis for a domain-wide creepage figure.

**Conclusion: whichever of 340V (nominal), 380V (worst-case non-fault), or
400V (abs max/transient) is used, all four exceed 300V**, and per the
no-interpolation rule below, all four land on the same table row. The
specific choice among them is immaterial to the outcome, which is why this
conclusion is robust rather than sensitive to picking exactly the right one
of the three.

MAINS's own working voltage is 340V peak/transient (spec §2.1, Domain A),
and Gate Drive Isolated's is 355V peak-to-earth (spec §2.1, Domain C) — both
also >300V, both also round up to the 400V row (see §3).

## 2. What creepage does that require?

Standards basis this project already uses: IEC 60335-1 Table 16, Pollution
Degree 2, Material Group IIIb, as transcribed in
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.1:

| Working Voltage (V) | Basic (mm) | Reinforced (mm) | Design Value (mm) |
|---|---|---|---|
| 300 | 4.0 | 8.0 | 10.0 |
| 400 | 5.0 | 10.0 | **12.0** |

**Interpolation is not permitted.** IEC 60664-1/60335-1 clearance and
creepage tables give discrete rows; a working voltage that falls between
two rows takes the *next row up*, never a value in between (this is
standard insulation-coordination practice, not a project-specific
convention — and this project already relies on it elsewhere: see §3). 340V,
355V, and 400V all exceed 300V, so all three read off the **400V** row:
REINFORCED creepage = **10.0mm**, not 8.0mm.

## 3. Which figure was authoritative, and was this isolated to DC_BUS<->LV_CONTROL?

**The validator's 8.0mm/10.0mm-design pair was wrong; the spec's own Table
16 (§5.1) is right and was simply misread.** Confirmed the spec itself
already knows the correct row for the *DC Bus* case: §5.2 ("Design
Creepage") already listed "DC Bus to SELV | Reinforced | 400V pk | 10.0mm |
12.0mm" — the 400V row — even before this change. What was wrong was (a)
the validator's constant, which used 8.0/10.0 instead of matching that
already-correct spec row, and (b) the spec's *own* §5.2 "AC Mains to SELV"
row, which — despite AC Mains being 340V pk, the same >300V case as DC
Bus — was pinned to the 300V row (8.0mm/10.0mm) instead. That AC Mains row
was the odd one out even within the spec document itself: §8.2's
verification checklist and §9.1's KiCad DRC rule (`HV_AC_to_SELV_creepage`)
both already independently used 10.0mm for AC Mains to SELV. Fixed as part
of this change (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.2).

**Checked every other row in the validator's matrix — this affected three
of four HV-referenced rows, not just one:**

| Row | Old creepage (basic/reinforced) | Working voltage basis | Correct row | New creepage |
|---|---|---|---|---|
| MAINS<->LV_CONTROL | 4.0 / 8.0 | 340V pk (spec §2.1, Domain A) | 400V | **5.0 / 10.0** |
| DC_BUS<->LV_CONTROL | 4.0 / 8.0 | 400V pk (spec §2.1, Domain B; §1 above) | 400V | **5.0 / 10.0** |
| MAINS<->ISOLATED | — / 8.0 | 355V peak-to-earth (spec §2.1, Domain C) | 400V | **— / 10.0** |
| LV_CONTROL<->LV_CONTROL (functional) | 1.0 | 3.3-15V (spec §2.1, Domain D) | 50V (table floor) | unchanged, correctly low-voltage |

All three HV rows shared the identical defect (pinned to the 300V row
despite each boundary's own declared working voltage exceeding 300V). The
functional LV_CONTROL<->LV_CONTROL row was not affected — its working
voltage genuinely is low (SELV, 3.3-15V) and 1.0mm/2.0mm predates and is
below Table 16's own 50V floor, which is out of scope for this correction.

**Clearance was not touched.** IEC 60335-1's clearance table (spec §4.1)
also rounds 340V/400V up to its own 400V row: Basic 2.5mm, Reinforced
5.0mm. The validator's clearance figures (3.0mm basic, 6.0mm reinforced,
every affected row) already meet or exceed those corrected minima —
clearance was already conservative, only creepage was under-specified. No
change was needed there, and none was made (`min_clearance_mm` is unchanged
in every row). Spec §4.2's own "Design Value" column (8.0mm for all three
HV rows) does not cleanly match Table 4.1's own Design column at either the
300V (5.0mm) or 400V (6.0mm) row — an existing internal inconsistency in
that document, but not a safety problem (it only ever asks for *more*
margin than the table requires) and left alone here as out of scope for a
creepage-specific correction.

**Checked, not affected — different standard, correctly applied
elsewhere:**
- `scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM = 8.0` is a
  separate, independently-derived figure (explicitly flagged in its own
  module docstring as "UNVERIFIED-at-primary," reconstructed from secondary
  SMPS-layout-guide sources, not from this project's own Table 16
  transcription). It is a **physical keepout corridor width**, not a
  per-pair distance check, and is listed in this task's own hard
  constraints as a pre-existing, out-of-scope failure on `main` (no keepout
  zone exists on the board at all today, so this gate fails regardless of
  the constant's value). Note for whoever picks this up next: now that the
  REINFORCED DC_BUS<->LV_CONTROL creepage requirement here is 10.0mm, an
  8.0mm keepout corridor would no longer be wide enough to structurally
  guarantee that requirement either — worth revisiting together with the
  keepout gate itself, but not fixed in this pass (out of scope, and the
  gate is already failing for an unrelated, structural reason).
- `packages/temper_placer/src/temper_placer/router_v6/creepage_check.py`'s
  `_calculate_required_creepage` uses **IPC-2221** (a different standard,
  for generic PCB conductor spacing, not IEC 60335-1's household-appliance
  table), with its own, differently-bracketed voltage table. Its 301-600V
  bracket already correctly returns 8.0mm per *that* standard's own
  breakpoints — not an instance of this defect, just a different table
  applied to a different check.
- `packages/temper-placer/configs/netclass_rules.yaml`'s 6.0mm
  ACMains/HighVoltage figure is explicitly documented (in
  `check_isolation_keepout.py`'s own docstring) as a *different* quantity —
  BASIC/functional clearance between two same-domain HV nets, not
  reinforced HV<->SELV creepage — and is untouched here.
- `packages/temper-drc-rs/src/types/hv_net.rs`'s `8.0` values are Rust unit
  test parameters for a structural net-isolation classifier (HV nets not
  co-mingled with signal nets), not a distance figure sourced from this
  matrix.

## 4. Fix applied

`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`,
`IEC60335_REQUIREMENTS`:

| Row | Field | Old | New |
|---|---|---|---|
| MAINS, LV_CONTROL, BASIC | min_creepage_mm / design_value_mm | 4.0 / 6.0 | 5.0 / 7.0 |
| MAINS, LV_CONTROL, REINFORCED | min_creepage_mm / design_value_mm | 8.0 / 10.0 | 10.0 / 12.0 |
| DC_BUS, LV_CONTROL, BASIC | min_creepage_mm / design_value_mm | 4.0 / 6.0 | 5.0 / 7.0 |
| DC_BUS, LV_CONTROL, REINFORCED | min_creepage_mm / design_value_mm | 8.0 / 10.0 | 10.0 / 12.0 |
| MAINS, ISOLATED, REINFORCED | min_creepage_mm / design_value_mm | 8.0 / 10.0 | 10.0 / 12.0 |

`min_clearance_mm` unchanged everywhere (already conservative, §3).
`design_value_mm` is documentary only (`min_creepage_mm + 2.0mm`, the
project's own existing convention across every affected row) — it is not
read by `verify_iec60335_compliance`, only `test_requirement_matrix_values`
asserts it directly.

`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.1 gained a note stating the
no-interpolation rule explicitly, and §5.2's "AC Mains to SELV" row was
corrected from 8.0mm/10.0mm to 10.0mm/12.0mm to match the rest of the same
document (§8.2, §9.1) and DC Bus's already-correct row directly below it.

### Downstream tests updated to match the corrected requirement

These encode literal expected values from the matrix (or copper geometry
measured against it) and needed updating to reflect the corrected, not the
old, numbers — none of them soften anything; all move in the stricter
direction:

- `packages/temper-placer/tests/requirements/safety/test_clearance.py`,
  `TestRequirementMatrix.test_requirement_matrix_values` — expected
  creepage/design literals per row.
- `packages/temper-placer/tests/requirements/safety/test_clearance_copper.py`
  — K1 (an isolator, exact copper gap 8.000mm, unchanged) and T1 (9.100mm,
  unchanged) were previously asserted to *pass* REINFORCED creepage under
  the old 8.0mm requirement (K1 exactly, T1 with 1.1mm margin). Under the
  corrected 10.0mm requirement both are genuine violations (K1 short by
  exactly 2.000mm, T1 by 0.900mm) — this is real information about the
  board, not a test artifact, so the tests (renamed) now assert the
  violation instead of its absence, and the "five known intra-footprint
  blockers" set grew to seven (`{C6, K1, K2, K3, T1, U3, U7}`).
- `packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py` —
  two tests asserted the CP-SAT domain-clearance constraint generator's
  emitted margin was exactly 8.0mm (the old MAINS/DC_BUS<->LV_CONTROL
  reinforced max); now 10.0mm. The BMC-exhaustive soundness sweep's margin
  list was widened to include 5.0mm and 10.0mm so it still covers the
  matrix's actual (now-corrected) values.

`packages/temper-placer/tests/requirements/safety/test_clearance.py`
itself — the REQ-SAFE-01 real-board integration test — was **not**
modified to pass. It was already failing before this change and remains
failing after, as required: violations are real and increased, not
decreased.

## 5. Violation count: before and after

Reproduced on this branch, `elec/build/default.net` built fresh (`make
netlist`, exit 0), then:

```
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -q
```

| | Before (8.0mm reinforced / 4.0mm basic creepage) | After (10.0mm / 5.0mm) |
|---|---|---|
| REQ-SAFE-01 violations | 76 | **98** |
| Violating pairs | 33 | 52 |
| Intra-footprint records (unfixable by moving anything) | 11 | 13 |
| Domain classification coverage | 158/168 components (94.0%) | unchanged |

The delta (+22 violations, +19 pairs, +2 intra) is every pair/record whose
measured creepage fell in the 8.0-10.0mm or 4.0-5.0mm band — genuinely
short of the corrected requirement, previously reported as passing only
because the requirement checked against was itself wrong. Nothing about
the board changed; `pcb/temper.kicad_pcb` was not touched (read-only, per
this task's hard constraints).

A second, independent finding also newly surfaces because the "largest IEC
margin" used by this same test's fail-closed unclassified-component-proximity
check grew from 8.0mm to 10.0mm along with the matrix: 4 previously-outside-margin
unclassified components (R42, R34, R40, R45 — all `rtd_pan` resistors) now
sit within the enlarged margin of a declared-HV component (R5). This is
reported by the existing test (unchanged logic, just a larger threshold) as
a second, separate REQ-SAFE-01 finding, and is not further investigated or
resolved here — it is a domain-classification-coverage question, the same
class of gap `docs/evidence/2026-07-27-domain-classification-coverage.md`
already tracks, not a creepage-requirement question.

## 6. Reproducing this document

```
git fetch origin && git checkout -b <branch> origin/main
uv sync --all-packages
make netlist   # elec/build/ is gitignored; the test skips without this
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -q
```

Full suite touched by this change, all green except the expected real-board
failure:

```
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/ \
  packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py \
  packages/temper-placer/tests/requirements/validators/ -q
# 1 failed (test_temper_board_clearance_compliance, expected), 101 passed
```

## 7. Constraints honoured

- No figure invented: every number traces to `elec/src/main.ato`'s own
  asserted voltages, `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`'s own
  Table 16 transcription, or the no-interpolation derivation shown in full
  above.
- The threshold moved **stricter**, never looser: creepage minimums only
  increased (4.0->5.0, 8.0->10.0); clearance was left alone because it was
  already conservative, not loosened.
- `test_clearance.py`'s real-board integration test was not modified to
  pass, and does not pass — it fails with more violations than before.
- `pcb/**` was not touched.
- No skip/xfail/deletion/assertion-weakening/`continue-on-error`/`git
  stash` used anywhere in this change.
