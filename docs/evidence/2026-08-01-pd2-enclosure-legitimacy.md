<!-- provenance: commit=e5bd461e276b65d0499f0ecd4a9ff29309f2c1bd dirty=false -->

# PD2 enclosure legitimacy — decision pack: which creepage bar actually governs the board

**Date:** 2026-08-02
**Branch:** `evidence/pd2-enclosure-decision-2` (worktree
`.claude/worktrees/agent-pd2-enclosure-r2`), based on `origin/main` at
`e5bd461e276b65d0499f0ecd4a9ff29309f2c1bd` (verified clean via
`scripts/assert-base.sh origin/main`).
**Scope:** DOC-ONLY. No `src/`, no `pcb/`, no `elec/` change. Every figure
below was read from the committed tree at the provenance SHA (code files),
or quoted from an already-committed evidence doc with its own provenance
(named per citation). No solver/validator was executed this session; the
code-state claims are direct reads of the committed sources.
**Owner decision requested:** which reinforced-creepage bar governs the
board — **PD2/8.0mm** (validator + DRU/keepout currently enforce it) or
**PD3/12.6mm** (the standard's fallback for the *as-built* forced-air-vented
construction).

---

## TL;DR — for the owner

1. **The design is forced-air-vented, not sealed.** The board outline is a
   plain rectangle with zero vent/compartment provisions; the fan is
   off-board on leadwires; the chassis routes bottom-intake air through an
   80mm fan → IGBT-heatsink duct → rear exhaust across the same cavity the
   PCB occupies. The "sealed gasketed PCB compartment" exists only as a
   *prescriptive release requirement* in the mech docs — no cover, gasket,
   partition, or inspection geometry is committed anywhere. **On the
   standard's own condition, PD3/12.6mm is what governs the as-built
   construction today.**
