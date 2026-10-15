# temper-airflow-r1: board-face air for native-21's 26–28 A ceiling

2026-10-15. This study answers the power stage's `b3-ratings/ENCLOSURE-REQUEST.md` and OPEN-ITEMS S2.

**Question.** What must the enclosure change so native-21 can run 26–28 A of tank current instead of the 18 A
still-air release ceiling?

**Answer.** Eight Ø3 mm air jets, fed from the existing push hood, aimed at the board's FET / film-cap channel. They
take 0.41–0.48 CFM. The build list for enclosure round **R45** is in `HANDOFF.md`, and the reasoning is in
`DECISIONS.md`.

**Evidence status.** Every number is an **estimate** from the scripts below. Nothing here is measured. Where a number
is a bound, it says so.

**Basis.**
- **Board:** s42, the board of record (DECISIONS 55; codex/power-stage-integration c8665ceb0).
- **Bay air:** R33 study 14, 55 °C expected and 61 °C worst.
- **Ratings:** the power stage's own gate, at the datasheet limits it cites.

## How to rerun

Run the scripts in this order. All write JSON beside themselves.

| Script | Runtime | Writes | What it does |
|---|---|---|---|
| `python3 board_h_sweep.py --snapshot` | ~70 min, 4 cores | `board-h-sweep.json`, `runs/` | Rebuilds `.ps-snapshot/` from git at c8665ceb0, plus the task-04 fields, which `a4_fields.check()` verifies. It then sweeps h_top over 10–150 W/m²K at 26 and 28 A, solving each bay of 55 and 61 °C separately. Control: it reproduces the power stage's s42 `margins.json` (44 rows each, max difference 0.0 K) and their still-air ceilings (19.9 / 18.2 A, against 20.0 / 18.3 A). |
| `python3 delivery.py` | seconds | `delivery.json` | Three-branch blower network: R43's `coil_thermal` model, imported read-only, plus the jet branch. Gives the jet h (Martin), the sink, coil and bay effects, door exhaust, and the parallel-flow comparison. |
| `python3 jet_air_check.py` | ~20 min | `jet-air-check.json` | Gates the chosen operating points with the jet air at 50 °C and the bay ventilated (estimate). |
| `cd cad && ../.venv/bin/python fit_check.py` | ~3 min | `cad/fit-check.json` | Clash and clearance check of the new parts against R43's STEP (build123d 0.11.1). |
| `cd cad && python3 channel_parts.py` | seconds | `cad/channel-parts.json` | Checks s42's own placement: every part under the jet box is SMD. |

The venv is not committed. Build it with `uv venv -p 3.12 .venv && VIRTUAL_ENV=.venv uv pip install build123d==0.11.1`.

**Provenance.** `board-h-sweep.json` → `provenance` records the commit and the sha256 of all 15 imported sources, and
`sources_match_commit: true`.

**Do not import from the live worktree.** The live `worktrees/ps-integrate` tree moved from s41 to s42 partway through
this study's first run, and that run was discarded. Always import from the snapshot.

## 1. Requirement: top-face h over the channel

The region is native-21's top copper between the TO-247 bodies and the film-cap bodies: model x 0–90, y 7–23.5. The
part bodies in the region are credited at the same h. The air is taken at bay temperature.

**Board-wide requirement** (`board-h-sweep.json` → `required_h_top`): the smallest h_top at which every gated row is ≥ 0.

| Ceiling | Bay 55 °C | Bay 61 °C |
|---|---|---|
| 26 A | 52.9 W/m²K | 82.1 W/m²K |
| 28 A | 73.2 W/m²K | 97.2 W/m²K |

**h_top that brings each row to 0** (`per_row_h_zero`), at 28 A, bay 55 / 61 °C:

| Row | 28 A, bay 55 °C | 28 A, bay 61 °C |
|---|---|---|
| C40 (Top,max 110 °C) | 73.2 | 95.2 |
| C38 | 66.7 | 90.5 |
| C39 | 53.7 | 79.7 |
| Laminate, 1 mm block | 51.2 | 60.4 |
| Laminate, FET row | 47.6 | 59.7 |
| R12 2512 terminal derating | 50.0 | 58.4 |
| R10 2512 terminal derating | 40.8 | 49.3 |
| R58 1206 terminal derating | 41.6 | 50.6 |
| U26 | — | 55.0 |

At 26 A every row needs less; the film caps still lead (C40 52.9 / 72.5).

**Ceiling vs h** (`ceiling_by_h`): the power stage's I_trip² method, applied to this sweep's c26/c28 pair.

| h_top | 10 | 20 | 35 | 60 | 100 | 150 |
|---|---|---|---|---|---|---|
| Ceiling at bay 55 °C (A) | 19.9 | 21.8 | 23.9 | 26.9 | 30.5 | 33.8 |
| Ceiling at bay 61 °C (A) | 18.2 | 20.1 | 22.2 | 25.0 | 28.5 | 29.5 |

- At bay 61 °C and h ≥ 100, U26 takes over; it sits outside the channel.
- Above 28 A the values are extrapolated, and the 28 A cap applies.

## 2. Delivery: a jet bleed from the push hood

**The path.** Push hood −Y wall hole → F3 duct (12 × 14 mm inside) → jet box → 8 × Ø3 jets at 11 mm pitch, 6 mm above
the board → bay → 30 × 25 mm vent in the exhaust plenum wall → door.

**Model.** Min-corner Delta BFB1012VH-F00, from the digitised datasheet curve.

