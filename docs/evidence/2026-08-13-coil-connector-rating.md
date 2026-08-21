<!-- provenance: commit=5511e581f50be9f7ef649840b1acb82aa3633f17 (branch
fix/coil-connector-rating, base origin/main @ a3e117347, worktree
/home/bennet/Desktop/temper/.claude/worktrees/fix-coil-connector-rating).
pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
-- UNCHANGED throughout (git status clean against it; every board written
by this work lives in the session scratchpad, never in the repo tree).
pumpkin_engine sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e
source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd, verified via
scripts/verify_pumpkin_engine.py --require exit 0 BEFORE the solve below,
NOT rebuilt. kicad-cli 10.0.5 present but not used -- no DRC/route was run,
Sec 5 states why. -->

# R30's litz pad is a bare solder termination rated for roughly half the current it carries -- fixed by sourcing the pad diameter, not a part number, via this repo's own IPC-2221B method. Placement re-solves `optimal` on the wider part with the isolation barrier, tank creepage, and heatsink co-location all intact.

**Verdict, up front.**

1. **This is a solder termination, not a purchased connector.** `docs/hardware/TANK_COIL_SPECIFICATION.md` requirement #10 (line 46) specifies "two leads, tinned, for ... through-hole pads (`LitzPad_15A`)"; `docs/hardware/BOM.md:115`'s `L_TANK` line says "2 leads to `LitzPad_15A` pads." `docs/CONNECTORS_AND_WIRING.md:14`'s `J_COIL` M4-screw-terminal entry (Keystone 7761, 30A) is a stale v1.0 document (dated 2025-12-17) with **no corresponding component anywhere in `elec/src/*.ato` or `docs/hardware/BOM.md`** -- confirmed by grep, not asserted. The as-built design solders the coil's litz leads directly into R30's two PTH pads. So the fix is pad geometry and copper cross-section, per the task brief's own instruction for this case, not a manufacturer part number.
2. **The real currents, stated separately and sourced, because the pad's own audit conflated them.** Continuous/RMS at the 1800W point: **20.7A rms** (this repo's ngspice harness) to **22.5A rms** (independent first-harmonic solve) -- `docs/hardware/TANK_COIL_SPECIFICATION.md:217-218`, mirrored at `elec/src/modules.ato:585-589`. Peak: **28.7-31.9A** -- `modules.ato:588-591`. The coil's own imposed continuous design rating, `inductor_conn.current_rating = 25A` (`modules.ato:620`; `TANK_COIL_SPECIFICATION.md:42` req #6, "25A rms at 40kHz, ΔT≤60K"), carries **1.11x margin** over the worse of the two measured RMS figures (25/22.5), matching the ratio `modules.ato:589`'s comment already states.
3. **The pad's declared rating was compared to the wrong current basis, and the corrected comparison still fails, by a smaller but real margin.** `docs/hardware/PART_STRESS_AUDIT.md:127-129` compares the **peak** current (28.7-31.9A) to the pad's **15A** rating and calls it "exceeded by ~1.9-2.1x" -- peak-to-continuous, not like-for-like (a PTH pad rating, like a connector rating, is conventionally continuous/RMS; nothing in this repo states a peak basis for it). Compared correctly, continuous-to-continuous: **20.7-22.5A rms actual vs. 15A rms declared -- exceeded by 1.38-1.5x.** Smaller than the audit's headline ratio, and still a real, unresolved shortfall before this change. Sec 1.
4. **`HighVoltageConstraints.i_max = 25A` is a peak-current design budget for the whole HighVoltage domain, not a component rating and not the coil's rating.** It floors the current rating of `q_high`/`q_low` (`modules.ato:88,90`), the gate driver (`modules.ato:176`), the fuse (`modules.ato:663`), and the CMC (`modules.ato:748`), and is asserted directly against `Top.i_peak_max = 25A` at `main.ato:60` -- both are peak-basis quantities (`constraints.ato:34`'s comment: "340V DC max, **25A peak**"). Compared peak-to-peak, the **real** conflict surfaces: the tank's own 28.7-31.9A peak **exceeds the design's own declared 25A peak ceiling by 15-28%**. This is not new (`modules.ato:585-596` already states it, `UNRESOLVED AND RECORDED, NOT FIXED HERE`) and this document does not fix it either -- **`i_max` is not touched**, per instruction. If the design current genuinely exceeds the design's own ceiling, that is a specification conflict the ceiling itself may need to answer, not the connector; it is recorded here, not resolved.
5. **What was changed:** `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`'s pad diameter, sourced (not guessed) via this repo's own IPC-2221B method against the coil's 25A rms design current, and `elec/src/footprints.ato`'s `pad.current_rating`/`annular_ring` to match. `pcb/temper.kicad_pcb` is untouched, as instructed. Sec 3.
6. **Placement re-solved, not hand-edited, on the wider part.** A real Pumpkin CP-SAT solve against a scratch board copy carrying the new R30 geometry (bounds measured at **40.0×15.0mm**, up from 26.0×8.0mm) returns `optimal` with the mains↔SELV isolation barrier (all 8 isolators, **none relaxed**), the 180-pair tank-node creepage constraint (**0 violations**), and #1082's heatsink co-location (**satisfied**) all composed together. Write-back with `board_origin=board.origin` and containment both pass. Sec 4.
7. **Routing/DRC on the wider part was not attempted.** `temper_orchestration.RouterPipeline` is absent from the installed extension in this environment -- the same pre-existing, environment-level defect `docs/evidence/2026-08-12-tank-creepage-geometry.md` §8.1 hit and worked around with a private out-of-tree build. That workaround was not repeated here; Sec 5 states the scope boundary plainly rather than silently skip it.