2. **The enforcement tree is NOT split at `origin/main` HEAD.** The
   handoff's claim ("validator enforces 12.6, DRU/keepout enforce 8.0
   [verified]") is stale: it was verified on branch `fix/k2k3-relay-swap`,
   which does **not** contain commit `9a3233a60` ("adopt PD2/8.0mm
   reinforced creepage in the REQ-SAFE-01 validator", 2026-07-30). That
   commit IS on `origin/main` (it is an ancestor of `f20400709`, the
   handoff's own stated base). At the provenance SHA, **all four
   enforcement points — validator, DRU, keepout, placement corridor — are
   aligned at 8.0mm/PD2.** The consequence is not "placement passes DRU and
   fails validator"; it is that the whole tree is aligned at a bar the
   standard only earns once the sealed compartment is actually built.
3. **Three options, honest trade-offs:**
   - **(a) Build the sealed compartment** — keeps 8.0mm everywhere; scope =
     real mech geometry (cover/gasket/partition), an assembly drawing with
     inspection points, production verification, and a thermal re-check
     (the existing thermal bound is marginal at the repo's hot-ambient
     band). Risk: mech design + verification effort; the board itself
     already satisfies the 8.0mm bar.
   - **(b) Accept PD3/12.6mm as governing** — retargets every enforcement
     point (validator matrix, `HV_CREEPAGE_ENFORCED_MM`, `MIN_BARRIER_WIDTH_MM`,
     corridor, keepaway margin) to 12.6; the K3 re-solve wall gets harder
     (PD3 measurement: K3 is in the 7-of-8 infeasible isolator set even
     with verified substitutions), and K3's RT314012 swap becomes
     mandatory (12.76mm achievable clears 12.6; the incumbent G5LE-1's
     3.559mm intra gap fails both bars).
   - **(c) Reconcile the "split"** — the split the handoff describes no
     longer exists on `main`; the only reconciliation left is between the
     *enforcement* (8.0) and the *physical enclosure reality* (unsealed),
     which is exactly the choice between (a) and (b).
4. **Recommendation: (a) — commit to the sealed compartment, or if the
   owner will not fund the mech work, explicitly retarget to (b).** Keeping
   8.0mm enforced while the as-built construction is forced-air-vented is
   the one indefensible state: it looks compliant and is not. The 8.0mm
   enforcement is only legitimate if the PD2 exception is genuinely earned,
   and the repo's own specs (`docs/ENVIRONMENTAL_SPEC.md` §3.1,
   `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2.1) say exactly that.

---

## 1. Physical facts from the committed design — sealed vs forced-air-vented

### Verdict: **forced-air-vented. The committed design contains no sealed-compartment provisions.**

#### 1.1 Board geometry — no vent holes, no cutouts, no keepout zone

- **Edge.Cuts outline** (`pcb/temper.kicad_pcb`, the only outline polygon,
  lines ~8262-8268):
  ```
  (gr_poly (pts (xy 20 20) (xy 172 20) (xy 172 254) (xy 20 254))
    (layer "Edge.Cuts") (width 0.1))
  ```
  A single plain rectangle = **152mm × 234mm board** (matching the
  2026-07-30 thermal-bound doc's own measured figure, which also flags the
  stale 100×150mm in `docs/specs/PCB_SPECIFICATION.md` §2). No vent-hole
  arrays, no notches, no mounting-hole cutouts, no slots:
  - `grep -cE "\(hole|\(slot" pcb/temper.kicad_pcb` → **0**
  - `grep -c "MountingHole" pcb/temper.kicad_pcb` → **0**
  - `grep -c "keepout" pcb/temper.kicad_pcb` → **0** (no
    `MAINS_SELV_ISOLATION_BARRIER` keepout zone exists — the PD2 decision
    doc's "What this decision does not close" section already recorded this)
- **Fan is off-board.** `elec/src/modules.ato` ThermalSystem (lines
  ~1652-1662): *"Forced-air cooling: fan power circuit (PCB side). ... The
  fan itself is off-board (leadwires to J_FAN)"*. The board carries only a
  1×02 pin header (`j_fan`); the Sunon MF60251V1 fan is chassis BOM.
- **The `gr_` graphics layer has exactly one shape** (`grep -cE "^\s*\(gr_"`
  → 1, the outline itself) — no vent-graphic annotations, no fan/vent
  silk marks.

#### 1.2 Chassis/mech docs — forced-air path crosses the PCB cavity, and the "sealed compartment" is prescriptive only

- **`docs/CHASSIS_AIRFLOW_DESIGN.md`** §2/§3 (quoted in the pollution-degree
  determination, read directly): the cooling system is forced convection —
  **bottom chassis intake vents → intake plenum → 80mm PWM fan (Noctua
  NF-A8) → transition duct → IGBT heatsink → rear exhaust (new 80mm
  opening)**. Requirement REQ-MECH-03: ≥15 CFM across the heatsink fins.
  This actively draws unfiltered kitchen air (grease, steam, cooking
  aerosol) through the same chassis cavity the PCB occupies. "Enclosed"
  in that doc's overview describes the outer appliance case, not a sealed
  PCB compartment excluded from the airflow.
- **`docs/COIL_BRACKET_DESIGN.md`** §4: *"Large triangular cutouts around
  the central coil ring allow air from the bottom intake to flow directly
  through the Litz wire strands"* — an air-permeable baffle **by design**,
  sitting directly above the main PCB. Not a seal.
- **`docs/ASSEMBLY_GUIDE.md`** Phase 1.2: *"Cut an 80mm circular opening in
  the rear panel for the exhaust fan."* Phase 4.3 mounts the PCB on M3
  standoffs. The **only gasket** in the whole guide (Phase 3.2) seals the
  **glass-ceramic cooktop to the chassis lip** — a different joint, sealing
  glass, not excluding pollution from the electronics.
- **The "PCB Pollution Barrier" item is an assembly-time instruction, not a
  designed artifact**: `docs/ASSEMBLY_GUIDE.md` Phase 4.2 — *"Install the
  covered, gasketed PCB compartment and verify that the coil/heatsink
  airflow path does not enter it. Do not release the assembly as PD2 if
  the cover, gasket, or partition is absent or damaged."* Same for
  `docs/ENVIRONMENTAL_SPEC.md` §3.1 ("Before release, the mechanical design
  must demonstrate all of the following: a gasketed PCB compartment or
  equivalent pollution barrier; no direct path from the coil/heatsink
  forced-air duct into the PCB compartment; ...") and
  `docs/CHASSIS_AIRFLOW_DESIGN.md` §3.3. **No document contains the
  compartment's geometry, an assembly drawing with the boundary, or a
  part/BOM entry for the cover, gasket, or partition.** No `.step`/`.stl`/
  `.fcstd`/CAD file exists anywhere in the repo (searched).
- **IP20 is the declared rating** (`docs/ENVIRONMENTAL_SPEC.md` §3):
  "No liquid ingress protection guaranteed" — argues *against* an enclosure
  claim, and neither IP20 digit addresses airborne grease/steam, which is
  exactly what the forced-air duct is designed to move across the
  compartment.
- **The pollution-degree determination's own independent reading agrees**
  (`docs/evidence/2026-07-30-pollution-degree-determination.md` §1.2,
  CITED-PRIMARY + MEASURED): *"No document in this repository specifies a
  sealed, gasketed PCB compartment separate from the coil/heatsink airflow
  path. The PD2 exception is therefore not earned on the evidence available
  today."* The 2026-07-30 thermal-bound doc states the same construction
  fact: *"the PCB sits standoff-mounted in the same forced-air-ventilated
  cavity as the coil and heatsink duct."*

**Definitive statement: the committed design contains no sealed-compartment
provisions.** No vent holes in outline/pour geometry (because there is no
compartment to vent), no cover/gasket/partition part or drawing, no
`MAINS_SELV_ISOLATION_BARRIER` keepout, no board mounting provisions
beyond standoffs. The "compartment" exists in prose as a release
prerequisite only.

#### 1.3 K3's relay (G5LE-1) relative to any compartment boundary

**There is no compartment boundary in the design, so K3 has no "side" to be
on** — it sits in the shared forced-air cavity with everything else.

- **K3 board position** (`pcb/temper.kicad_pcb` footprint
  `Relay_THT:Relay_SPDT_Omron-G5LE-1`, line ~3889-3890): `(at 69.72 29 90)`
  — 49.7mm from the left edge, **9.0mm from the top edge** of the 152×234
  board (top edge y=20). K3 is the discharge relay `discharge.k_dis2`
  (elec/domain_manifest.yaml: k_dis2 contacts = HV-side; coil = SELV coil
  drive).
- **K3's own intra-footprint gap is the single remaining REQ-SAFE-01
  violation on the board**: G5LE-1's coil-to-contact copper gap is
  **3.559mm** — below the 4.0 basic, 6.0 clearance, and 8.0/12.6 reinforced
  bars alike (run-B evidence doc: "3 violations / 1 pair, all K3-intra").
  This is placement-independent (fixed terminal topology; the RT314012
  swap's 12.76mm achievable coil-to-contact gap clears even 12.6mm).
- Consequence for the decision: K3 needs the RT314012 swap **under either
  bar**. The enclosure decision changes the difficulty of the surrounding
  domain-clearance solve (8.0 vs 12.6 to every cross-domain neighbour),
  not the K3 swap itself.

---

## 2. The standard's condition — when is PD2/8.0 legitimate vs PD3/12.6

### 2.1 The governing clause chain (from the committed PD3 determination, CITED-PRIMARY)

- **IEC 60335-1 cl. 29.2** (base rule): pollution degree 2 applies
  *unless* the insulation is subjected to conductive pollution (→ PD3).
- **IEC 60335-2-6 cl. 29.2 Addition** (this appliance's *particular*
  standard — cooking ranges/hobs): **PD3 is the default microenvironment
  for this appliance class; PD2 is an exception that must be earned by an
  enclosure/sealing argument.** The repo's own specs restate this:
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2.1: "IEC 60335-2-6
  clause 29.2 Addition makes PD3 the default for cooking appliances unless
  the insulation is enclosed or located so that it is unlikely to be
  exposed to pollution during normal use."
- **Table 17 row iv** (>250V, ≤400V working voltage, Material Group
  IIIa/IIIb), reinforced creepage, doubled per cl. 29.2.3
  (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.3 table):
  | PD2 reinforced | PD3 reinforced |
  |---|---:|
  | **8.0mm** | **12.6mm** |

### 2.2 The condition, stated as a test

**PD2/8.0mm is legitimate if and only if** a genuinely sealed, gasketed PCB
compartment separate from the coil/heatsink forced-air path is built and
verified (IEC 60335-2-6 cl. 29.2 addition earned). The five release
conditions are enumerated verbatim in `docs/ENVIRONMENTAL_SPEC.md` §3.1
(compartment or equivalent barrier; no duct path into the compartment; no
exposed PCB insulation in the grease/steam/aerosol path; assembly +
inspection criteria; documented review). **Otherwise PD3/12.6mm governs.**
The 2026-07-30 owner decision
(`docs/evidence/2026-07-30-pd2-enclosure-decision.md`) selected PD2 as the
*production target* conditional on exactly that prerequisite — it did not
claim the current vented layout already qualifies ("not a claim that the
existing vented layout already qualifies"; "This decision therefore
authorizes the PD2 target but does not claim that the board is yet
fabrication-ready").

**Where the matrix rows live in code** —
`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`,
`IEC60335_REQUIREMENTS` at **line 302**; at the provenance SHA the
enforced values are (already the PD2/8.0 set — see §3):

| boundary | insulation | min_clearance_mm | min_creepage_mm | design_value_mm | lines |
|---|---|---:|---:|---:|---|
| MAINS ↔ LV_CONTROL | BASIC | 3.0 | **4.0** | 6.0 | 303-307 |
| MAINS ↔ LV_CONTROL | REINFORCED | 6.0 | **8.0** | 10.0 | 308-312 |
| DC_BUS ↔ LV_CONTROL | BASIC | 3.0 | **4.0** | 6.0 | 313-317 |
| DC_BUS ↔ LV_CONTROL | REINFORCED | 6.0 | **8.0** | 10.0 | 318-322 |
| MAINS ↔ ISOLATED | REINFORCED | 6.0 | **8.0** | 10.0 | 323-327 |
| LV_CONTROL ↔ LV_CONTROL | FUNCTIONAL | 0.5 | **1.0** | 2.0 | 328-332 |

`verify_iec60335_compliance` (line 765) walks this matrix; `design_value_mm`
is not read by the validator (line 271 comment).

---

## 3. The tree-split enumeration (corrected against `origin/main` HEAD)

### 3.1 The handoff's split claim, and why it is stale

`docs/handoffs/2026-08-01-k3-gap2-validator-audit-handoff.md` §5.3:
*"Tree is currently **split**: validator enforces 12.6 (PD3), DRU/keepout
enforce 8.0 (PD2) [verified]."*

**This is not the state of `origin/main`.** Verification:

- Commit **`9a3233a60`** ("safety: adopt PD2/8.0mm reinforced creepage in
  the REQ-SAFE-01 validator", authored 2026-07-30) changes the validator's
  matrix from the PD3 fallback (12.6/6.3) to PD2 (8.0/4.0), and is an
  ancestor of **`f20400709`** — the handoff's *own stated base* — and of
  `origin/main` HEAD (`git merge-base --is-ancestor 9a3233a60 f20400709` →
  exit 0; `git show f20400709:...clearance.py` → 8.0mm rows).
- The handoff was committed on branch **`fix/k2k3-relay-swap`**, whose
  clearance.py still shows 12.6 because that branch **does not contain
  `9a3233a60`** (`git merge-base --is-ancestor 9a3233a60
  fix/k2k3-relay-swap` → non-zero; the branch's main-merge `ef5d8d820`
  predates the validator alignment entering `main`). The "[verified]"
  claim was verified on that branch's tree, not on the base it names.
- No commit between `f20400709` and the provenance SHA touches
  clearance.py (`git log f20400709..HEAD -- clearance.py` → empty), so the
  8.0mm state is stable through HEAD.

### 3.2 The actual enforcement tree at the provenance SHA — aligned at 8.0/PD2

| # | Enforcement point | Location | Value at SHA | 12.6 fallback retained? |
|---|---|---|---|---|
| 1 | **REQ-SAFE-01 validator** (matrix + `verify_iec60335_compliance`) | `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:302-333` (matrix), `:765` (verify) | reinforced creepage **8.0** / basic 4.0 | yes, as re-dated derivation comments only (lines 215, 236, 251) |
| 2 | **KiCad DRU generator** | `scripts/generate_kicad_dru.py:77` (`HV_CREEPAGE_PD2_MM = 8.0`), `:78` (`HV_CREEPAGE_PD3_MM = 12.6` fallback), `:106` (`HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM`); emitted `(constraint creepage (min 8.0))` at `:421/:474/:654`; output `pcb/temper.kicad_dru` (generated, not committed) | **8.0** enforced, 12.6 declared as fallback | **yes — declared, structurally selected** (drift gate `scripts/check_creepage_clearance_drift.py:206-215` recognises the NAME2=NAME1 selection alias) |
| 3 | **Physical isolation keepout gate** | `packages/temper-placer/src/temper_placer/core/isolation_constants.py:45` (`MIN_BARRIER_WIDTH_MM = 8.0`), consumed by `scripts/check_isolation_keepout.py:152,569,894` | **8.0** | no literal; PD3 discussed in module docstring |
| 4 | **Placement corridor** (CP-SAT isolator corridor) | `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py:150` (`DEFAULT_CORRIDOR_WIDTH_MM = MIN_BARRIER_WIDTH_MM + 0.5` = **8.5**) | 8.5 (= 8.0 + design margin), derived from #3 | derives automatically from #3 |
| 5 | **Solver domain-clearance + unclassified keepaway margins** | `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py:248-253` (`MAX_IEC_MARGIN_MM = max(...)` of the matrix = **8.0**), `:222` (`required_margin_mm`), `:364` (`generate_unclassified_hv_keepaway_constraints`, default margin = MAX_IEC_MARGIN_MM) | **8.0** (computed from the matrix itself — cannot drift from #1) | no — tracks the matrix |
| 6 | **elec constraint declarations** | `elec/src/constraints.ato:36` (`creepage = 8.0mm`), `:84,96` (`min_creepage = 8.0mm`) | **8.0** | — |
| 7 | **PCL solver config** | `packages/temper-placer/configs/pcl/temper_production.yaml:111-135` (`min_distance_mm: 8.0`) | **8.0** | — |
| 8 | **Netclass rules (placer-feasibility)** | `packages/temper-placer/configs/netclass_rules.yaml:17,28,61` (`creepage_mm: 6.0` for ACMains/HighVoltage/HighVoltageIsolated) | 6.0 — explicitly *not* fab-authoritative (comment at `:53`: "the fab-authoritative enforcement point is generate_kicad_dru.py's HV_CREEPAGE_ENFORCED_MM") | — |

**Consequence stated precisely:** a placement can still differ between the
solver's *box* bar and the validator's *exact-copper* bar (that is the
measured, separate gap-2 finding — 45 box-violated / 0 copper-violated
pairs on the canonical domain/keepaway basis, `spike/gap2-wall-box-vs-copper`
`gap2_wall_summary.json`). But it **cannot** pass a DRU/keepout gate at 8.0
and then fail a validator still at 12.6 — the validator is also at 8.0 on
`main`. The real inconsistency the owner faces is between the **enforcement
(8.0)** and the **as-built enclosure (unsealed → PD3/12.6 governs)**.

The drift gate (`scripts/check_creepage_clearance_drift.py`) cross-checks
declared creepage/clearance literals across `elec/`, `scripts/`,
`packages/`, `configs/` and enforces family consistency (exit 3 on
MISMATCH, exit 5 fail-closed on vacuity) — it currently sees a consistent
8.0 family, with `HV_CREEPAGE_PD3_MM = 12.6` reported under "declared but
not enforced". Any future retarget must move every point in the table
together or the gate goes red.

---

## 4. The owner's options, with honest trade-offs

### Option (a) — Build the sealed compartment (keep 8.0mm)

**What the design would need (from §1.2 — every item is currently
missing):**
1. Real compartment geometry: a cover, gasket interface, and partition
   between the PCB and the coil/heatsink duct (part/BOM entries + a CAD or
   dimensioned drawing; none exists).
2. An assembly drawing identifying the compartment boundary, gasket
   interface, service openings/cable penetrations, and inspection points
   (`docs/ENVIRONMENTAL_SPEC.md` §3.1 and the PD2 decision doc both name
   this as a hard release requirement).
3. A board/keepout-side element so the boundary is checkable: the
   `MAINS_SELV_ISOLATION_BARRIER` keepout (`scripts/check_isolation_keepout.py`
   currently has no geometry to measure — the PD2 decision doc already
   records this gate as red).
4. Thermal re-verification: the committed thermal bound
   (`docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md`) concludes
   a sealed compartment is *marginal* — viable for normal-to-warm ambient,
   not comfortably viable at the repo's own 55–70°C worst-case band,
   because the LMR51430 buck and UCC21550 gate driver already run near
   Tj-max with airflow; removing airflow pushes them past zero margin in a
   sizeable fraction of the assumption space.

**Scope:** mech design + BOM + assembly/inspection docs + thermal
validation + the board keepout element. No electrical/placer change; the
8.0mm tree stays as-is.
**Risk:** the thermal marginality (mitigation likely needed — e.g. a
ducted-but-filtered path, higher fan, or derating); production-inspection
burden to keep the barrier intact.
**Meaning for the K3 re-solve candidate:** unchanged bar (8.0). The K3
RT314012 swap is still required (3.559mm intra fails 8.0). The wall-spike
repair recipe (§6 of the gap-2 doc) already produces a validator-clean
C27-on-board placement at 8.0; the remaining work is the zone-inclusive
fixed-copper solve and the gap-2 copper-accurate constraint.

### Option (b) — Accept PD3/12.6mm as governing (retarget the tree)

**What changes** (every enforcement point in §3.2, together — the drift
gate enforces unanimity):
- Validator matrix: reinforced creepage 8.0 → **12.6**, basic 4.0 → 6.3,
  design 10.0 → 14.6 (this is exactly what `9a3233a60` reverted).
- `HV_CREEPAGE_ENFORCED_MM` → `HV_CREEPAGE_PD3_MM` (12.6).
- `MIN_BARRIER_WIDTH_MM` → 12.6; corridor → 13.1 (derived).
- `MAX_IEC_MARGIN_MM` → 12.6 (matrix-derived, automatic).
- `elec/src/constraints.ato`, pcl yaml, netclass rules → 12.6/6.3.
- Measured consequence on the *unchanged* board (from `9a3233a60`'s own
  before/after): REQ-SAFE-01 **123 violations / 86 pairs at 12.6** vs
  **53 / 25 at 8.0** (the pre-#517 board; the re-solved board is below
  that but the direction is the same). The 45 box-bar pairs from the
  wall-spike measurement are all 8.0-bar pairs — at 12.6 the copper bar
  rises 4.6mm and many of the marginal GAP2-HOLDS (copper 8.5–25mm) become
  genuine copper violations; the "0 copper-violated" verdict does **not**
  survive the bar change.
- **K3/C27 consequences (measured in the committed PD3 evidence):**
  - `docs/evidence/2026-07-30-pd3-board-expansion-measurement.md`:
    at 12.6mm, K3 is in the **7-of-8 infeasible isolator set**
    (`C6, K1, K2, K3, T1, U3, U7`) even after board expansion to
    +100% per dimension, and in the reduced 4-set (`K1, T1, U3, U7`)
    after the verified substitutions (C6/K2/K3 → RT314012-class parts);
    the model is still INFEASIBLE (UNSAT core `isolator_straddle_K1`).
  - `docs/evidence/2026-07-30-pd3-inter-component-creepage-board-expansion.md`:
    at 12.6mm, **196 violating HV↔SELV pad pairs / 75 component groups**
    on the real board; the 39 intra pairs / 7 groups are bit-for-bit
    invariant to board size.
  - `docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md` §3.4:
    "the 12.6mm domain bar, even scoped to the free set, forces a full
    re-layout" — free refs move 30–280mm.
  - K3's RT314012 swap becomes **mandatory** (G5LE-1 3.559mm fails 12.6;
    RT314012's 12.76mm achievable gap passes 12.6 with 0.16mm margin).

**Scope:** a coordinated constant retarget + full re-solve + DRC re-measure
+ `drc_ceiling.json` re-measure in the same PR (AGENTS.md board-change
protocol). This reverses the 2026-07-30 owner decision's PD2 selection.
**Risk:** re-opens the whole PD3 wall the #517 re-solve paid down; the
board may not be PD3-feasible at all without a slot or full re-layout.
**Meaning for K3 re-solve:** the wall gets harder, not easier; the K3 swap
is still the right move but the surrounding solve must handle the 12.6
domain bar to every cross-domain neighbour.

### Option (c) — Reconcile the "split" (align the tree to one bar)

**What the handoff calls "the split" no longer exists on `main`** (§3.1):
commit `9a3233a60` already aligned the validator to the DRU/keepout 8.0 in
July. The only remaining misalignment is between the enforcement (8.0) and
the physical enclosure (unsealed). So "reconcile" collapses into (a) vs
(b):
- **Validator→8.0 reconciliation is done.** Nothing to do.
- **DRU/keepout→12.6 reconciliation** = Option (b) with the validator
  moved back up to match.
- **Keep 8.0 with the enclosure change** = Option (a); the enclosure is
  the only thing standing between the current tree and legitimacy.

**Scope/Risk:** zero new work beyond (a)/(b) — this option is the honest
framing, not a third path.

---

## 5. Recommendation

**Build the sealed compartment (a) — or, if the owner will not fund the
mech work, retarget to 12.6 (b) now, explicitly.** The one state to avoid
is the current one: 8.0mm enforced across the whole tree while the
as-built construction is forced-air-vented and PD3/12.6 governs per the
standard. That state is not "conservative" — it is a compliance claim the
design does not yet earn, and the repo's own specs already say so.

- The 2026-07-30 decision already *chose* PD2 as the production target,
  conditional on the compartment. Option (a) is executing that decision;
  the honest prerequisite list is short and concrete (§4a items 1-4).
- If the mech work is not funded, (b) is the defensible fallback and must
  be done deliberately (all points together, re-measure DRC, re-solve),
  not left as a latent drift.
- The K3 RT314012 swap is required under both bars — it is not gated on
  this decision. What the decision *does* gate is whether the K3 re-solve
  continues against the 8.0 bar (feasible repair placement already
  demonstrated by the wall spike) or must also absorb the 12.6 domain bar
  (full re-layout wall, PD3 measurements say infeasible without a slot).

**Owner action needed:** pick (a) or (b); the tree is already aligned, so
the decision is purely about the enclosure/venting reality and the funding
for it.

---

## Files

- This document: `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`
- Primary sources read (all at the provenance SHA): `pcb/temper.kicad_pcb`,
  `elec/src/modules.ato`, `elec/domain_manifest.yaml`,
  `elec/src/constraints.ato`, `docs/CHASSIS_AIRFLOW_DESIGN.md`,
  `docs/ASSEMBLY_GUIDE.md`, `docs/COIL_BRACKET_DESIGN.md`,
  `docs/ENVIRONMENTAL_SPEC.md`, `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`,
  `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`,
  `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py`,
  `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`,
  `packages/temper-placer/src/temper_placer/core/isolation_constants.py`,
  `scripts/generate_kicad_dru.py`, `scripts/check_isolation_keepout.py`,
  `scripts/check_creepage_clearance_drift.py`,
  `packages/temper-placer/configs/pcl/temper_production.yaml`,
  `packages/temper-placer/configs/netclass_rules.yaml`
- Prior evidence cited: `2026-07-30-pd2-enclosure-decision.md`,
  `2026-07-30-pollution-degree-determination.md`,
  `2026-07-30-pcb-compartment-thermal-bound.md`,
  `2026-07-30-pd3-board-expansion-measurement.md`,
  `2026-07-30-pd3-inter-component-creepage-board-expansion.md`,
  `2026-07-31-k3-rtsolve-infeasible-board.md`,
  `2026-08-01-k3-runb-not-validator-clean.md`,
  `2026-08-01-solve-wall-box-vs-copper-gap.md` (branch `spike/gap2-wall-box-vs-copper`),
  handoff `2026-08-01-k3-gap2-validator-audit-handoff.md` (branch `fix/k2k3-relay-swap`)
- Git facts: `9a3233a60` (validator PD2 adoption, on `main`), `f20400709`
  (handoff's stated base, contains `9a3233a60`), `fix/k2k3-relay-swap`
  (handoff branch, lacks `9a3233a60`)
