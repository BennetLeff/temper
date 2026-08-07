<!-- provenance: commit=c3305915 (worktree-agent-aaaac157441fa01a8, fast-forward merge of
     worktree-agent-a79e198a124568852 onto origin/main), dirty=false except this file.
     pcb/temper.kicad_pcb NOT modified -- all placement experiments below ran against
     an in-memory / scratch copy of the board's geometry, never the committed file. -->

# OCP-02 Second CT — Placement Feasibility Study

**Date:** 2026-08-07
**Question this answers:** `OCP02_DECISION_BRIEF.md`'s one open item —
"whether a second 23×30mm CT footprint fits the board without a routing
regression."
**This is not a placement change.** `pcb/temper.kicad_pcb` was not touched.
Every geometric experiment below ran against data read from the committed
board, in a throwaway Python/Shapely analysis; nothing was written back.

**Bottom line: fits, but only with a re-place — not a drop-in next to the
circuit's ideal splice point.** Details and the reasoning below.

---

## 1. The footprint envelope, reconciled

The brief cites **23.0 × 30.0 mm**; `STRATEGY.md`'s Rung 1b note cites
**24.86 × 30.5 mm**. Both are correct, for different things — read directly
from `pcb/libs/temper.pretty/CST3015.kicad_mod`:

| Feature | Layer | Size | What it is |
|---|---|---|---|
| Body outline | `F.Fab` | 23.0 × 30.0 mm | The physical Coilcraft part's max body, per the datasheet |
| **Courtyard** | `F.CrtYd` | **24.86 × 30.5 mm** | Body **+ pad extent in X** (primary pads span ±12.18mm, wider than the ±11.5mm body) **+ 0.25mm placement margin on all sides** |

The footprint file's own comment confirms this exactly: *"Courtyard: body
23.0 x 30.0 and pads (x +/-12.18) plus 0.25mm margin. Body dominates in Y,
pads dominate in X."* — `(fp_rect (start -12.43 -15.25) (end 12.43 15.25)
(layer "F.CrtYd") ...)` is exactly 24.86 × 30.5 mm.

**The courtyard, not the body, is the number that matters for this
question.** DRC's `courtyards_overlap` check and any placement/free-area
reasoning operate on courtyard geometry, not the fab-layer body outline —
and it's confirmed by precedent: `STRATEGY.md`'s Rung 1b entry for the T1
swap already states "courtyard 21.0 × 16.2 → 24.86 × 30.5 mm" for this exact
part. All placement analysis below uses **24.86 × 30.5 mm** (758.2 mm²).

---

## 2. Candidate locations — constrained by circuit, not just area

### 2.1 Where the fault current actually is

The brief derives (§3.1, not re-derived here) that a shoot-through fault's
current path is `dc_bus_plus → Q_high → SW_NODE → Q_low → DC_BUS_RTN`. On
the board, `Q_low` is **U6** (`hb.power_loop.q_low`, TO-247-3, sheet
`hb.power_loop.q_low`, at world position `(100.07, 159.33)`, rotated 180°).
Reading its pads directly from the board:

```
(pad "3" thru_hole oval (at 10.9 0 180) ...)
  (net 5 "DC_BUS_RTN"))
