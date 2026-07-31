# Handoff — safety-requirement and geometry work, 2026-07-30/31

**Status:** in progress. One task is mid-flight with verified analysis but uncommitted
code. Everything else is either merged or is an owner decision.

Claims below are marked **[verified]** where I measured them myself in this session,
and **[reported]** where they come from another agent's or session's account that I
did not independently reproduce. Treat unmarked prose as narrative.

---

## 1. Immediate next action: K2/K3 relay swap

**Branch:** `fix/k2k3-relay-swap` (worktree `.claude/worktrees/k2k3-swap`, based on
`origin/main` @ `4a387393e`).

**State:** `pcb/libs/temper.pretty/Relay_SPDT_Schrack-RT314012.kicad_mod` is copied in
and **uncommitted**. Nothing else has been touched. `pcb/temper.kicad_pcb` and
`elec/src/**` are clean.

### The verification that matters is already done

K2/K3 (discharge relays) currently use Omron `G5LE-1`, whose coil-to-contact creepage
is **3.559 mm** [reported]. That fails both the operative 8.0 mm reinforced creepage
requirement and the **6.0 mm clearance minimum** — the latter is pollution-degree
independent, so the PD2 enclosure decision does not rescue it. These are the last
isolator blockers on the mains↔SELV barrier.

Replacement `RT314012` (TE Schrack RT1), computed by hand from the footprint
geometry **[verified]**:

| | value |
|---|---|
| coil pads (2, 5) at x=0, size 3×2 | rightmost copper edge **+1.5 mm** |
| nearest contact pad (4) at x=15.26, size 2×3 | leftmost copper edge **14.26 mm** |
| **coil-to-contact copper gap** | **12.76 mm** |
| vs 8.0 mm reinforced creepage | PASS, 1.6× |
| vs 6.0 mm clearance minimum | PASS, 2.1× |

12.76 independently reproduces the **12.760 mm** figure the sourcing analysis derived
from the datasheet by a different route, which is why I trust a footprint I did not
watch get built.

Footprint provenance: `descr` records `ENG_DS_RT1_0718` re-fetched and
pdftotext-extracted with the source URL cited; coil A1/A2 renumbered 2/5 and contacts
12/11/14 renumbered 4/1/3 per the project's `Relay_SPDT` convention; each contact
carries two physical solder holes sharing one pad number for 16 A current sharing,
"confirmed against the datasheet's own 8-hole dimensioned drawing".

### Remaining steps

1. Commit the footprint.
2. Update `elec/src/` — MPN, footprint, and any coil/contact parameters the modules
   assert on. **If an existing `assert` fails, that is a finding — report it, do not
   relax it.** Rebuild the netlist (`make netlist`); `elec/build/` is gitignored, and
   several gates ERROR rather than fail without it.
3. Propagate the embedded footprint into `pcb/temper.kicad_pcb` following
   `docs/evidence/2026-07-29-board-regeneration-corrected-footprints.md` (PR #426's
   method). The board carries embedded footprint copies; a library change does not
   reach it.
4. Measure and report (see §5 for the required proof).

**Deferred deliberately:** placing `tank.c_tank3`, currently staged at
`(20.0, 272.75)` outside the board outline. Its position is derivable from `C25`/`C26`
(`tank.c_tank1`/`tank.c_tank2` — same net function, same
`temper:C_Axial_L34.0mm_D22.5mm_P40.00mm` footprint, same HV domain). Do it after the
relay lands; the RT314012's courtyard may change what fits.

---

## 2. What landed

**The board**

- Intra-component copper shorts **60 → 0** [verified]. Two independent causes: a
  writer that rotated pad positions but not pad bodies, and three hand-built footprints
  overlapping in their own local frames.
- Six drifted footprints corrected and propagated; the board had been carrying stale
  embedded copies of source fixes made days earlier.
- `tank.c_tank3` added (staged, unplaced) — it existed in `elec/src` with no footprint
  on the board at all.

