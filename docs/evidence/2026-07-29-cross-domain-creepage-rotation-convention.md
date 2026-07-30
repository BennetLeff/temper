# Cross-domain creepage triage: rotation convention resolved, unknowns cut 16→9, 60 pairs classified by remedy

<!-- provenance: commit=916a06a26e300efdaf24ce7f4a9c7b4912c50ddb dirty=false -->

**Date:** 2026-07-29
**Base commit:** `5401a827` / `3cd4fc4c` (branch `feat/pairwise-creepage-tool`,
which added `scripts/measure_cross_domain_creepage.py` and
`docs/evidence/2026-07-29-cross-domain-creepage-pd2-vs-pd3.md`). This
document's own work sits on branch `fix/cross-domain-creepage-triage`,
worktree `wt-creepage-triage`, two commits on top:
`c341286125b8320c611f75515cb5c3e216fba0b5` (tool: resolve rotation
convention) and `916a06a26e300efdaf24ce7f4a9c7b4912c50ddb` (board: add
F.Fab/F.CrtYd body outlines). `dirty=false`: this document's own numbers
come from the tree exactly as committed at `916a06a2`, re-verified after
committing (see §8).
**Scope touched:** `scripts/measure_cross_domain_creepage.py` (rotation
convention only — see §2), `pcb/temper.kicad_pcb` (F.Fab/F.CrtYd graphics
and `descr` documentation only, on 6 of its 168 footprints — see §3), this
document. No copper, no pads, no netclass, no safety constant, no
floorplan change anywhere. `make venv-isolate` run before any measurement.
**Method:** `scripts/measure_cross_domain_creepage.py --min-creepage-mm
8.0`, run against `pcb/temper.kicad_pcb` / `elec/domain_manifest.yaml`, plus
one hand-built minimal `.kicad_pcb` checked against real `kicad-cli 10.0.4
pcb drc` output (§2) and one `make netlist` diff (§3.4). No other tooling.

---

## Headline