```

Local pad offset `(10.9, 0)` rotated 180° and added to the footprint origin
puts **U6's emitter pad — the actual physical entry point of shoot-through
current into `DC_BUS_RTN` copper — at world coordinates ≈ (89.17, 159.33)**.

This is the correct splice point, confirmed by how the *existing* CT (T1,
OCP-01) is wired: T1's primary pads are on nets `tank-out` / `PWR_RTN`, not
a single shared net — i.e. T1 physically **breaks** the tank-return copper
into two named nets and bridges them with its primary winding. A second CT
must do the same to `DC_BUS_RTN`: split it into (e.g.) a `q_low-emitter` net
local to U6 and the rest of the `DC_BUS_RTN` plane, with the new CT's
primary as the only bridge. That's an `elec/` change (out of scope here,
per the brief), but it fixes *where* the CT has to sit: **physically
adjacent to U6**, not merely "somewhere on the `DC_BUS_RTN` net" — that net
is a large copper pour (its own zone polygon spans roughly the whole board,
`(24.3,25.3)`–`(180.1,105.4)`–`(58.0,252.9)`), and splicing a CT into a pour
anywhere else would sense the wrong current.

### 2.2 What's actually near U6

Reading every footprint's courtyard and reference designator from the board
directly (169 footprints, 127 with a drawn `F.CrtYd` rectangle), the pocket
immediately around U6 is **not empty** — and not just HV:

| Ref | Sheet | Domain | Distance to U6's `DC_BUS_RTN` pad |
|---|---|---|---|
| R67 | `safety.coil_thermal.r_ref_top` | SELV (`+3V3`) | 17.4 mm |
| C15 | `aux_supply.c_out` | SELV | 19.6 mm |
| J1 | `thermal.j_fan` | SELV | 19.6 mm |
| T1 | `ct_sense.ct` | mixed (OCP-01's own isolator) | 20.7 mm |
| R16 | `discharge.r_coil2` | SELV | 23.7 mm |

Domain classification here isn't eyeballed — it's the same
`elec/domain_manifest.yaml` → compiled-netlist mapping the repo's own
`verify_iec60335_compliance` validator produces (§3 below): a component is
SELV (`LV_CONTROL`) if every declared net on it maps to the manifest's SELV
list, HV (`DC_BUS`/`MAINS`) if HV, "mixed" if both (true isolators, like T1
and U7).

A raw courtyard-only free-space search finds a legal, non-overlapping slot
for the new CT within about a millimetre of J1/U6/R67. But that's the wrong
test: J1 and R67 are SELV, and this board's own reinforced-insulation
figure (`MIN_BARRIER_WIDTH_MM = 8.0mm`, `check_isolation_keepout.py`, same
constant `verify_iec60335_compliance` uses as `max_iec_margin_mm`) applies
between any HV-domain footprint and any SELV-domain footprint. A courtyard
sitting 1mm from R67 fails that by 7mm.

### 2.3 Domain-aware search

Re-running the free-space search with the 8.0mm reinforced rule applied
against every SELV-or-mixed component on the board (not just the two
nearest), the closest legal placement moves from "adjacent to U6" out to
**≈44 mm from U6's `DC_BUS_RTN` pad** — centered around `(89, 115)`,
landscape orientation (30.5mm wide × 24.86mm tall), north of the immediate
half-bridge cluster, in the gap between the RTD/safety reference-resistor
field and the T1/J1/discharge-relay group. Nearest SELV neighbor there
(J1) sits 8.6mm away — just clear.

**Relocating the two nearest SELV parts doesn't materially help.**
Re-running the search with R67 and J1 removed from the obstacle set (as if
they'd already been moved elsewhere) only pulls the nearest legal slot in
to ≈41 mm, because C15, R16, T1 itself, and the rest of the RTD/safety
sense-resistor field still ring U6 within the 8mm-plus-courtyard radius.
This is a densely mixed neighborhood by construction — five SELV/mixed
components inside 30mm of U6 — not a two-part obstruction.

---

## 3. Checks run (repo tooling, not eyeballing)

All commands below ran from this worktree against the **committed, unmodified**
board and the freshly-built netlist (`make netlist` was required — no
`elec/build/default.net` existed yet in this worktree; it's gitignored, per
`AGENTS.md`).

**`scripts/check_isolation_keepout.py`** (against `pcb/temper.kicad_pcb` as
committed):

```
Barrier zone NOT FOUND (name='MAINS_SELV_ISOLATION_BARRIER').
FAILED -- 1 violation(s)
```

This is a **pre-existing** condition, not something this study caused: the
board has **zero** keepout zones of any kind today (`grep -c keepout
pcb/temper.kicad_pcb` → 0, and the gate's own report confirms 0 "other
keepout zones present"). The mains↔SELV barrier this gate polices doesn't
physically exist on the board yet — it's tracked separately
(`docs/plans/2026-08-01-001-feat-mains-selv-isolation-barrier-plan.md`,
commit `ee3da42a`'s PD2 architecture selection). This means a second CT's
placement can't today be checked against "is it on the correct side of the
drawn barrier," because there is no drawn barrier — only the domain
*classification* (§2.2–2.3, via the manifest) is currently enforced.

**`scripts/check_domain_partition.py`** (against a fresh `make netlist`
build of the current, OCP-02-less design):

```
Checked 54 declared nets across 2 domains (HV, SELV), 10 declared isolators...
PASSED -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance
chain defects, 0 board-interface contract violations
```

Clean, as expected — OCP-02 isn't instantiated in `elec/` yet, so there's
nothing new for this netlist-level gate to check. Confirms the tooling and
the freshly-built netlist are both usable, and that the current design
starts from a clean isolation baseline.

**`temper_placer.requirements.validators.clearance.verify_iec60335_compliance`**
via `temper_placer.io.real_board.load_real_board_placement` (the same
Rust-backed `req_safe_01_*` clearance/creepage engine
`packages/temper-drc-rs` exports, loaded from its already-built wheel in
the shared `target-shared/wheels/` cache — no fresh `cargo`/`maturin` build
was run, consistent with the disk-pressure guidance in `AGENTS.md`):

```
159/169 components matched and classified. max_iec_margin_mm = 8.0
No clearance/creepage violations.
```

Baseline passes. This run also produced the real per-component domain
classification (HV / SELV / mixed) used for §2.3's search — not a hand-rolled
guess at which parts are SELV.

**What I could *not* run:** `kicad-cli` is not installed in this sandbox (no
root; same class of gap the brief already flagged for `ngspice`), so no real
`kicad-cli pcb drc` (`courtyards_overlap`, `clearance`, `shorting_items`,
etc.) and no router run. §2.3's placement search is therefore my own
Shapely geometry against courtyard rectangles and the real domain map — not
a substitute for `kicad-cli`'s DRC, but built on the same 8.0mm constant and
the same domain classification the repo's real validator computes, not an
invented number.

---

## 4. Routing impact — an estimate, explicitly

Per `docs/evidence/2026-08-07-router-silent-noop-diagnosis.md` (issue
`#871`), the router does not currently complete on this board, so a real
before/after routing comparison for this specific change is **not
obtainable** — stated here rather than fabricated.