**Design basis.** h = Martin × 0.6, as R32 uses for the coil jets. The jets run at Re 570–1150, below Martin's ≥ 2000,
so this is an estimate.

`delivery.json` → `operating_points`, S8 sink:

| Drive | Jet branch | Jet h (design / est.) | Sink flow | Coil flow | Noise est. | Blower power, typ / max |
|---|---|---|---|---|---|---|
| 0.458 (5.5 V floor) | 0.41 CFM at 20.1 Pa | 90 / 150 W/m²K | 8.6 CFM | 2.9 CFM | 41.0 dB(A) | 1.6 / 3.1 W |
| **0.55** | **0.48 CFM at 27.6 Pa** | **100 / 167 W/m²K** | 10.5 CFM | 3.5 CFM | **45.0 dB(A)** | **2.8 / 5.4 W** |
| 1.0 | 0.83 CFM at 80.4 Pa | 143 / 239 W/m²K | 19.9 CFM | 5.9 CFM | 58.0 dB(A) | 17.0 / 32.4 W |

**Minimum drive** (`board_min_drive`, design basis):
- the floor for 26 A at both bays and for 28 A at bay 55 °C;
- **0.55 for 28 A at bay 61 °C**.

On the estimate basis, every case is met at the floor.

**Estimate with jet-air credit** (`jet-air-check.json`). Jets at 50 °C, bay ventilated to 54.7 / 59.5–59.8 °C:

| Ceiling, bay | Drive | Worst gated row | C40 |
|---|---|---|---|
| 28 A, bay 61 °C | 0.55 | U26 +2.4 K | +6.3 K |
| 28 A, bay 55 °C | floor | C40 +6.4 K | +6.4 K |
| 26 A, bay 61 °C | floor | U26 +3.4 K | +8.8 K |

**Air blown along the board instead** (`parallel_flow_alternative`) would need 8.5–18 m/s (turbulent), or 4.5–9.6 CFM
at 60–270 Pa. That was rejected (DECISIONS D2).

**What the jets cost the sink and coil** (`cost_to_sink_and_coil`):

| Item | Without jets | With jets |
|---|---|---|
| Sink R_SA at full speed, S8 | 0.2552 °C/W | 0.2576 °C/W |
| Sink R_SA at full speed, K1 | 0.214 °C/W | 0.216 °C/W |
| Basis B at 28 A (73 W) | floor | floor (FET tabs unchanged) |
| Basis A at 28 A (150 W), K1 sink | drive 0.75 | drive 0.80 |
| Coil winding, expected Litz, at the floor | — | +1.0 K |
| Coil, 196 W acceptance case | drive 0.85 | drive 0.90 |

**Bay air** (`bay_air_C_by_drive`), still air → with jets at the floor:

| Case | Still air | With jets (floor) |
|---|---|---|
| Expected | 55.4 °C | 54.7 °C |
| 28 A | 61.3 °C | 59.8 °C |
| Allowances stacked | 78.1 °C | 74.2 °C |

Door exhaust rises by 0.26–0.33 K.

## 3. Constraints

| Constraint | Result | Source |
|---|---|---|
| Spill / ingress | No new external opening. The vent is internal, with its bottom edge 14 mm above the plenum floor. | `cad/fit_check.py` geometry |
| Touch | Door exhaust +0.33 K at most. The jet box is internal. | `delivery.json` → `door_exhaust` |
| Creepage / clearance | **No new metal near native-21.** The jet box and F3 are insulating. The only metal change, the hood hole rim, is 26.0 mm from native-21's components and 23.6 mm from the board, against the ≥ 8 mm rule. Insulating parts sit 1.2 mm from the film-cap bodies and 6.0 mm above the board. | `cad/fit-check.json` |
| EMC | No metal duct, so no new coupling path. The perforated-steel EM4/EM6 contingency, if fitted, sits above the comb and clears the jet box's top at Z42.5. | design choice |
| Fit | No overlaps with R43. Closest gaps: 1.0 mm to the FR-4 pressure strip, 1.2 mm to the film caps, 2.0 mm (F3) to the board edge. The R43 envelope is stage 13; s42's placement under the box is all SMD (PASS). | `cad/fit-check.json`, `cad/channel-parts.json` |
| C1 sensor connector at (135, 285, 62) | **The "≤ 50 °C air" premise does not hold.** C1 sits in bay air: 55.4 / 61.3 °C in still air, 54.7 / 59.8 °C with jets (74.2 °C stacked). That is within the Micro-Fit's 85 °C limit, which sensor-r3 used, by ≥ 25 K (≥ 10.8 K stacked). Neither design gives ≤ 50 °C. Flag this to the sensor line. | `delivery.json` → `bay_air_C_by_drive` |
| Assembly and cost | Two new insulating parts, one hood hole with 2 PEMs, one plenum cut, one NTC with its lead. No prices here: quote them. | `HANDOFF.md` |

## 4. Open items

- **Board-face h is a correlation estimate, used outside its validated Re** (× 0.6 design factor). It needs a
  heated-plate or IR measurement under the jet box.
- **The film caps have no body-to-air path in the model.** They are the limiting, bounding row.
- **U26 at 28 A and bay 61 °C has only 2.4 K (estimate) to 0.6 K (conservative).** Airflow does not fix it.
- **The bay model is lumped** (study 14, UA assumed). The soak with the bay NTC measures it.
- **Basis-A sink at 28 A** still needs study 11's K1 sink. S8 cannot hold 150 W, with or without jets.
- **R45 CAD, assembly sequence and retention** of the cantilevered jet box are not done yet. The firmware board-floor
  and tach-loss clamp are not built.