---

## 1. The real currents, and what the pad's own comparison got wrong

### 1.1 Continuous / RMS

| Basis | Value | Source |
|---|---:|---|
| ngspice harness, 1800W operating point | **20.7A rms** | `docs/hardware/TANK_COIL_SPECIFICATION.md:217` |
| Independent first-harmonic solve | **22.5A rms** | `docs/hardware/TANK_COIL_SPECIFICATION.md:218`, `docs/evidence/2026-07-28-coil-selection-research.md` §4.2 |
| Coil's own imposed continuous design rating | **25A rms** | `modules.ato:620` (`inductor_conn.current_rating`); `TANK_COIL_SPECIFICATION.md:42` req #6 ("25A rms at 40kHz, ΔT ≤ 60K") |

`modules.ato:585-589` states the 25A figure is "an RMS THERMAL requirement this design imposes, not a value read from any part," derived to carry **~1.11x margin** over the worse (higher) of the two measured RMS figures, 22.5A. This is the design's own chosen safety factor -- restated, not re-derived, here.

### 1.2 Peak

| Basis | Value | Source |
|---|---:|---|
| Both the previous 150µH model and the current 88µH model | **28.7-31.9A peak** | `modules.ato:588-591` |
| Same figure, cross-referenced | 28.7-31.9A | `docs/hardware/PART_STRESS_AUDIT.md:127` |

### 1.3 Comparing like with like

`PART_STRESS_AUDIT.md` §1.3 ("Resonant-tank coil: peak current vs. its own pad rating," lines 122-133) runs the comparison **peak vs. the pad's declared rating**:

> "Rating `current_rating = 25A` (imposed thermal requirement, not a datasheet figure); footprint `LitzPad_15A` -- **15 A** by its own name ... Applied **28.7-31.9 A peak** ... Margin ... Negative against both figures: 15A pad rating exceeded by ~1.9-2.1x"

Nothing in `elec/src`, `footprints.ato`, or the footprint's own `descr` ever states the 15A figure on a **peak** basis; PTH pad current ratings, like connector ratings, are conventionally continuous/RMS (this is also the basis `TRACE_WIDTH_CALCULATIONS.md`'s IPC-2221B method uses throughout -- an I²R/thermal-soak calculation, not an instantaneous one). Comparing continuous to continuous instead:

**20.7-22.5A rms actual vs. 15A rms declared → exceeded by 1.38-1.5x**, not 1.9-2.1x. A real, unresolved shortfall either way, but a materially different (smaller) one, and the one that actually answers "is this pad rated for the current it carries as a continuous-duty part." The audit's 1.9-2.1x figure is real too, but it is answering a different question (peak vs. a continuous rating), and conflating the two is exactly the trap the task brief named.

### 1.4 What `i_max` governs

`elec/src/constraints.ato:6-8` declares `HighVoltageConstraints.i_max = 25A`; the nested `Constraints.HighVoltage` netclass block (`constraints.ato:29-36`) restates the same 25A with the comment **"340V DC max, 25A peak"** -- i.e. this constant is declared, in the source, as a peak-basis quantity. `main.ato:44` instantiates it (`constraints = new HighVoltageConstraints`) and `main.ato:51,60` assert `i_peak_max <= constraints.i_max`, where `i_peak_max = 25A` is itself named as a peak system quantity. `i_max` also floors the *declared ratings* of several other HV-domain components -- `q_high`/`q_low` (`modules.ato:88,90`), the gate driver (`modules.ato:176`), the fuse (`modules.ato:663`), the CMC (`modules.ato:748`) -- all via `assert X.current_rating >= constraints.i_max`.