- **The rotation-convention question flagged in this repo's own history is
  resolved, with new first-party evidence, not just a literature reread**:
  KiCad places a rotated footprint's pad at `R(-theta)`, not `R(+theta)`.
  `scripts/measure_cross_domain_creepage.py` now defaults to the confirmed
  convention. This also means **`scripts/check_isolation_keepout.py` — the
  gate that actually enforces 8.0mm creepage on `origin/main` today — uses
  the disproven convention** for 90/270°-rotated footprints' pad *positions*
  relative to another footprint. Flagged, not fixed here (out of this
  document's scope).
- **62 → 60** cross-domain violations at 8.0mm after the rotation fix (one
  pair, C22↔L2, was a false positive under the old convention; one
  previously-unremarkable pair, R30↔L2, newly crosses under the corrected
  one).
- **Unknown bucket: 16 → 12 (rotation fix) → 9 (real F.Fab/F.CrtYd added for
  4 of 7 gapped footprints)**. The remaining 9 are all R30 (the tank
  capacitor's HV litz-wire terminal), which this board's own footprint
  library already documents as having no part-specific datasheet — left
  unknown, not guessed, per this task's hard rule.
- **Triage of the 60**: `routing` (slot candidate) 9, `local placement` 21,
  `part` (different package needed) 21, `unresolved` 9 (R30, see above).
  **Zero require floorplan work** by this triage's own methodology — see
  §6 for the important caveat on what that claim does and does not mean.
- **Zero routing fixes applied.** Not because none look promising on paper,
  but because verifying one requires machinery this tool does not have
  (real routed-copper collision checking, creepage-path-around-an-obstacle
  recomputation) — see §7. This is reported as a finding, not softened.

---

## 1. Reproducing this

```bash
uv run --no-sync python scripts/measure_cross_domain_creepage.py \
    --min-creepage-mm 8.0 --limit 100 --json /tmp/result.json
```

All counts below come from this command against commit `916a06a2` (clean
tree). §2's rotation-convention experiment is reproduced by the commands in
that section against a hand-built board, not the real one.

## 2. Rotation convention: resolved by direct KiCad ground truth, not by rereading this repo's own parser

### 2.1 The prior open question

`docs/evidence/2026-07-28-req-safe-01-rederivation.md`'s "Rotation-convention
caveat" found that this repo's own parser/writer
(`temper_placer.io._parse_modules.py`) and `scripts/check_isolation_keepout.py`
both transform a pad's local offset to world position with `R(+theta))`:

```
world = footprint_position + R(+theta) * local_offset
R(+theta): (x cosθ − y sinθ,  x sinθ + y cosθ)
```

...while KiCad's own internal convention was *suspected*, on weak evidence,
to be `R(-theta)`. The two conventions agree everywhere except a pad's
position on a **90°/270°-rotated** footprint relative to *another*
footprint — the exact shape of the ambiguity this pairwise creepage tool
depends on, since most of its violating pairs involve at least one rotated
footprint. `scripts/measure_cross_domain_creepage.py` (the branch this task
started from) responded by computing every violating pair under *both*
conventions and flagging disagreements, rather than picking a side —
correct engineering caution, but not a resolution.

### 2.2 The experiment

A minimal two-footprint `.kicad_pcb` was constructed by hand (not derived
from this repo's own writer, to avoid begging the question):

- Footprint `A1`, placed at `(50, 50)`, **rotated 90°**, with one pad at
  **local offset `(5, 0)`** — deliberately asymmetric, so the two candidate
  world positions are far apart and unambiguous.
  - `R(+theta)` predicts world position `(50, 55)`.
  - `R(-theta)` predicts world position `(50, 45)`.
- Footprint `B1`, placed at `(50, 50)`, unrotated, with **two marker pads**:
  one at local `(0, 5)` (world `(50, 55)`, the `R(+theta)` candidate, net
  `NET_PLUS`) and one at local `(0, -5)` (world `(50, 45)`, the `R(-theta)`
  candidate, net `NET_MINUS`).

This turns "which convention is real" into a direct short/no-short readout
from real KiCad, not an inference: whichever marker A1's pad actually lands
on top of will short to it.

```bash
kicad-cli pcb drc --format json -o drc_out.json rot_test.kicad_pcb
```

Result — `kicad-cli 10.0.4`'s own DRC engine, verbatim:

```json
{
  "description": "Items shorting two nets (nets NET1 and NET_MINUS)",
  "items": [
    {"description": "Pad 1 [NET1] of A1 on F.Cu", "pos": {"x": 50.0, "y": 45.0}},
    {"description": "Pad 2 [NET_MINUS] of B1 on F.Cu", "pos": {"x": 50.0, "y": 45.0}}
  ],
  "severity": "error", "type": "shorting_items"
}
```

KiCad itself reports A1's rotated pad at **`(50.0, 45.0)`** — exactly the
`R(-theta)` prediction — and shorting only against the `R(-theta)` marker.
The `R(+theta)` marker at `(50, 55)` produces no violation at all (10mm
clear). This is first-party, direct evidence from KiCad's own DRC engine,
not a re-reading of this repo's own code.

### 2.3 Corroboration already in this repo

`scripts/check_pad_orientation.py`'s `_rotate()` — independently built and
independently validated to reproduce real `kicad-cli` DRC output on **57 of
57** intra-component `shorting_items` geometric pairs
(`docs/evidence/2026-07-29-intra-component-shorts-root-cause.md`) — already
computes footprint-child position rotation as:

```python
return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))
```

This is `R(-theta)`, bit-for-bit the same formula this section's experiment
confirms. Two independent validations (a fresh hand-built minimal board
checked against live `kicad-cli`, and this repo's own pre-existing,
DRC-matched gate) agree.

### 2.4 What this means for the rest of this repo — flagged, not fixed here

`scripts/check_isolation_keepout.py` (imports `_rotate` implementing
`R(+theta)`) and `temper_placer.io._parse_modules.py` **both still use the
now-disproven convention** for 90°/270°-rotated footprints' pad positions
relative to another footprint. This is a real defect in the
**currently-enforced** 8.0mm gate — for any HV/SELV pad pair involving a
90/270-rotated footprint, `check_isolation_keepout.py` may currently be
consulting the wrong world position. Fixing those two files is **out of
scope for this document** (this task's brief was the measurement tool, not
the gate); flagged here so it is not lost. `pcb/temper.kicad_pcb` has zero
back-side (B.Cu) footprints, so the position-mirroring half of the original
ambiguity never triggers on this board either way (checked at runtime by
the tool, not assumed).

### 2.5 The fix and its measured effect

`scripts/measure_cross_domain_creepage.py` now uses `R(-theta)` as the
PRIMARY convention for **both** pad position and footprint body-outline
construction (the body-outline function had the same latent bug — it also
used `R(+theta)` unconditionally, with no sensitivity check at all, since
the sensitivity machinery only ever covered pad position). `R(+theta)` is
retained only as the `alt` convention for the sensitivity check, now
reframed as a regression signal ("would this verdict flip under the
disproven convention") rather than an open question.

| | 8.0mm violations | body_free | body_crossing | unknown | conv.-sensitive |
|---|---:|---:|---:|---:|---:|
| Before (R(+theta) primary) | 62 | 8 | 38 | 16 | 12 |
| After (R(-theta) primary) | **60** | 8 | 40 | 12 | 10 |

The delta is small in count (62→60) but not in kind: one pair
(C22.2↔L2.2, 1.969mm under the old convention) was a **false positive** —
it does not violate under the confirmed-correct convention at all, and
dropped out of the report entirely, not merely reclassified. One
previously-unremarkable pair (R30.2↔L2.2) newly appears. This is exactly
the failure mode the original tool's sensitivity check existed to catch,
now resolved instead of merely flagged.

## 3. The 16→12→9 unknown pairs

### 3.1 Why 16→12 for free, from the rotation fix alone

Of the 16 `unknown` pairs at the old convention, one (C22↔L2) was the false
positive described in §2.5 and vanished; several others' `crossed_by`
membership changed as body outlines were recomputed correctly, netting
16→12 before any footprint-library work.

### 3.2 The 7 footprints with zero body-outline data

`scripts/measure_cross_domain_creepage.py` classifies a pair `unknown`
only when no crossing body was found on the direct path **and** at least
one endpoint's own footprint carries no usable F.Fab/F.CrtYd geometry.
Seven footprints on this board have **zero graphic items of any kind** —
not just a missing F.Fab, no `fp_line`/`fp_rect`/`fp_circle`/`fp_poly` at
all: `C1`, `C6`, `F1`, `L2`, `R30`, `RT1`, `U27`. All seven are
`(generator stub)` or `(generator hand-built)` footprint instances, the
same class of custom/incompletely-authored footprint this repo's history
has already flagged for other reasons
(`docs/evidence/2026-07-29-intra-component-shorts-root-cause.md`'s cause B).

### 3.3 Resolved (4 of 7)

| ref | part | body added | sourcing |
|---|---|---|---|
| C1, C6 | disc Y2 safety capacitor | 10.0×5.0mm disc, F.Fab rect `[(P−D)/2,(P+D)/2]×[−W/2,W/2]` | D/W/P already declared in this footprint's own name/`descr`. The construction formula itself was **verified, not assumed**: checked against two real KiCad-shipped `Capacitor_THT/C_Disc_*` library instances (`D10.5/W5.0/P5.00` and `D11.0/W5.0/P7.50`) before use — both reproduce their real `.kicad_mod` F.Fab/F.CrtYd rectangles exactly under this formula. |
| U27 | ESP32-S3-WROOM-1 | 18.00×25.50mm F.Fab rect | Already documented in this footprint's own `descr` as sourced from "Espressif ESP32-S3-WROOM-1 datasheet v1.5"; matches this board's own pad extents exactly (`x∈[−9,9]`, `y∈[−12.75,12.75]` — 39 pads checked directly), consistent with castellated edge pads sitting at the module's physical boundary. |
| L2 | Bourns SRP1265A | 13.5×12.5mm F.Fab rect | Bourns datasheet figure (0.531in×0.492in) via DigiKey's SRP1265A-100M product page, 2026-07-29 — a direct fetch of `bourns.com/docs/Product-Datasheets/SRP1265A.pdf` returned HTTP 403 (bot-blocked). **Medium confidence**: distributor-sourced restatement of the datasheet dimension, not the primary PDF. Noted as such in the footprint's own `descr`. |

The construction formula (over-approximating a disc as its bounding
rectangle, or using the datasheet body rectangle directly) matches this
tool's own documented "never under-approximate a body" discipline — see the
tool's module docstring, "Body-free vs body-crossing".

### 3.4 Verified: no copper/pad/netlist change

F.Fab/F.CrtYd are non-electrical documentation layers, but this was
**verified, not assumed**, per this task's explicit requirement:

```
$ sha256sum elec/build/default.net   # BEFORE (pcb/temper.kicad_pcb restored to HEAD)
446891bf6d6ea40983b8fdb5bf3dbbe405e256d613e33f40b0f8f24a3b93efa6

$ sha256sum elec/build/default.net   # AFTER (edited pcb/temper.kicad_pcb restored)
446891bf6d6ea40983b8fdb5bf3dbbe405e256d613e33f40b0f8f24a3b93efa6
```

**Byte-identical.** (`make netlist` builds `elec/build/default.net` from
`elec/src/*.ato` via atopile — it does not read `pcb/` at all, so this was
expected, but it was measured, not assumed, per this task's instruction.)
`scripts/check_pad_orientation.py` still passes on the edited board (168
footprints, 519 pads, 1682 different-net pad pairs, 0 violations) and
`scripts/check_isolation_keepout.py` reports the same single pre-existing
failure (missing barrier keepout zone — unrelated, unchanged by this work).

### 3.5 Unresolved (3 of 7) — flagged, not guessed

| ref | part | why left unknown |
|---|---|---|
| **R30** | LitzPad_15A (custom coil terminal) | Already documented, pre-existing, in this footprint's own `descr`: "low confidence — no part-specific datasheet exists for this custom coil terminal." Nothing new to add; this is the case the task's hard rule exists for. |
| **RT1** | "Ametherm SL32 10015 NTC" per `descr`, footprint named `R_Disc_D15.0mm_W7.0mm_P7.5mm` | **New finding.** The footprint's own declared name does not match its own cited part's real datasheet. Ametherm's own published mechanical spec for SL32-10015 (`ametherm.com/datasheets/sl3210015/`, fetched 2026-07-29) gives disc diameter **≈31.0mm**, disc thickness ≈6.0mm, lead spacing ≈7.8mm — not the declared 15.0mm/7.0mm/7.5mm ("SL32" denotes a 32mm-class disc in Ametherm's own naming scheme; "SL15"/"SL22" would be the 15mm/22mm classes). Drawing a D15mm outline would encode a dimension already proven wrong; drawing a D31mm outline would silently overrule the footprint's own declared identity — a part-selection judgment call outside this task's scope. Left unknown, flagged in the footprint's own `descr` for a human to resolve. |
| **F1** | "Schurter 0034.3128 fuse holder" per `descr`, footprint named `Fuse_Holder_5x20mm` | **New finding.** Schurter part 0034.3128 is the 5×20mm glass fuse **cartridge** itself (confirmed via Schurter's own FST-5×20 datasheet family and DigiKey/RS listings), not any specific holder/clip. Several mechanically-different 5×20mm PCB fuse clips exist from Bel/Eaton/Keystone/Littelfuse/Schurter (all present in KiCad's own `Fuse.pretty` library under different names) — the footprint's own `descr` does not identify which one this represents, so no holder-specific datasheet body dimension can be established. Left unknown, flagged in the footprint's own `descr`. |

RT1 and F1 were not blocking any of the 9 remaining unknown *violations*
(neither appears as an endpoint of any of the 9 — see §3.6), so leaving
them unresolved does not change the headline count; they are reported
because the task asked for all 7, and because the RT1 discrepancy is a
real, independently-worth-flagging finding on its own.

### 3.6 The remaining 9

All nine are R30 pairs — R30 alone, per §3.5:

```
2.612mm  R30.1(tank.c_tank1-p2) <-> R32.1(+3V3)
2.953mm  R30.1(tank.c_tank1-p2) <-> R1.1(+15V)
3.018mm  R30.1(tank.c_tank1-p2) <-> R1.2(power_in.bypass_relay-coil1)
3.666mm  R30.1(tank.c_tank1-p2) <-> R54.1(safety.ovp.comp-inp)
3.794mm  R30.1(tank.c_tank1-p2) <-> U13.3(gnd)
4.616mm  R30.2(tank-out)        <-> R73.1(+3V3)
5.116mm  R30.2(tank-out)        <-> R1.1(+15V)
5.835mm  R30.1(tank.c_tank1-p2) <-> R26.1(PWM_LS)
6.116mm  R30.1(tank.c_tank1-p2) <-> C30.2(gnd)
```

## 4. Triage of all 60 by remedy class

### 4.1 Method

For each of the 60 violations, remedy was assigned by a documented,
mechanical rule, not per-pair judgment (full table in §4.3):

- **`unresolved`** — `body_class == unknown` (R30, §3.6). Cannot classify a
  remedy without knowing whether R30's own body blocks the path.
- **`routing`** — `body_class == body_free`. Nothing physically blocks the
  straight-line path, so a milled isolation slot (a `Edge.Cuts` interior
  cutout — a real, standard PCB technique, not a copper-trace change; this
  board currently has none) is the only remedy that requires moving zero
  parts. See §7 for why none were actually cut in this pass.
- **`part`** — `body_class == body_crossing` **and** the HV and SELV pads
  belong to the **same** footprint (`hv.ref == selv.ref`). This is the
  signature of a component that inherently straddles the domain boundary
  by design (a relay's coil vs. contact pins, an optoisolator's two sides,
  a Y-capacitor's two leads) — its own two pins are the violating pair, so
  no placement change can fix it; only a wider-creepage **package** can.
- **`local placement`** — `body_class == body_crossing`, different
  footprints, and the blocking body is either one of the two endpoints
  themselves or a third-party bystander component. In both cases, moving
  the blocking part (or either endpoint) a few mm removes the crossing —
  in principle; see the important caveat in §6.

### 4.2 Counts

| remedy | count | of 60 |
|---|---:|---:|
| `part` | 21 | 35% |
| `local placement` | 21 | 35% |
| `unresolved` (R30) | 9 | 15% |
| `routing` | 9 | 15% |

### 4.3 Full table (worst gap first)

```
 dist(mm)  remedy            pair (body_class, crosses)
   0.905  routing           C17.2(hb.gate_hs.driver-p2) <-> R32.1(+3V3)  [body_free]
   2.612  unresolved        R30.1(tank.c_tank1-p2) <-> R32.1(+3V3)  [unknown]
   2.953  unresolved        R30.1(tank.c_tank1-p2) <-> R1.1(+15V)  [unknown]
   3.018  unresolved        R30.1(tank.c_tank1-p2) <-> R1.2(power_in.bypass_relay-coil1)  [unknown]
   3.200  part              C6.1(PWR_RTN) <-> C6.2(gnd)  [crosses: C6]
   3.325  routing           C17.1(hb.gate_hs.driver-p1-1) <-> R26.1(PWM_LS)  [body_free]
   3.559  part              K2.1(PWR_RTN) <-> K2.2(discharge.k_dis1-coil1)  [crosses: K2]
   3.559  part              K2.1(PWR_RTN) <-> K2.5(discharge.k_dis1-coil2)  [crosses: K2]
   3.559  part              K3.1(DC_BUS_RTN) <-> K3.2(discharge.k_dis2-coil1)  [crosses: K3]
   3.559  part              K3.1(DC_BUS_RTN) <-> K3.5(discharge.k_dis1-coil2)  [crosses: K3]
   3.666  unresolved        R30.1(tank.c_tank1-p2) <-> R54.1(safety.ovp.comp-inp)  [unknown]
   3.794  unresolved        R30.1(tank.c_tank1-p2) <-> U13.3(gnd)  [unknown]
   3.855  local placement   C17.1(hb.gate_hs.driver-p1-1) <-> R32.1(+3V3)  [crosses: C17]
   3.894  local placement   R12.2(discharge.k_dis1-nc) <-> K3.2(discharge.k_dis2-coil1)  [crosses: K3] [SENS]
   4.019  local placement   R30.1(tank.c_tank1-p2) <-> R54.2(gnd)  [crosses: R54]
   4.023  routing           C17.1(hb.gate_hs.driver-p1-1) <-> U13.3(gnd)  [body_free]
   4.594  routing           C22.2(hb.gate_hs.driver-p2) <-> U15.4(RTD_HW_FAULT)  [body_free]
   4.616  unresolved        R30.2(tank-out) <-> R73.1(+3V3)  [unknown]
   5.116  unresolved        R30.2(tank-out) <-> R1.1(+15V)  [unknown]
   5.293  routing           C22.2(hb.gate_hs.driver-p2) <-> C16.1(+15V)  [body_free]
   5.389  local placement   R30.1(tank.c_tank1-p2) <-> R73.1(+3V3)  [crosses: R73]
   5.406  local placement   R30.2(tank-out) <-> R46.2(gnd)  [crosses: R46]
   5.502  local placement   R30.1(tank.c_tank1-p2) <-> L2.2(+3V3)  [crosses: L2, R1] [SENS]
   5.824  local placement   C22.2(hb.gate_hs.driver-p2) <-> U15.3(gnd)  [crosses: U15]
   5.835  unresolved        R30.1(tank.c_tank1-p2) <-> R26.1(PWM_LS)  [unknown]
   5.843  local placement   C22.1(hb.gate_hs.driver-p1-1) <-> C16.1(+15V)  [crosses: C22]
   6.020  part              U3.2(PWR_RTN) <-> U3.5(gnd)  [crosses: U3]
   6.020  part              U3.1(a) <-> U3.6(+3V3)  [crosses: U3]
   6.056  local placement   C22.1(hb.gate_hs.driver-p1-1) <-> U15.4(RTD_HW_FAULT)  [crosses: C22]
   6.116  unresolved        R30.1(tank.c_tank1-p2) <-> C30.2(gnd)  [unknown]
   6.130  local placement   U6.3(DC_BUS_RTN) <-> R18.2(gnd)  [crosses: R18, U6] [SENS]
   6.275  local placement   C17.2(hb.gate_hs.driver-p2) <-> R26.1(PWM_LS)  [crosses: C17]
   6.295  part              U3.1(a) <-> U3.5(gnd)  [crosses: U3]
   6.432  part              U3.2(PWR_RTN) <-> U3.4(ZCD_ISO)  [crosses: U3]
   6.432  part              U3.2(PWR_RTN) <-> U3.6(+3V3)  [crosses: U3]
   6.515  local placement   C17.2(hb.gate_hs.driver-p2) <-> R73.1(+3V3)  [crosses: R32, R73]
   6.657  routing           C17.1(hb.gate_hs.driver-p1-1) <-> R54.1(safety.ovp.comp-inp)  [body_free] [SENS]
   6.721  routing           C22.2(hb.gate_hs.driver-p2) <-> R77.1(+3V3)  [body_free]
   6.742  local placement   C22.2(hb.gate_hs.driver-p2) <-> C12.1(+3V3)  [crosses: C12] [SENS]
   6.744  local placement   C17.2(hb.gate_hs.driver-p2) <-> U13.3(gnd)  [crosses: C17]
   6.809  local placement   C22.2(hb.gate_hs.driver-p2) <-> C16.2(gnd)  [crosses: C16]
   6.843  local placement   C22.2(hb.gate_hs.driver-p2) <-> C12.2(gnd)  [crosses: C12] [SENS]
   7.047  local placement   C22.1(hb.gate_hs.driver-p1-1) <-> U15.3(gnd)  [crosses: C22, U15]
   7.250  part              U7.14(hb.gate_hs.driver-p2) <-> U7.3(+3V3)  [crosses: U7]
   7.250  part              U7.9(DC_BUS_RTN) <-> U7.8(+3V3)  [crosses: U7]
   7.251  local placement   C22.1(hb.gate_hs.driver-p1-1) <-> C16.2(gnd)  [crosses: C16, C22]
   7.312  part              U7.14(hb.gate_hs.driver-p2) <-> U7.4(gnd)  [crosses: U7]
   7.312  part              U7.11(+15V_LS) <-> U7.5(SHUTDOWN)  [crosses: U7]
   7.312  part              U7.15(GATE_HS) <-> U7.3(+3V3)  [crosses: U7]
   7.347  part              U3.1(a) <-> U3.4(ZCD_ISO)  [crosses: U3]
   7.575  part              U7.14(hb.gate_hs.driver-p2) <-> U7.5(SHUTDOWN)  [crosses: U7]
   7.575  part              U7.11(+15V_LS) <-> U7.4(gnd)  [crosses: U7]
   7.575  part              U7.15(GATE_HS) <-> U7.4(gnd)  [crosses: U7]
   7.575  part              U7.11(+15V_LS) <-> U7.8(+3V3)  [crosses: U7]
   7.575  part              U7.16(hb.gate_hs.driver-p1-1) <-> U7.3(+3V3)  [crosses: U7]
   7.599  routing           C22.2(hb.gate_hs.driver-p2) <-> C37.1(+3V3)  [body_free] [SENS]
   7.714  local placement   F1.2(w1_1) <-> R70.1(+3V3)  [crosses: R70] [SENS]
   7.785  local placement   C22.1(hb.gate_hs.driver-p1-1) <-> R77.1(+3V3)  [crosses: C22]
   7.850  routing           T1.1(tank-out) <-> U27.38(V_BUS_SENSE)  [body_free] [SENS]
   7.993  local placement   R30.2(tank-out) <-> L2.2(+3V3)  [crosses: L2] [SENS]
```

`[SENS]` = convention-sensitive (§2.5) — this pair's PASS/FAIL verdict
would differ under the disproven R(+theta) convention. All 10 are already
below 8.0mm under the confirmed-correct convention this report uses; the
flag means "closer to the resolution boundary, worth a second look," not
"uncertain which side of 8.0mm it's on."

### 4.4 Per-component breakdown

Sorted by worst gap. A component's "pairs" count includes every violation
it participates in either as an endpoint or as the crossed/blocking body.

```
component  worst(mm)  pairs  remedy breakdown
C17            0.905      8  routing=4, local placement=4
R32            0.905      4  local placement=2, routing=1, unresolved=1
R30            2.612     14  unresolved=9, local placement=5
R1             2.953      4  unresolved=3, local placement=1
C6             3.200      1  part=1
R26            3.325      3  routing=1, unresolved=1, local placement=1
K2             3.559      2  part=2
K3             3.559      3  part=2, local placement=1
R54            3.666      3  unresolved=1, local placement=1, routing=1
U13            3.794      3  unresolved=1, routing=1, local placement=1
R12            3.894      1  local placement=1
U15            4.594      4  local placement=3, routing=1
C22            4.594     13  local placement=9, routing=4
R73            4.616      3  local placement=2, unresolved=1
C16            5.293      4  local placement=3, routing=1
R46            5.406      1  local placement=1
L2             5.502      2  local placement=2
U3             6.020      6  part=6
C30            6.116      1  unresolved=1
U6             6.130      1  local placement=1
R18            6.130      1  local placement=1
R77            6.721      2  routing=1, local placement=1
C12            6.742      2  local placement=2
U7             7.250     10  part=10
C37            7.599      1  routing=1
R70            7.714      1  local placement=1
F1             7.714      1  local placement=1
T1             7.850      1  routing=1
U27            7.850      1  routing=1
```

**Structure**: a handful of components account for most of the pairs.
`R30` (14, unresolved-dominated), `U7` (10, all `part` — a declared
isolator), `C22`/`C17` (13/8, mostly the gate-driver bootstrap network's
own bootstrap-cap bystander proximity to nearby SELV signal pins), and
`U3` (6, another declared isolator, all `part`). Fixing R30's data gap,
swapping U7/U3/K2/K3/C6 for wider-creepage packages, and giving the
bootstrap network (C17/C22) a few mm of local clearance from their SELV
neighbors would resolve the large majority of the 60.

## 5. `part` — the declared isolators, confirmed

Every `part`-classified pair has `hv.ref == selv.ref`: the violating pair
*is* a single component's own two pins straddling the domain boundary.
This reproduces exactly the "declared mains↔PELV isolator" set from
`docs/evidence/2026-07-29-cross-domain-creepage-pd2-vs-pd3.md` §6 (K2, K3,
U3, U7, C6) — components whose entire job is to bridge HV and SELV, so an
intra-component "violation" here is not a layout mistake, it's the
component's datasheet creepage rating falling short of this board's 8.0mm
reinforced-insulation target. The only fix is a different, wider-creepage
package; no placement or routing change touches an intra-package pin
spacing.

## 6. Local placement — what the classification does and does not prove

The 21 `local placement` pairs are ones where the blocking body belongs to
a bystander or an endpoint's own footprint, and moving that part (or the
other endpoint) a few mm would remove the crossing **in principle** — this
is a claim about remedy *type* (placement suffices, no part swap or
floorplan change needed), not a proof that the necessary headroom actually
exists at each site. This triage did not run the placer, check local
component density, or verify keepout/thermal/mechanical constraints at any
of the 21 sites. Several of them cluster tightly around the same two nets
(`hb.gate_hs.driver-p2`/`p1-1`, i.e. the C17/C22 bootstrap network) and the
same handful of SELV neighbors (R26, R32, U13, U15, C16, C12, R77) — dense
enough that moving one part to clear one pair could plausibly tighten
another. **Verifying actual headroom at each of the 21 sites is flagged as
follow-up work, not claimed here.**

## 7. Why zero routing (slot) fixes were applied

The 9 `routing`-classified pairs are genuine candidates for a milled
isolation slot in principle (nothing physically blocks the direct
pad-to-pad path). None were cut in this pass, for reasons specific to what
this tool can and cannot verify, not from general caution:

1. **This tool measures pad-to-pad creepage only** (documented in its own
   module docstring, "What could not be measured" section, carried over
   unchanged from the branch this task started from) — it does not model
   any routed copper (traces, vias, pours). Proposing a slot's exact
   polygon without checking it against the board's real copper would risk
   routing a slot straight through an existing trace or via — a
   fabrication-breaking, not merely cosmetic, error. That check does not
   exist in this tool or elsewhere in this pass.
2. **A slot only helps if the resulting *creepage path around it* clears
   the target** — the straight-line pad-to-pad distance is not what a slot
   changes; the path that has to detour around the slot's perimeter is.
   Computing that path length correctly (shortest path around an obstacle
   polygon, not just "a slot exists") is machinery this tool does not
   have. Cutting a slot without that calculation could produce a board
   that still fails at 8.0mm, which is worse than not cutting one — a
   false sense of the problem being solved.
3. **The tightest cases have very little room.** C17.2↔R32.1 (0.905mm) is
   the extreme case: any slot geometry has to fit in well under 1mm of pad
   clearance plus whatever margin the slot itself needs from each pad
   (typically ≥0.5mm on a side, and a ≥0.6mm minimum mill-bit width) —
   plausible only if the slot is allowed to extend well beyond the direct
   line between the two pads into open board area, which again requires
   knowing what else occupies that area.

Given all three, "cut a slot" was judged **not verifiable within this
task's scope**, and per this task's own explicit escape valve ("if the
honest answer is 'few or none of these are routing-fixable,' say that — it
is a finding, not a failure"), this is reported as the honest answer: **0
of 60 fixed, before/after counts identical (60/60 at 8.0mm)**, because the
verification machinery to do it safely does not exist yet, not because the
9 candidates are hopeless.

## 8. How many of the 60 genuinely require floorplan work

**By this triage's own classification rule (§4.1), zero.** Every one of
the 60 was assigned `routing`, `local placement`, `part`, or `unresolved`
— none required "relocating HV/SELV regions relative to each other"
(this task's own definition of `floorplan`). The `part`-classified pairs
(21, §5) are single-component package swaps, not region moves; the
`local placement`-classified pairs (21, §6) are, by the classification
rule, moves of one part relative to its immediate neighbors, not of a
domain region relative to another.

**This is not the same claim as "the floorplan is fine."** Two caveats,
stated plainly rather than buried:

- §6's caveat applies directly here: 21 pairs being *classifiable* as
  local-placement-fixable is not the same as 21 pairs being *proven*
  fixable without touching the floorplan — if the bootstrap-network
  cluster (C17/C22 and their 7 SELV neighbors, accounting for roughly a
  third of the 60) turns out to have no local headroom on inspection, some
  of those 21 could turn out to need floorplan-level intervention after
  all. That inspection is out of this task's scope.
- The `part`-classified 21 assume a wider-creepage replacement part
  *exists and fits in the same footprint's placement*. If no
  drop-in-compatible part clears 8.0mm for a given package family (e.g. no
  optoisolator in U7's outline meets the creepage figure), the honest
  remedy for that component becomes floorplan-level after all. Not
  checked here — this task's brief was measurement and triage, not part
  sourcing.

So: **this triage found 0 of 60 that are floorplan-inevitable by its own
mechanical rule, with an important, explicitly-flagged residual risk that
up to roughly 42 of the 60 (the `local placement` + `part` buckets) could
partially escalate to floorplan on closer inspection** if their assumed
headroom or drop-in replacement parts don't materialize. This is reported
as the honest state of knowledge, not rounded up to a cleaner-sounding
verdict.

## 9. Constraints honoured

- No creepage target lowered or adjusted, no domain reclassified, to
  reduce any count. 60 is reported as measured, including the 9
  `unresolved` and the residual-risk caveat in §8.
- Domain membership taken from `elec/domain_manifest.yaml` by exact
  literal net name throughout (inherited from the tool's own existing
  discipline — not re-implemented here).
- No board re-floorplanning attempted (out of scope per this task's brief;
  §8 explicitly declines to claim more than the mechanical classification
  supports).
- Built in an isolated worktree (`wt-creepage-triage`), branched from
  `feat/pairwise-creepage-tool`. `make venv-isolate` run before any
  measurement. `uv run --no-sync` used for every invocation. No
  `git stash` used anywhere in this task.
- Two commits before this document: `c341286` (tool: rotation convention)
  and `916a06a` (board: F.Fab/F.CrtYd additions), each independently
  verified (§2, §3.4) before this document was written.