Two data points, both from the *committed* board, both estimates:

- **Trace density near the domain-safe candidate site is *below* board
  average.** Counting `(segment ...)` midpoints: board-wide average is
  0.064 segments/mm². The `(89,115)` candidate region measures 0.025
  segments/mm² — less congested than typical. The already-crowded
  T1/U6 cluster measures 0.096 segments/mm² — precedent's own T1 swap
  happened in the *denser* part of this same neighborhood.
- **The new copper run to reach it is the real cost, not the footprint's
  own local area.** Splicing the CT in near U6 means breaking `DC_BUS_RTN`'s
  copper and routing ~44mm of new HV trace/plane-break through exactly the
  denser T1/U6/J1/R16 pocket to reach a domain-safe landing spot — a more
  invasive operation than T1's original swap, which was a same-footprint
  component substitution with no new long HV run.

Extrapolating from the one measured precedent this board has
(`STRATEGY.md` Rung 1b: T1's 3.5×-area swap cost **−1.2pp completion** and
**+22 median shorting-items**, five-run protocol, non-overlapping ranges):
this change is a larger footprint (758 mm² vs. T1's post-swap 758 mm² — same
part, so identical area) landed **further from its electrical anchor point**
and requiring a **new HV copper run** through the most congested part of the
board to get there. I'd estimate a regression **at or somewhat worse than**
the T1 precedent (same ballpark: low-single-digit pp completion loss,
shorting-items increase in the T1 precedent's range or higher) —
**estimate only, not measured**, and it cannot be measured until `#871` is
fixed.

---

## 5. Verdict

**Fits with a re-place — not a drop-in next to U6.**

- A legal, courtyard-clean, 8.0mm-reinforced-clean placement for the second
  `CST3015-100ED` **does exist** on this board (2,255+ valid center points
  found board-wide in the domain-aware search; the board is only ~25%
  courtyard-occupied overall). This is not a "does not fit" result.
- But the *only* legal placements are **displaced ~40–44mm** from the
  circuit's actual splice point (U6's `DC_BUS_RTN` emitter pad), because
  the immediate neighborhood around U6 already carries five SELV/mixed
  components within 30mm, at least one (R67) inside 20mm. Relocating the
  one or two nearest SELV parts doesn't open a closer slot — the whole
  local RTD/safety/aux-supply sense-resistor field would need to move to
  get materially closer, which is a genuine re-placement of a
  multi-component neighborhood, not a nudge.