**So `i_max` is neither a purchased-component rating nor specifically the coil's rating. It is a peak-current design budget for the entire HighVoltage domain**, used as (a) the ceiling `Top.i_peak_max` must clear and (b) the floor every other HV-domain component's own rating must clear. Compared on its own (peak) basis against the tank's real peak current: **28.7-31.9A actual vs. 25A budget -- the design's own peak ceiling is exceeded by 15-28%.** This is the genuine, already-recorded conflict (`modules.ato:585-596`, `UNRESOLVED AND RECORDED, NOT FIXED HERE`) -- and per the task's explicit instruction, `i_max` is **not** changed here to make it go away. It is restated, with its correct comparison basis, not resolved.

---

## 2. What the part physically is

`TANK_COIL_SPECIFICATION.md` requirement #10 (line 46): *"Terminations: Two leads, tinned, for 2.5 mm through-hole pads (`LitzPad_15A`), ≥ 150 mm free length"* -- verified by visual inspection, not a mating-connector spec. `docs/hardware/BOM.md:115`'s `L_TANK` line: *"1 | Flat spiral, ferrite-backed, OD ≤ 200mm, **2 leads to `LitzPad_15A` pads**"*. The footprint's own `descr` (`pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`, pre-existing text) already calls the pads *"bare litz-wire terminations that must stay uncoated to be soldered to."*

`docs/CONNECTORS_AND_WIRING.md:14` lists a `J_COIL` "M4 Screw Terminal," Keystone 7761, 30A rating -- but:

```
$ grep -rn "J_COIL\|Keystone 7761" elec/src/*.ato docs/hardware/BOM.md
(no matches)
```

That document is dated 2025-12-17 (v1.0), predates the as-built `elec/src` design (R30/`LitzPad_15A` as an `Inductor` component, `modules.ato:598-623`), and has no corresponding component anywhere the design is actually enforced. It is a stale early-spec artifact, the same class of trap this repo's own evidence trail has hit before (`docs/hardware/PART_STRESS_AUDIT.md`, `TANK_COIL_SPECIFICATION.md` are both explicit about superseding earlier, unenforced documents). **Confirmed: this is a bare solder/lug PTH termination, not a purchased connector.** Per the task brief, the fix is pad geometry and copper cross-section.

---

## 3. The fix: pad geometry, sourced via IPC-2221B, not a part number

### 3.1 Design current for sizing

Sized to `inductor_conn.current_rating = 25A` rms (`modules.ato:620`) -- the coil's own imposed continuous-thermal design figure (`TANK_COIL_SPECIFICATION.md` req #6), not the lower measured operating figures, so the pad fix carries the same ~1.11x margin over measured current the rest of the design already relies on, rather than introducing a fourth, independent current number.

### 3.2 IPC-2221B, applied

