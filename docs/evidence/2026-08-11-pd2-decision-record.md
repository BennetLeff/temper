<!-- provenance: commit=4a327d920de8daf4cf55ef875fbbec9cacda00e9 dirty=false -->

# PD2 decision record: PD2/8.0mm is the target; the sealed compartment is a hard, unmet prerequisite

**Date:** 2026-08-11
**Decided by:** the project owner (Bennet), closing the question
`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` asked on 2026-08-02.
This document is **not** a re-litigation of that decision pack's analysis —
its physical-facts and standard-condition findings (Sections 1-2 of that
doc) are correct and remain correct. This document records the decision the
owner made against those findings, defines concrete, checkable evidence for
the one thing the decision does not yet make true, and lands a gate that
enforces the gap cannot go unflagged.

---

## 1. The decision

- **D1. PD2/8.0mm governs; the owner will add the sealed compartment**
  (session-settled: user-directed, 2026-08-11 — chosen over retargeting to
  PD3/12.6mm, which a same-day spike measured **not established feasible**:
  `docs/plans/2026-08-11-002-feat-placer-wirelength-and-hv-separation-plan.md`
  found 196 violating pad-pairs at 12.6mm, an isolator population
  structurally invariant to board size, and at least one isolator UNSAT
  even after part substitution). This confirms and executes, rather than
  reopens, the 2026-07-30 owner decision
  (`docs/evidence/2026-07-30-pd2-enclosure-decision.md`) that already
  selected PD2 as the production target conditional on the compartment —
  today's decision is that the condition will be met, not a change of
  target.