- The alternative — accept the ~44mm-displaced site — avoids re-placing
  anything, but requires a new HV trace/plane-break run through the
  densest part of the board to physically reach the splice point, which is
  the more invasive of the two costs by the estimate in §4.

**What this means for the brief's recommendation:** the brief's own
conditional applies. §7 of `OCP02_DECISION_BRIEF.md` states: *"If a
placement study shows a second CST3015-100ED does not fit without a
routing regression at least as bad as the one the first one caused, switch
to option B despite its added bias-supply scope."* This study did not find
"does not fit" — it found "fits, but at a real, precedent-scale cost
comparable to or exceeding the one already measured for T1." That's close
enough to the brief's own stated trigger that **the decision is now
genuinely live, not a formality**: Option A (second CT) is still buildable,
but no longer the "zero-friction, already-proven-pattern" case the brief
leaned on — its >4µs timing margin remains the strongest argument in its
favor regardless of placement cost, while Option B's ~21% timing margin
(the tightest of any option, and intrinsic to the AMC1300, not improvable)
is the cost on the other side of that trade. This is a placement-cost vs.
timing-margin tradeoff for a human to weigh, not one this study can resolve
by itself — consistent with the brief's own framing that this remains a
recommendation, not a decision.

---

## 6. Reproducing this analysis

```bash
# Netlist (needed for check_domain_partition.py and the real clearance validator):
cd elec && uv tool run --from 'atopile>=0.2,<0.3' ato --non-interactive build src/main.ato:Top
cd .. && uv run --no-sync python scripts/write_build_stamp.py \
  --artifact elec/build/default.net --source-root elec/src --glob '*.ato'

# Baseline gates (both against the committed, unmodified board):
export PYTHONPATH="$(pwd)/packages/temper-placer/src"
uv run --no-sync python scripts/check_isolation_keepout.py
uv run --no-sync python scripts/check_domain_partition.py

# Real-board IEC60335 clearance validator + domain map (needs the pyo3
# wheels from target-shared/wheels/ -- installed here from the shared cache,
# no fresh cargo/maturin build):
uv pip install /path/to/temper/target-shared/wheels/*.whl
# then: temper_placer.io.real_board.load_real_board_placement(pcb, manifest, netlist)
#       + temper_placer.requirements.validators.clearance.verify_iec60335_compliance(...)
```

The domain-aware courtyard/creepage search in §2.3 is a scratch script, not
a repo artifact — no existing script in this repo does automated
footprint-placement search; building one was out of scope for a feasibility
study. It uses only the repo's own courtyard geometry (parsed directly from
`pcb/temper.kicad_pcb`) and the repo's own domain classification and
`MIN_BARRIER_WIDTH_MM`/`max_iec_margin_mm` = 8.0mm constant, not invented
figures.