`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §2 (external layer):

```
I = k × ΔT^0.44 × A^0.725,  k = 0.048 (external)
```

Parameters, all cited from the same document: **2oz/70µm outer copper** (§1), **40°C rise** (§3.1/§3.3/§4's "HighVoltage"/"Resonant Tank Connection" rows -- the established allowance for this exact net class). Solving for the required cross-sectional area at I = 25A:

```
A = (25 / (0.048 × 40^0.44))^(1/0.725) = (25 / 0.24330)^1.37931 = 595.5 mils² (0.384 mm²)
W = A / (2oz thickness, 2.74 mils) = 217.3 mils = 5.52mm
```

Applied as the **minimum radial annular-ring width** (hole wall to pad edge) -- an explicitly conservative translation of a straight-trace formula onto a round PTH pad (it ignores the extra conducting cross-section a round pad's full 360° spread provides over a linear trace of the same width, so this is a floor, not a fitted answer). Rounded up to **6.0mm** for fabrication margin (~9% above the 5.52mm computed minimum).

**Drill held at 3.0mm** -- litz-bundle physical fit, not re-examined by this pass; this is not the current-carrying bottleneck the fix targets, and the repo has no data connecting it to bundle size beyond the existing hand-built figure.

### 3.3 New geometry

```
New pad diameter = 3.0mm drill + 2 × 6.0mm ring = 15.0mm   (was 8.0mm)
New pitch         = 15.0mm diameter + 10.0mm PD3/Table 18 creepage = 25.0mm   (was 18.0mm)
```

The pitch formula (`diameter + 10.0mm`) is unchanged from PR #1109's derivation (IEC 60335-1 Table 18, functional insulation, band >500-800V, material group IIIa/IIIb, Pollution Degree 3 -- `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`'s pre-existing `descr`) -- widening the diameter and keeping the coupling explicit is exactly the maintenance step that `descr` already flagged as owed: *"if the diameter is later sourced at anything other than 8.0mm the pitch must move with it, or the 10.0mm creepage is silently lost."*

`pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`'s `descr` preserves every prior sentence verbatim (the 2026-07-29 pitch-overlap fix, the 2026-08-12 PD2→PD3 re-derivation, both still-open caveats) and appends the new derivation above, plus an explicit note on what remains open: **the pad diameter is now a computed, cited figure, but it is still not a part-specific manufacturer datasheet number** -- it is this repo's own trace-width method applied to a PTH annulus by engineering judgment. Flagged for human visual cross-check before fabrication, same as before; caveat (2) from the 2026-08-12 revision is only **partially** closed.

`elec/src/footprints.ato`'s `LitzPad_15A` module: `pad.current_rating` 15A → **25A** (matching `inductor_conn.current_rating`), `pad.annular_ring` 1.5mm → **6.0mm**. The module/footprint **name is kept unchanged** on purpose -- renaming it would desync the atopile source from the `fp-lib-table` reference already baked into R30's footprint instance on `pcb/temper.kicad_pcb` (out of scope here), the same reasoning `modules.ato:598-616` already gives for keeping R30's deliberately-wrong "R" designator prefix. `15A` in the name is now historical, not descriptive; `pad.current_rating` is the field that matters.

**Not addressed, noted rather than silently skipped:** `elec/src/footprints.ato:6`'s `pad.drill_size = 2.5mm` has always disagreed with the `.kicad_mod`'s actual 3.0mm drill (pre-existing drift, unrelated to current rating, not touched by this change).

**No manufacturer part number was invented or sourced.** This part is, and remains, a bare custom PTH pad, consistent with the coil itself having no orderable MPN (`TANK_COIL_SPECIFICATION.md` §6, `inductor_conn.mpn = "CUSTOM_LITZ_COIL"`, unchanged).

---

## 4. Placement re-solved on the wider part, and it holds

`pcb/temper.kicad_pcb` is explicitly out of scope for this change, so feasibility is established the same way PR #1109's own companion evidence (`docs/evidence/2026-08-12-tank-creepage-geometry.md`) established it: a **scratch copy** of the committed board with R30's footprint instance widened to match the library fix (pad size 8→15mm, pitch 13→25mm — the committed board still carries the pre-#1109 13mm pitch; `pcb/temper.kicad_pcb`'s own R30 was never landed, so this scratch copy starts from that, not from an intermediate 18mm state), fed through the same composed-constraint Pumpkin harness the prior evidence used (`docs/evidence/scripts/2026-08-12-tank-creepage-geometry-run.py`, unmodified).

```
$ .venv/bin/python scripts/verify_pumpkin_engine.py --require
pumpkin_engine identity gate: VERIFIED -- sha256=7ff153f4… source_commit=5bbf650d47…   (exit 0)

$ PYTHONPATH=packages/temper-placer/src .venv/bin/python \
    docs/evidence/scripts/2026-08-12-tank-creepage-geometry-run.py \
    --board <scratch>/widened_r30.kicad_pcb --rot 1 --relax '' --margin-mm 10.0 \
    --timeout-ms 120000 --out solved.json

[board] 152x234mm, 169 components, tau=0.4mm
[board] R30 bounds = (40.0, 15.0) mm
[tank] intra-footprint self-pairs (NOT coverable by placement): ['C25', 'C26', 'C27', 'R30']
[tank] 180 pairs at margin=10.0mm (180 wire constraints emitted)
[base] 9714 netclass + 6282 courtyard = 15996
[barrier] corridor Y [113.0, 121.0] mm | hv_only=43 selv_only=106 isolators=8 unclassified=12
[barrier] isolators: ['C6', 'K1', 'K2', 'K3', 'PS1', 'T1', 'U3', 'U7']  relaxed: NONE

=== barrier(173) + tank_creepage(180) + heatsink(4, common rot=1) ===
    -> status=optimal wall=11.18s solver=11032.96ms
       C25: centre=(129.81, 63.30)mm rot=2 (180deg)
       C26: centre=(69.86, 12.00)mm rot=2 (180deg)
       C27: centre=(83.60, 45.45)mm rot=3 (270deg)
       R30: centre=(58.22, 49.55)mm rot=1 (90deg)
       U5: centre=(108.71, 8.70)mm rot=1 (90deg)
       U6: centre=(108.07, 93.42)mm rot=1 (90deg)
       tank-creepage post-check: all 180 pairs SATISFIED (>= 10.0mm)
       heatsink post-check: shared-heatsink requirement SATISFIED