The board's enforced reinforced-creepage target remains **8.0mm**
(`scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_ENFORCED_MM =
HV_CREEPAGE_PD2_MM`, unchanged by this document — see "What this document
does NOT do" below). **12.6mm remains declared** as the PD3 fallback in the
same file, unchanged.

## 2. The critical nuance this decision does not erase

**The decision does not make PD2 valid today.** Per
`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`'s own findings, at
the commit this document is provenanced against:

- The design is **forced-air-vented, not sealed**. The board outline is a
  plain rectangle (`pcb/temper.kicad_pcb`'s only `Edge.Cuts` polygon) with
  zero vent/compartment provisions.
- The fan is off-board on leadwires; the chassis routes bottom-intake air
  through an 80mm fan → IGBT-heatsink duct → rear exhaust, **across the
  same cavity the PCB occupies** (`docs/CHASSIS_AIRFLOW_DESIGN.md`).
- The "sealed gasketed PCB compartment" exists **only as a prescriptive
  release requirement** in `docs/ENVIRONMENTAL_SPEC.md` §3.1 and
  `docs/ASSEMBLY_GUIDE.md` Phase 4.2 — no cover, gasket, partition, or
  inspection geometry is committed anywhere in this repository.
- On the standard's own condition (IEC 60664-1 pollution-degree criteria;
  the board also cites IEC 60335-1, and its own particular standard IEC
  60335-2-6 cl. 29.2 Addition makes PD3 the *default* for this appliance
  class), **PD3/12.6mm governs the as-built construction today.**

So PD2 is the *chosen target*, not a claim that today's board already
qualifies, and the sealed compartment is a **hard prerequisite that does
not yet exist**. Until it does, every creepage figure measured against
8.0mm is provisional — a number that is true of the *enforced constant*,
not yet true of the *physical product*.

**Interim position, stated plainly for anyone reading a creepage number in
this repo:** until the compartment lands, **the board is PD3-governed as
built**, and any figure measured or reported against the 8.0mm bar carries
an unearned credit. Ask two questions of any creepage number you read:
(1) which bar was it measured against, and (2) is that bar earned yet —
i.e. does `scripts/check_pd2_compartment_evidence.py` (Section 4 below)
pass. As of this writing, it does not.

## 3. What this document does NOT do

- It does **not** change any creepage value, DRU rule, keepout distance, or
  `power_pcb_dataset/drc_ceiling.json` entry. The bar stays 8.0mm — that is
  the decision, not a re-measurement.
- It does **not** mark the compartment as built. It is not built.
- It does **not** soften the PD3-governs-today finding — that finding is
  exactly why the gate in Section 4 exists.
- It does **not** re-run or re-verify the K3/RT314012, thermal-marginality,
  or other measurements `2026-08-01-pd2-enclosure-legitimacy.md` and its
  cited evidence already established; those stand as measured.

## 4. What evidence would demonstrate the compartment exists

This is the substantive part. `docs/ENVIRONMENTAL_SPEC.md` §3.1 already
*lists* what a released assembly must have — a gasketed PCB compartment,
no duct path into it, no exposed insulation in the pollution path,
assembly/inspection criteria, documented review. The problem this section
solves is that list has stayed **prose intent** for over a week (first
stated 2026-07-30) with nothing verifying it. Below is a structured
artifact a script can actually evaluate, not sentences a human has to trust.

### 4.1 The artifact: `docs/specs/pd2_compartment_evidence.yaml`

A single, machine-checkable YAML file, absent today, is the compartment's
evidence record. Required fields, each independently checkable and each
mapped to one of the physical items the 2026-08-01 decision pack's Option
(a) scope named as currently missing (§4 items 1-3 of that doc):

| Field | What it must contain | Why it is checkable, not prose |
|---|---|---|
| `pd2_bar_mm` | Must equal the PD2 bar this gate reads *live* from `generate_kicad_dru.py`'s `HV_CREEPAGE_PD2_MM` (8.0) | Ties the evidence to the actual enforced constant, not a copied number that can drift |
| `cover.part_ref`, `cover.material`, `cover.length_mm`/`width_mm`/`thickness_mm` (> 0) | A real BOM part reference and non-zero dimensions | A cover that exists has a part number and a size; a sentence promising one does not |
| `gasket.part_ref`, `gasket.perimeter_length_mm` (> 0), `gasket.compression_mm` (> 0) | A real gasket part and its sealed perimeter/compression spec | Same reasoning — a gasket that seals something has a perimeter length and a compression spec |
| `partition.keepout_zone_name` | The name of a zone that must **actually exist** in `pcb/temper.kicad_pcb` as a `(name "...")` rule area | **Cross-checked against the real board file, not merely declared.** A paper partition with no matching board geometry is a violation, not a pass — this is the single strongest anti-vacuity check in the schema, because it means the mech claim and the electrical board must agree |
| `partition.separates_pcb_from_airflow` | Literal boolean `true` | Forces an explicit yes/no, not an inferred one |
| `airflow_routing.duct_crosses_pcb_cavity` | Literal boolean `false` | The single sentence at the center of the whole problem — "does the duct cross the compartment" — turned into a field a script reads instead of a claim a human has to parse out of English prose |
| `airflow_routing.duct_geometry_doc` | Path to a document that **must exist** in the repository | The airflow-routing claim must cite something real and committed (e.g. a revised `docs/CHASSIS_AIRFLOW_DESIGN.md` section showing the duct terminates outside the compartment), not a fabricated reference |
| `inspection.criterion_id`, `inspection.method`, `inspection.acceptance_max_gap_mm` (> 0) | A named criterion, a method, and a numeric pass/fail bound | "Verify the barrier is present and intact" (the current `ENVIRONMENTAL_SPEC.md` wording) is not measurable; a numeric acceptance gap is |
| `sign_off.verified_by`, `sign_off.date` (ISO), `sign_off.commit` (`UNKNOWN` or 40-hex, shape-checked) | Who verified it and when | Mirrors this repo's own measurement-provenance convention (`scripts/check_measurement_provenance.py`) rather than inventing a new one |

Every field above is validated for *type*, *non-placeholder content*
(`TBD`/`TODO`/`N/A`/empty and similar are rejected), *sign* (dimensions
must be positive), and, for the two fields where it is possible, *cross-
referenced existence* against real repository state (the board file for
the keepout zone, the filesystem for the airflow-routing document). No
field is validated by matching keywords in free English text — the
`duct_crosses_pcb_cavity: false` / `separates_pcb_from_airflow: true`
booleans exist specifically so the gate never has to guess at what a
sentence "really means."

### 4.2 What was considered and rejected

- **Prose-only sign-off in `docs/ENVIRONMENTAL_SPEC.md` §3.1** (the status
  quo): rejected — this is exactly the currently-unverified state the gate
  exists to close. A human "Do not release... if the cover, gasket, or
  partition is absent" instruction is unenforceable by any script.
- **A CAD/STEP file as the sole artifact**: rejected as the *only* signal —
  a CAD file's existence proves geometry was drawn, not that it was
  reconciled with the real board outline, the real airflow duct, or given
  an inspection bound. The structured YAML instead requires the dimensions
  and the board cross-reference explicitly; a CAD/STEP file remains a good
  *additional* artifact (`cover.part_ref`/`gasket.part_ref` can point at
  one) but is not machine-parseable by this gate and is not required by it.
- **Re-using `scripts/check_isolation_keepout.py`'s existing barrier check
  as sufficient evidence**: rejected — that gate (already in this repo,
  already red for the same underlying reason: `MAINS_SELV_ISOLATION_BARRIER`
  does not exist) verifies the *electrical* board-level keepout's geometry
  (layer span, width, bisection, intrusion, far-side crossing). It says
  nothing about a *cover*, a *gasket*, or whether the *coil/heatsink duct*
  is routed outside the compartment — the mechanical-enclosure claim this
  decision is actually conditional on. The new gate's `partition.
  keepout_zone_name` cross-check deliberately reuses the *same board-file
  fact* (does a named zone exist) without duplicating that gate's own
  geometric analysis, so the two gates check different, complementary
  properties rather than one silently standing in for the other.

## 5. The gate

`scripts/check_pd2_compartment_evidence.py` (registered in
`scripts/manifest.yaml`; tests in
`scripts/tests/test_check_pd2_compartment_evidence.py`) implements Section
4 above:

1. Reads `scripts/generate_kicad_dru.py` live to determine which bar the
   tree currently claims (`HV_CREEPAGE_ENFORCED_MM`). If PD3 governs, the
   compartment prerequisite is moot and the gate reports `not_applicable`
   (a real, positive verdict, not a silent skip).
2. If PD2 governs, `docs/specs/pd2_compartment_evidence.yaml` must exist
   and every field in Section 4.1's table must validate, including the
   live cross-check of `partition.keepout_zone_name` against a real
   `(name "...")` zone in `pcb/temper.kicad_pcb`.
3. Exit codes match this repo's gate-family convention: `0` = PASSED or
   NOT_APPLICABLE, `3` = VIOLATION (a real, substantive finding — evidence
   missing, incomplete, placeholder, or board-geometry-mismatched), `5` =
   GATE ERROR (the gate could not determine which bar governs at all).

The gate is fast and deterministic: pure text/YAML parsing, no
`kicad-cli`, no solver, no network, no package import beyond `yaml` and
this repo's own `scripts/_lib` helpers. Runtime is well under a second.

### 5.1 Proof it fails today

```
$ uv run python scripts/check_pd2_compartment_evidence.py
PD2 compartment-evidence gate -- tree currently claims PD2 (8.0mm reinforced creepage)

Evidence file: docs/specs/pd2_compartment_evidence.yaml (present: False)

=== VIOLATIONS: 1 ===
  VIOLATION docs/specs/pd2_compartment_evidence.yaml does not exist -- the tree claims
  PD2/8.0mm (generate_kicad_dru.py's HV_CREEPAGE_ENFORCED_MM) but no compartment
  evidence artifact has been committed

FAILED -- 1 violation(s). The tree claims PD2/8.0mm without a complete, real
compartment. See docs/evidence/2026-08-11-pd2-decision-record.md.
$ echo $?
3
```

This is **correct and is the point** — the compartment does not exist, so
the gate must say so. `scripts/tests/test_check_pd2_compartment_evidence.py::
TestRealRepoIntegration` pins this exact behavior against the real repo
files (not a fixture) so any future change either fixes the gap for real or
has to consciously update the test that documents it.

### 5.2 Proof it passes once the compartment evidence is present

Against a synthetic tree (`--evidence`/`--board` pointed at scratch
fixtures built from the same `generate_kicad_dru.py`, with a complete,
non-placeholder `pd2_compartment_evidence.yaml` and a board file carrying
the matching `MAINS_SELV_ISOLATION_BARRIER` named zone):

```
$ uv run python scripts/check_pd2_compartment_evidence.py \
    --evidence /tmp/.../synthetic_evidence.yaml \
    --board /tmp/.../synthetic_board/board.kicad_pcb
PD2 compartment-evidence gate -- tree currently claims PD2 (8.0mm reinforced creepage)

Evidence file: /tmp/.../synthetic_evidence.yaml (present: True)

=== VIOLATIONS: 0 ===

PD2 compartment-evidence gate passed -- compartment evidence is complete,
non-placeholder, and cross-checked against the real board.
$ echo $?
0
```

`scripts/tests/test_check_pd2_compartment_evidence.py::TestRunEndToEnd::
test_pd2_governs_complete_evidence_and_matching_zone_passes` pins the same
result as a unit test. The full suite (31 tests: pure-function unit tests
for `load_enforced_bar`, `load_board_zone_names`, and
`validate_evidence_fields`; synthetic end-to-end `run()` scenarios;
anti-vacuity cases; and the two real-repo integration tests above) passes:

```
$ uv run pytest scripts/tests/test_check_pd2_compartment_evidence.py -v
...
============================== 31 passed in 0.64s ==============================
```

### 5.3 Landed advisory, with a named path to blocking

Wired into `.github/workflows/python-tests.yml`'s `consistency-gates` job
(`Cross-Source Consistency Gates`) as Gate 4, alongside the three
correspondence gates PR #1030 landed the same day for the identical
"declares something, nothing verifies it" shape. Like those three, this
gate runs its real check and prints a real verdict on every PR — only the
CI step's `continue-on-error: true` prevents the still-missing compartment
from failing builds today.

**Path to blocking:** build the real cover/gasket/partition, revise the
airflow-routing documentation to show the duct terminates outside the
compartment, add the `MAINS_SELV_ISOLATION_BARRIER` keepout to
`pcb/temper.kicad_pcb` (also required to clear `scripts/
check_isolation_keepout.py`, already red for the same underlying gap),
commit `docs/specs/pd2_compartment_evidence.yaml` with every field
populated for real, confirm the CI step goes clean, then remove
`continue-on-error` from the "PD2 compartment-evidence gate (Gate 4)" step.

Per `.github/required-checks.json`'s existing `trigger_paths` (which
already includes `scripts/**` and `.github/workflows/**`, and was not
modified by this change per the task's boundaries), this gate runs on any
PR that touches its own script or the workflow — it does not yet run on
every PR unconditionally the way a fully-required check would; that is a
separate, later decision (adding the `consistency-gates` job to
`required_contexts`) same as it was for Gates 1-3.

---

## Files

- This document: `docs/evidence/2026-08-11-pd2-decision-record.md`
- Resolution appended (not edited) to the still-open decision pack:
  `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`
- Gate: `scripts/check_pd2_compartment_evidence.py`
- Tests: `scripts/tests/test_check_pd2_compartment_evidence.py`
- Manifest entry: `scripts/manifest.yaml` (`check_pd2_compartment_evidence.py`)
- Workflow wiring: `.github/workflows/python-tests.yml`,
  `consistency-gates` job, "PD2 compartment-evidence gate (Gate 4)" and its
  paired test step
- Cited: `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`,
  `docs/evidence/2026-07-30-pd2-enclosure-decision.md`,
  `docs/plans/2026-08-11-002-feat-placer-wirelength-and-hv-separation-plan.md`
  (PD3 not-established-feasible spike), `docs/ENVIRONMENTAL_SPEC.md` §3.1,
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2.1,
  `docs/CHASSIS_AIRFLOW_DESIGN.md`, `docs/ASSEMBLY_GUIDE.md`,
  `scripts/check_isolation_keepout.py`,
  `scripts/check_measurement_provenance.py` (provenance-field convention
  this document's `sign_off` schema mirrors), the three correspondence
  gates landed the same day
  (`docs/evidence/2026-08-11-correspondence-gates.md`,
  `scripts/check_pcl_config_board_correspondence.py`,
  `scripts/check_layer_plane_emission_coverage.py`).
- Not modified by this document (see Section 3): `pcb/temper.kicad_pcb`,
  `pcb/temper.kicad_pro`, `power_pcb_dataset/**`,
  `.github/required-checks.json`, any DRU/keepout/creepage constant.