**The safety requirement** — audited on three independent axes, and **two of the three
corrections were to the requirement itself**, not the board:

- Voltage row: the validator read IEC 60335-1 Table 17's 300 V row against a
  340–400 V bus.
- Insulation tier: `REINFORCED` confirmed correct for `(DC_BUS, LV_CONTROL)` —
  `LV_CONTROL` is operator-accessible via a user-touchable food-contact RTD probe.
- Pollution degree: PD3 governs the unsealed construction (IEC 60335-2-6 cl. 29.2
  Addition).

A **transcription error in this repo's own spec** had tabulated Table 17's bounded
ranges (`>250 and ≤400`) as discrete points (`300`, `400`), which set a safety constant
25% too strict. Three separate audits reading three different axes were needed to
surface it.

**The architecture decision** — PR #506 selected the PD2 protected-compartment
architecture; PR #515 aligned the requirements validator to 8.0 mm. All three
enforcement points now agree: validator, `generate_kicad_dru.py`'s
`HV_CREEPAGE_ENFORCED_MM`, and `check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM`.
REQ-SAFE-01 went **123 violations / 86 pairs → 53 / 25** [reported].

That decision cleared U3, U7, C6, K1 and T1. K2/K3 remain because their failure is
against the PD-independent clearance minimum.

**The rotation convention** — KiCad rotates footprint children **clockwise**, R(−θ);
the repo used CCW R(+θ) in 21 call sites, including
`requirements/validators/_copper.py::_rotate`, the function REQ-SAFE-01 uses to compute
copper positions. The wrong sign was **concealing** real clearance hazards on 18
production components.

Verified against `pcbnew` itself **[verified]**: footprint at 37°, pad local offset
(10, 4) mm → actual `(10.393615, -2.823608)`; R(−θ) matches to 6 dp, R(+θ) gives
`(5.579095, 9.212692)`.

It hid because the two conventions coincide at 0°/180° and differ only in which axis
is negated at 90°/270° — and every footprint on this board sits at a multiple of 90°.

---

## 3. Guards now in place

Each mechanises "check the source, not the summary" for one failure class:

| gate | catches |
|---|---|
| `scripts/kicad_pad_rotation_oracle.py` + oracle tests | wrong transform conventions, verified against `pcbnew` |
| `scripts/check_no_raw_rotation_trig.py` | raw rotation trig outside the sanctioned module (18 guarded files) [verified passing] |
| `packages/temper-placer/src/temper_placer/geometry/kicad_transform.py` | the single sanctioned rotation implementation |
| `scripts/check_pad_orientation.py` | intra-footprint copper overlap [verified: fails pre-fix board, passes corrected board and KiCad-authored control] |
| `scripts/check_footprint_drift.py` | source-corrected footprints that never reached the board |
| `scripts/check_copper_net_consistency.py` | designator/net drift between netlist and board |
| `scripts/known_failure_pins.py` | a known-red test silently absorbing a *different* failure |
| `scripts/check_derived_doc_drift.py` | doc claims drifting from `pcb/temper.kicad_pcb` |

The oracle is the load-bearing one. The typed-coordinate-frames plan (`docs/plans/`)
concluded honestly that **types would not have caught the rotation bug** — a sign error
inside a correctly-typed `float → float` function — so it is complementary, not a
substitute.

---

## 4. Open — owner decisions

1. **The sealed enclosure must actually be built.** PD2 / 8.0 mm is legitimate *only*
   for a genuinely sealed electronics compartment. PD3 was determined from the current
   construction: forced-air-vented chassis shared with the PCB, air-permeable coil
   baffle, no sealed compartment, IP20. If the enclosure does not change, 8.0 mm is
   wrong and the board is under-insulated against the standard its own analysis
   identified. The open mechanical question is IGBT heatsinking versus a sealed
   enclosure.