```

R30's bounding box grew from 26.0×8.0mm (PR #1109's 18mm-pitch/8mm-pad geometry) to **40.0×15.0mm** -- confirms the geometry math in Sec 3.3 exactly (pitch 25 + pad radius 7.5×2 = 40; pad diameter 15). **`optimal`, all 8 isolators unrelaxed, all 180 tank-creepage pairs satisfied, heatsink requirement satisfied.** Solve time (11.2s) sits between #1089's 168-pair/26mm-R30 baseline (1.3s) and #1109's own 180-pair/26mm-R30 composition run (37-46s) -- consistent with a larger rigid obstacle costing solve time, not feasibility, the same pattern #1109 recorded.

**Write-back and containment**, per instruction:

```
board.origin = (20, 20)
write_placements_to_pcb(..., components=netlist.components, board_origin=board.origin)
write result: components_updated=169, components_skipped=0, warnings=[]

$ .venv/bin/python scripts/check_board_containment.py --board <scratch>/placed.kicad_pcb
outline (Edge.Cuts) bounds: (20.00, 20.00) - (172.00, 254.00) mm
checked: 169 footprints, 527 pads
Board containment: PASS -- all copper inside the board outline
```

**Placement stays feasible with the wider part.** The isolation barrier (PD2/8.0mm, all 8 isolators), the 180-pair PD3 tank-node creepage constraint, and #1082's heatsink co-location all compose successfully over the new R30 geometry.

---

## 5. What was not attempted, and why

**Routing and DRC on the widened board were not run.** `docs/evidence/2026-08-12-tank-creepage-geometry.md` §8.1 documents that `temper_orchestration` in this environment does not export `RouterPipeline`, and worked around it with a private, out-of-tree `cargo build --release` of the orchestration extension. Reconfirmed here, same symptom:

```
$ python3 -c "import temper_orchestration; print(hasattr(temper_orchestration, 'RouterPipeline'))"
False
```

That workaround was not repeated for this change: it is a pre-existing environment defect unrelated to the pad-geometry fix, and PR #1109's own companion document already measured, on the 26.0×8.0mm R30, that routing re-creates a pad-to-track creepage violation regardless of the placement-level fix (its §3, the "4.87mm approach" finding) -- i.e. routing-stage verification is a known, separately-scoped unit of work on this exact net, not something this pass would newly resolve even if run. Placement feasibility (the specific ask: "confirm the PD2/8.0mm isolation barrier ... and #1082's heatsink co-location still hold") is answered in Sec 4 by a real solver run, not by omission.

**`pcb/temper.kicad_pcb`'s own R30 instance is unchanged** -- it still carries the pre-#1109 8.0mm-pad/13.0mm-pitch geometry (PR #1109 fixed the library but never landed the board either; see that PR's commit message, "No board is landed here"). This change compounds that gap rather than closing it: the library now specifies 15.0mm/25.0mm, two revisions ahead of what is physically on the committed board. Landing either revision onto `pcb/temper.kicad_pcb` is a separate, explicitly out-of-scope step for this task.

**A pre-existing, unrelated test failure was reconfirmed, not caused by this change:** `test_tank_creepage.py::TestGroupMembership::test_pair_count_matches_measured_board` asserts 168 pairs, measures 180 -- the same drift `docs/evidence/2026-08-12-tank-creepage-geometry.md` §8.2 already recorded (a netclass-sync widening of the `HighVoltage` population after #1089 pinned the 168 figure, unrelated to R30).

---

## 6. Files

* Footprint fix: `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`
* Source-of-truth field update: `elec/src/footprints.ato`
* This document: `docs/evidence/2026-08-13-coil-connector-rating.md`
* Carried forward, not re-derived: `docs/hardware/TANK_COIL_SPECIFICATION.md`, `docs/hardware/PART_STRESS_AUDIT.md` §1.3, `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §2, `docs/evidence/2026-08-12-tank-creepage-placement.md` (#1089's box-vs-copper boundary), `docs/evidence/2026-08-12-tank-creepage-geometry.md` (#1109's pitch derivation and composition harness, reused verbatim here)
* **Not modified:** `pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`, `power_pcb_dataset/drc_ceiling.json`, `elec/src/constraints.ato`, `elec/src/main.ato` (no current figure, including `i_max`, was changed)
