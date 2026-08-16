<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 (origin/fix/board-schematic-resync) dirty=false. Worktree: own git worktree (`investigate/cst3015-reinforced-isolation`), never the main checkout. Extensions rebuilt in an isolated `.venv` this session (`make venv-isolate` then `make extensions`), `scripts/check_stale_extensions.py` reports 10/10 fresh, AND every extension used below was confirmed to actually import from that fresh build before any measurement was taken (freshness alone is not sufficient -- see AGENTS.md). No `pcb/temper.kicad_pcb`, footprint, DRU threshold, or clearance/creepage value was edited. `pcb/temper.kicad_dru` was regenerated from the unmodified `scripts/generate_kicad_dru.py` purely to run a read-only `kicad-cli` DRC cross-check; that file is `.gitignore`d and was never committed. -->

# CST3015 cannot meet this board's own 12.6mm PD3 reinforced-creepage requirement, in this footprint or (per this repo's own prior part search) in any drop-in replacement at the same ratio/current class — a part-selection defect affecting both T1 and T2

## Verdict, up front

**Non-compliant, part-selection defect.** Both `T1` (`ct_sense.ct`, OCP-01)
and `T2` (`safety.ocp2.ct`, OCP-02) are `temper:CST3015` — Coilcraft
`CST3015-100ED`. Their true intrinsic primary-to-secondary PCB separation,
measured authoritatively (Sec. 1) with this repo's own canonical,
rotation-aware, shape-exact pad-geometry kernels, is **9.100mm** for both
instances — **3.500mm short** of the **12.6mm PD3 reinforced** requirement
this repo has determined governs (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:174,183`,
per `docs/evidence/2026-08-12-pollution-degree-resolution.md`). This is not
a footprint-drawing defect: the part's own physical terminal geometry
leaves at most ~1mm of theoretical shrink headroom (Sec. 3.2), nowhere near
3.5mm, and this repo's own prior exhaustive part search
(`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`) already found
no 1:100-ratio, ≥50A-sensed current-sense transformer, from Coilcraft's own
catalog or any other manufacturer, with better PCB creepage than the
incumbent CST3015 — it already appears to be the best-in-class part on
this specific axis, at this ratio/current class. There is also no
certification credit available to substitute for the PCB measurement
(Sec. 2): the CST3015's own datasheet 5000Vrms/≥8mm creepage figures are
design/test specifications only, carrying **no third-party agency
recognition** (`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:87`) — and
even a genuinely agency-certified isolator would not get such a
substitution under this repo's own prior, primary-source standards reading
(Sec. 2.2). **Both T1 and T2 need a different part or a different sensing
mechanism; this is not resolvable by re-placing or re-routing either one.**

Separately, the DRU currently enforces 8.0mm (PD2) everywhere a reinforced
creepage constraint is emitted, not the 12.6mm PD3 figure this repo has
already determined governs (Sec. 4). That gap is real and board-wide, but
it is **not what makes CST3015 non-compliant** — 9.100mm already clears
8.0mm with margin (confirmed by a live `kicad-cli` DRC run, Sec. 4) and
already falls short of 12.6mm on its own; fixing the DRU number would not
change this part's verdict either way.

This document does not duplicate PR #1140 (T1's routing-defect finding).
That PR owns the question of whether *routing* around T1 achieves the
9.1mm footprint figure in practice. This document owns a different,
prior question: whether the **part** (both its footprint's PCB geometry
and its datasheet's own certification standing) can reach 12.6mm **at
all**, for either T1 or T2. It cannot.

---

## 0. Environment / method provenance

Per `AGENTS.md` "Rebuilding pyo3/maturin Rust Extensions" and "Worktree
`.venv`": this worktree was branched from `origin/fix/board-schematic-resync`
(`a3fbaff37`, PR #1134's resynced board — not `main`), given its own
isolated `.venv` (`make venv-isolate`, ~85s, after `unset CONDA_PREFIX`),
and every pyo3/maturin crate rebuilt (`make extensions`, all 10 crates
compiled in `release` and installed editable). `scripts/check_stale_extensions.py`
reports:

```
fresh=10 stale=0 missing=0 tool-errors=0
PASSED -- 10/10 extension module(s) fresh.
```

Per the environment note that freshness alone is not sufficient (it
certifies content-hash/mtime freshness, not that the module actually
loads), every module used below was independently confirmed to import
from this fresh build before any measurement:

```
import temper_design_bundle_python
import temper_geometry
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.core.pad_geometry import pad_bounding_radius, pad_pair_distance
from temper_placer.io.real_board import _load_manifest
# imports OK
```

`kicad-cli 10.0.5` (`/home/bennet/.local/bin/kicad-cli`) was used for one
independent cross-check (Sec. 4). `git status --porcelain` was clean and
`git grep -l "^<<<<<<< "` returned nothing throughout.

---

## 1. The true intrinsic primary-to-secondary separation: 9.100mm, authoritatively measured

### 1.1 Why the hand calculation disagreed — reproduced, not guessed at

The task brief reported two conflicting hand-computed figures (7.8mm and
12.6mm) depending on how KiCad's `(at x y 90)` pad rotation was applied to
`(size w h)`. This was reproduced directly, and the exact mechanism is now
known:

`Component.initial_rotation` (the field the project's own parser exposes)
is a **quantized rotation index**, 0-3, meaning 0/90/180/270 degrees — not
a literal degree value. Confirmed directly against the project's own
kernel:

```
>>> import temper_geometry as _tg, math
>>> [(i, math.degrees(_tg.normalize_rotation_py(i))) for i in range(4)]
[(0, 0.0), (1, 90.0), (2, 180.0), (3, 270.0)]
```

`T1` is placed at board rotation index `1` (i.e. 90°: `pcb/temper.kicad_pcb`
line 6364, `(at 53.21 148.91 90)`); `T2` at index `0` (no rotation).
`temper_placer.core.pin_geometry.pin_world_position` — the project's own
documented **canonical** rotation-and-side-aware pad-position function
(flagged as the one to use, not `ParseResult.pads`, by the prior
`docs/evidence/2026-08-08-isolation-barrier-geometry-analysis.md` session,
which found a *different*, already-reported rotation bug in the raw
parser output) — correctly converts this index through
`normalize_rotation_py` when computing each pad's **world position**.

The disagreement the task brief describes arises from computing a pad's
**orientation** (the angle fed into the exact rectangle-distance kernel,
`pad_pair_distance`) by a *different*, uncorrected path — e.g. treating
the raw index `1` as `1 degree` instead of running it through
`normalize_rotation_py` first, while the *position* math (correctly)
already had. This was reproduced exactly, side by side, on the real board
(`measure_cst3015.py`, reproduced in full at the end of this section):

```
=== T1 (board rotation index=1, i.e. 90°) ===
  [WRONG: index-as-literal-degrees for orientation, correct rotation for position]
    pad_pair_distance(pin 1, pin 3) = 12.5427 mm
    pad_pair_distance(pin 1, pin 4) =  7.8119 mm
    pad_pair_distance(pin 2, pin 3) =  7.7839 mm
    pad_pair_distance(pin 2, pin 4) = 12.6052 mm
  [CORRECT: normalize_rotation_py(1) = 90° applied consistently to both]
    pad_pair_distance(pin 1, pin 3) = 12.4933 mm
    pad_pair_distance(pin 1, pin 4) =  9.1000 mm
    pad_pair_distance(pin 2, pin 3) =  9.1000 mm
    pad_pair_distance(pin 2, pin 4) = 12.4933 mm
```

This reproduces both figures the task brief reported (7.8mm and — close
to, at 12.605mm vs. 12.6mm — the other) from the *same* single bug, and
confirms the correct figure is neither: it is **9.100mm**, matching `T2`
(board rotation index=0, where the bug is invisible because index-as-degrees
and normalize-then-degrees agree at 0) exactly:

```
=== T2 (board rotation index=0, i.e. 0°) ===
    pad_pair_distance(pin 1, pin 3) = 12.4933 mm
    pad_pair_distance(pin 1, pin 4) =  9.1000 mm
    pad_pair_distance(pin 2, pin 3) =  9.1000 mm
    pad_pair_distance(pin 2, pin 4) = 12.4933 mm
```

This is exactly what physics requires and what the tooling should show: a
whole-footprint rigid-body rotation cannot change the pairwise distances
between its own pads. That both T1 (90°-rotated) and T2 (0°-rotated) land
on the identical 9.1000mm figure, once rotation is handled correctly, is
itself a consistency proof that the measurement is right — the earlier,
rotation-dependent disagreement was a measurement artifact, not a real
difference between the two placed instances.

### 1.2 Method

`packages/temper-placer/src/temper_placer/core/pad_geometry.py`'s
`pad_pair_distance` is the project's exact (not approximate) Minkowski-sum
copper-to-copper pad distance — the same function the module's own
docstring notes reports a real board pair "at exactly 8.000mm against an
8.000mm REINFORCED creepage requirement" where the polygon-buffer
approximation it replaced would have manufactured a false violation. It is
computed in the `temper-geometry` Rust crate, reproducing GEOS'
`DistanceOp` bit-for-bit, pinned by a differential test suite against the
pre-migration Shapely oracle.

For each of `T1`/`T2` (found by scanning `netlist.components` for
`footprint == "temper:CST3015"`):

1. Parse `pcb/temper.kicad_pcb` via `temper_placer.io.kicad_parser.parse_kicad_pcb`
   (the Rust parse engine).
2. For each pin 1-4, get its world position via `pin_world_position(pin, comp)`.
3. Build each pad's `(width, height, shape, cx, cy, rotation_rad, roundrect_ratio)`
   tuple, with `rotation_rad = normalize_rotation_py(comp.initial_rotation) +
   radians(pin.pad_rotation_deg)` — i.e. the component's quantized placement
   rotation (correctly converted) plus the pad's own local rotation relative
   to the footprint (0° for every pad on this footprint; the raw file's
   apparent per-pad "90" on T1's pads is the *already-baked-in* total, and
   the parser correctly reports it back out as local 0° relative to the
   90°-rotated footprint — confirmed by this exact agreement with T2).
4. Compute `pad_pair_distance` for all 4 primary×secondary pairs
   (`{1,2}×{3,4}`, per `elec/domain_manifest.yaml`'s declared `groups`) and
   take the minimum.

Full script (`measure_cst3015.py`, run via `uv run --no-sync python
measure_cst3015.py` against this worktree's freshly-built extensions):

```python
from pathlib import Path
import math
import temper_geometry as _tg
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.core.pad_geometry import pad_pair_distance

result = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
targets = [c for c in result.netlist.components if "CST3015" in (c.footprint or "")]
PRIMARY, SECONDARY = {"1", "2"}, {"3", "4"}

for comp in targets:
    pins = {p.number: p for p in comp.pins}
    world = {n: pin_world_position(p, comp) for n, p in pins.items()}
    comp_rot_rad = _tg.normalize_rotation_py(comp.initial_rotation or 0)

    def pad_tuple(n):
        p = pins[n]; wx, wy = world[n]
        rot = comp_rot_rad + math.radians(p.pad_rotation_deg or 0.0)
        return (p.width, p.height, p.shape, wx, wy, rot, p.roundrect_ratio or 0.25)

    best = min(
        pad_pair_distance(pad_tuple(a), pad_tuple(b))
        for a in PRIMARY for b in SECONDARY
    )
    print(comp.ref, "min primary<->secondary =", round(best, 4), "mm")
```

Output:

```
T1 min primary<->secondary = 9.1 mm
T2 min primary<->secondary = 9.1 mm
```

### 1.3 Cross-checks (three independent confirmations, all agree)

1. **Footprint-local, rotation-invariant hand check.** From
   `pcb/libs/temper.pretty/CST3015.kicad_mod`'s own unrotated pad
   coordinates (primary pads centred at y=-6.85, half-height 2.4mm;
   secondary pads centred at y=6.95, half-height 2.3mm): inner-edge gap
   = 4.65 - (-4.45) = **9.10mm**. This is rotation-invariant by
   construction (all four pads of one footprint instance rotate together
   as a rigid body), which is exactly why T1 and T2 agree once the
   rotation bug above is fixed.
2. **Prior evidence docs, independent sessions.**
   `docs/evidence/2026-07-28-conformal-coating-pd1.md:66`: "T1 | Coilcraft
   CST3015 | **9.100 mm**"; `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:449`:
   "T1 | Coilcraft CST3015-100ED | 13.823 | **9.100** | 7.000 | +2.100".
3. **Live `kicad-cli 10.0.5` DRC**, run against `pcb/temper.kicad_pcb`
   with a freshly (re)generated, unmodified `pcb/temper.kicad_dru`
   (`scripts/generate_kicad_dru.py`, output gitignored, never committed):
   zero `creepage`-type violations report a T1 or T2 primary↔secondary
   intra-footprint pad pair, consistent with 9.100mm clearing the
   currently-enforced 8.0mm bar (`RULE 4 "HV to LV"`, `HV_CREEPAGE_ENFORCED_MM`)
   with margin. (The 7 T1-adjacent creepage violations DRC does report are
   pad↔track/via violations at 0.23-7.13mm — real, but they are stray
   routing near T1, the class of finding PR #1140 owns, not the
   intra-footprint primary/secondary pair this document measures.)

**This confirms PR #1140's 9.1mm figure was correct.** The hand
verification that produced 7.8mm/12.6mm was not — it mixed a
correctly-converted pad-position rotation with an unconverted
pad-orientation rotation, reproduced exactly in Sec. 1.1.

---

## 2. Certification: no credit available, on this part or in principle for this repo

### 2.1 CST3015 carries no third-party agency recognition

`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:87` (an independent, prior
session that fetched and text-extracted Coilcraft's own `cst3015.pdf`):

> "Coilcraft's own `cst3015.pdf` (fetched, text-extracted) states the
> 5000Vrms/1-minute isolation and ≥8mm creepage/clearance as **design/test
> specifications only** — no UL, CSA, VDE, or other agency recognition
> file is listed anywhere in the datasheet."

Restated at line 104: "**CT1 (Coilcraft CST3015-100ED) carries no agency
safety approval** despite a 5000Vrms/reinforced-insulation spec being
cited in design rationale. If that spec is meant to carry certification
weight, it currently can't." This is unchanged for `T2` — same real MPN,
per `elec/domain_manifest.yaml:400-404`.

**Per the task's hard constraint against inventing a datasheet figure:**
if a certification argument were to be pursued for this part, what would
be needed and is not present is a third-party agency certificate (UL
Recognition, CSA, VDE, ENEC, or CB Scheme) specifically covering
IEC 60335-1 or IEC 60664-1 insulation-coordination requirements (not just
a manufacturer-stated hipot/isolation-voltage test result) — this
document does not have one and does not assert one exists.

### 2.2 Even a genuine certificate would not substitute for the PCB measurement, per this repo's own prior standards reading

This is not this document's own interpretation — it reproduces a finding
this repo already reached, with primary-source text, for the general
question of whether *any* certified component's internal barrier can
stand in for the board's own pad-to-pad creepage path.
`docs/evidence/2026-07-29-relay-60335-1-certification-resolution.md`
(Track B, researching whether a relay's IEC 61810-1 certificate could
substitute for the PCB coil-to-contact spacing measurement):

> "IEC 61810-1:2015 itself, in its own Scope clause, says a relay's own
> certification does not cover appliance-level requirements and must be
> separately assessed against the appliance standard. IEC 60335-1 clause
> 24.1 says the same thing from the other direction, and clause 29 is what
> actually governs... **A relay's IEC 61810-1 certificate, however solid,
> governs only the component's own internal construction. It cannot stand
> in for the PCB pad-to-pad path's own appliance-level creepage
> requirement, because that path is physically outside the relay** — it
> exists on this project's own board, under this project's own control,
> and the component manufacturer's certificate says nothing about it...
> it is not a question of whether 61810-1 'counts' as some fraction of
> 60335-1 — the two clauses are about two different physical paths, and
> both must independently clear their own bar."

That reasoning is component-agnostic (component-standard certificate vs.
appliance-standard PCB path), and this repo's own practice elsewhere is
consistent with it: `U3` (`power_in.zcd_opto`, onsemi H11L1TVM) **does**
carry real third-party certification — "UL recognized File E90700 vol.2,
VDE #102497" (`IEC60335_CRITICAL_COMPONENTS.md`, same table) — and is
still tracked with its PCB creepage measured and compared directly against
the board's own reinforced-insulation figure ("this audit's own re-run of
`test_clearance.py`... measures this crossing (U3, HV-to-SELV) at 8.560mm
against the 10.0mm IEC 60335-1 reinforced-insulation requirement — **a
layout gap, not a certification gap**"), not exempted from it. So even
setting aside that CST3015 has no certificate at all (Sec. 2.1), the
precedent this repo has actually built out for a *certified* isolator
(U3) is to still require the PCB path to clear the board figure on its
own — not to substitute the certificate for it.

**One inconsistent outlier exists and should not be read as a counter-precedent.**
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:203,258-262,393` gives the
UCC21550 gate driver a "Per device spec" allowance ("Minimum 1.0mm
clearance between primary and secondary pins... Per UCC21550 datasheet
Figure 34 layout recommendation") in place of the board's literal
8.0/12.6mm figure. This reads as the same kind of stale, uncorrected
provision §6.4 of the same document explicitly flags and retracts for
conformal coating ("This section previously specified a 'Creepage
Multiplier: x1.5 for coated surfaces.' No such provision exists in
IEC 60335-1 or IEC 60664-3" — corrected 2026-07-30) — §6.3's "Per device
spec" line was never reconciled against the later (2026-07-29), more
rigorously primary-source-grounded Track B finding above, or against how
U3 is actually treated in the same repo. It is not evidence that a
certified barrier substitutes for PCB creepage under this repo's own best
current reading of the standard; if anything, extending it further would
now be applying an already-questionable provision to a part (CST3015)
that does not even meet that provision's own precondition (an actual
agency certificate).

**Net: no certification path closes the 3.5mm gap for CST3015.** Verdict
option "Compliant via component certification" does not apply.

---

## 3. Why this is a part-selection defect, not a footprint-drawing defect

### 3.1 This repo already searched for a better-creepage drop-in and found none

`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` §3 (T1, prior
session, independent of this one) already ran this search directly against
the 12.6mm PD3 bar:

> "Every PCB-trace-primary current-sense transformer found with a 1:100
> ratio and >=50A sensed-current range (Coilcraft's own CST1211, CS4xxx,
> SCS families; TDK's B78419A) has *equal or smaller* primary-secondary
> creepage than the incumbent CST3015-100ED, despite some having higher
> hipot voltage ratings — hipot rating and PCB creepage are not the same
> figure... **Within Coilcraft's own current-sensing lineup, CST3015
> already appears to be the highest-PCB-creepage, 1:100-ratio,
> >=50A-sensed part they sell.**"

Concretely: Coilcraft CST1211 (9mm/8mm, but only 28A sensed — below the
50A OCP trip point); CS4100V-01L (a 1:100 part, but **3mm** creepage per
its own datasheet, and only 35A sensed); TDK B78419A (≥6mm creepage,
≥3.9mm clearance, only 30A sensed). None reach 12.6mm; none even reach
9.1mm; none meet the current-range requirement either. A fundamentally
different mechanism — donut/aperture-primary CTs (Talema ASM, ICE
Components CT07/08/10), where the mains conductor threads through the
core's bore instead of landing on a PCB primary pad — genuinely decouples
PCB creepage from a fixed component figure (that same document's §3.5
worked this out concretely: a single burden-resistor value change, 4.99Ω
→ 49.85Ω, would preserve the 50A trip point at a 1:1000 ratio). But this
is a real mechanism/topology change, not a drop-in part swap, and the
specific parts checked also lack third-party reinforced-insulation
certification — out of scope for a part-selection fix and not itself a
solved recommendation.

### 3.2 The footprint's own margin cannot close 3.5mm even in the extreme

`pcb/libs/temper.pretty/CST3015.kicad_mod`'s own descriptive comment:
primary pads are 9.0×4.8mm landing a **7.36×3.8mm physical terminal**
("0.82mm extension per side" in X). In Y — the axis that sets the
primary-to-secondary gap — the pad (half-height 2.4mm) extends 0.5mm
beyond the terminal's own half-height (1.9mm) on the inner edge. Even in
the extreme, manufacturer-guideline-violating case of drawing the pad at
exactly the physical terminal's own footprint (eliminating the entire
solder-fillet margin, which the CST3015.kicad_mod file itself notes is
built from Coilcraft's own official recommended land pattern, Document
1608-2), that recovers at most ~0.5mm per side. The secondary pad's
terminal size is not independently documented in this repo, so this bound
is stated as an order-of-magnitude check, not a certified ceiling — but
even doubling the primary-side estimate (1.0mm) leaves the part roughly
2.5mm short of 12.6mm, consistent with Sec. 3.1's finding that no
Coilcraft or third-party 1:100/≥50A part beats this footprint's own
creepage. **The gap is dominated by the component's own terminal
placement on its 23×30mm body, not by slack in how the footprint was
drawn.**

### 3.3 Conclusion

Both preconditions for "footprint-fixable" fail: there is no meaningful
unused margin in the current land pattern (3.2), and there is no
alternative part at this ratio/current class with better creepage to draw
a new footprint for (3.1). **Verdict: non-compliant, part-selection
defect — for both T1 and T2, already placed, using the same real MPN.**

---

## 4. The enforced-vs-required DRU gap (reported, not fixed)

`scripts/generate_kicad_dru.py`:

```python
HV_CREEPAGE_PD2_MM = 8.0
HV_CREEPAGE_PD3_MM = 12.6  # fallback if the PD2 enclosure prerequisite fails
...
HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM
```

`docs/evidence/2026-08-12-pollution-degree-resolution.md` (cited by the
task brief) already determined, board-wide, that the PD2 enclosure
prerequisite is unmet ("no `docs/specs/pd2_compartment_evidence.yaml`
exists... `scripts/check_pd2_compartment_evidence.py` fails today...
**PD2 is the repo's selected target, not an earned classification. On the
standard's own condition, PD3 governs the as-built board now.**") — yet
`HV_CREEPAGE_ENFORCED_MM` was not updated to `HV_CREEPAGE_PD3_MM`.

**Scope of this gap, this session:** `HV_CREEPAGE_ENFORCED_MM` feeds the
`(constraint creepage (min ...))` clause in four separate generated rule
blocks — `"AC Mains to LV"`, `"HV to LV"` (the rule that actually
catches the T1/T2 primary↔secondary intra-footprint pair, confirmed via
the live DRC run in Sec. 1.3), `"HighVoltageIsolated to LV"`, and the
`{HV_TANK_CLASS} to LV` rule — i.e. **every reinforced HV↔LV/SELV
creepage boundary the DRU currently checks anywhere on the board**, not
specifically T1/T2. This is a board-wide 4.6mm under-enforcement (8.0mm
enforced vs. 12.6mm required) that would need its own remediation pass,
with board-wide placement consequences — **not changed here**, per the
task's explicit constraint.

**This is not what makes CST3015 non-compliant.** 9.100mm already clears
the current 8.0mm bar (no violation reported, Sec. 1.3) and already falls
3.5mm short of 12.6mm on the correct, PD3-governed figure — raising the
enforced bar to 12.6mm would surface this defect as a hard DRC failure
rather than create it; the underlying part-capability gap exists either
way.

---

## 5. Summary table

| Item | Value | Source |
|---|---:|---|
| T1 measured min primary↔secondary | **9.100mm** | Sec. 1.2, canonical tooling |
| T2 measured min primary↔secondary | **9.100mm** | Sec. 1.2, canonical tooling |
| PD3 reinforced requirement (this repo's own determination) | **12.6mm** | `HIGH_VOLTAGE_CLEARANCE_SPEC.md:174,183` |
| Shortfall | **-3.500mm** (both T1, T2) | derived |
| Currently DRC-enforced bar | 8.0mm (PD2) | `generate_kicad_dru.py`, confirmed by live DRC |
| CST3015 third-party agency certification | **None found** | `IEC60335_CRITICAL_COMPONENTS.md:87,104` |
| Best alternative 1:100/≥50A part found (any manufacturer) | **None better** | `2026-07-30-pd3-part-selection-k1-c6-t1.md` §3 |
| Verdict | **Non-compliant, part-selection defect** | this document |