2. **`drc_ceiling.json`** needs a `Ceiling-Approval:` trailer. It is stale on two axes:
   board content, and kicad-cli 10.0.4 → 10.0.5 (CI's container has moved).
3. **The 1.4× double-fault margin** on the ADC bus-sense divider
   (`elec/domain_manifest.yaml` ~line 620): 3×169k + 10k, 949.7 µA against a 1.35 mA
   limit. It passes, and the single-fault requirement holds with real margin, but 1.4×
   is thin and a repeated "3.5×–10×" summary figure was found to be optimistic — it was
   one divider's own span read as a range across crossings. Reconcile before it is
   cited externally.
4. **`tank.c_tank3` placement** — see §1.

---

## 5. Required proof for any board change

The board's segments, vias, arcs and zones store their net as a **bare ordinal index**
into the net table, not a name. Rebuilding or reordering `board.nets` without remapping
by name identity silently repoints copper — measured at **79% of segments and 75% of
vias** on this exact board (`docs/evidence/2026-07-27-post-ovp-resync.md` §1). Swapping
a component or adding a placement both perturb that table.

So the deliverable for a board edit is not "it works", it is:

- **every copper item's net resolved BY NAME, unchanged before/after.** Any change is
  stop-and-report, never repair-in-place.
- before/after counts: footprints, segments, vias, zones, net declarations
- `kicad-cli pcb drc`, **median of N≥5** — this board scatters ~20 on `shorting_items`
  alone, so a single reading cannot gate anything
- REQ-SAFE-01 before/after
- exit codes for `check_copper_net_consistency.py`, `check_footprint_drift.py`,
  `check_pad_orientation.py`, `check_domain_partition.py`, `check_isolation_keepout.py`

Re-baseline any DRC constant this invalidates per the convention in
`test_regression_drc.py`: measured value, date, kicad-cli version, and the board shape
measured against. Never raise a number to make a test pass.

---

## 6. Traps that cost real time here

- **`git stash` is repo-global across worktrees.** With concurrent sessions, a push/pop
  pair is a race — one pop applied and dropped another session's entry. The repo's
  guard blocks `push` but **not** `pop`, so a *failed* push must be a hard stop.
- **Two-dot diffs lie about agent branches.** `git diff origin/main <branch>` renders
  every commit that landed since the branch point as a deletion, which looks identical
  to an agent destroying files. Use `origin/main...<branch>`. This produced three false
  alarms.
- **Cancelled CI jobs render as `fail`** in `gh pr checks`. Check `.conclusion ==
  "cancelled"` via the API. A concurrency cancellation was mistaken for a real failure
  across several turns.
- **Stale compiled extensions produce phantom failures.** Three separate reports of
  "45", "148", and "49" failing tests were all local-environment artifacts that CI did
  not reproduce. A freshness check is cheap and distinguishes them.
- **A long-lived PR stack inverts.** Once its content reaches trunk by another path,
  the branch starts carrying *older* versions of files it introduced — so merging it
  becomes a regression. Three PRs had to be closed for this reason.
- **Agents idle on CI monitors.** Several burned 150k–370k tokens emitting "I'll wait"
  while their work sat uncommitted. Instruct them to report and exit; commit
  incrementally so an interruption costs nothing.
- **Verify falsifier mutations were restored.** One agent left `TEMP: reverted` sabotage
  in five production files, including the REQ-SAFE-01 validator with its docstring still
  documenting the correct behaviour, then reported success.

---

## 7. Standing constraints

- Never resolve a failure with `pytest.importorskip`, `skipif`, `xfail`, deletion, or
  assertion-weakening.
- Never add `continue-on-error`.
- Never loosen a ratchet, cap or allowlist to pass; fix by extraction.
- `pcb/**` and `elec/src/**` are read-only except for a task explicitly scoped to them.
- Do not move or delete anything under `docs/brainstorms/`, `docs/plans/`,
  `docs/solutions/` — a deliberate knowledge wiki.
- Re-date superseded documents rather than deleting them; the history of how state moved
  is the point.
