# temper-airflow-r1 decisions (2026-10-15)

**Decision: impinging jets from the existing push hood onto native-21's FET / film-cap channel.** The jets take about
0.5 CFM. There is no second blower and no bigger blower. Numbers are in `README.md`; the build list is in `HANDOFF.md`.

**Basis.**
- **Board:** s42 (DECISIONS 55, codex/power-stage-integration c8665ceb0). The release ceiling there is 18.0 A in still air.
- **Bay:** 55 °C expected and 61 °C worst, from R33 study 14.
- **Ratings:** the power stage's own gate, with every gated row, including the 2512 R_on derating.

## D1. What the board needs: h_top ≈ 100 W/m²K over the channel, not "some airflow"

`board_h_sweep.py` puts forced convection on the native-21 top face, but only over the open copper between the TO-247
bodies and the film-cap bodies (model x 0–90, y 7–23.5). It credits the in-channel part bodies (R5, R10/R12/R18/R20,
R53/R54/R57/R58) at the same h. Everything else stays at h 10, and the air is taken at bay temperature.

It reproduces the power stage's s42 `margins.json` exactly: 44 rows each, 0.0 K difference. It also reproduces their
still-air ceilings: 19.9 / 18.2 A here, against their 20.0 / 18.3 A.

**Required h_top** (smallest h at which every gated row is ≥ 0):

| Ceiling | Bay 55 °C | Bay 61 °C |
|---|---|---|
| 26 A | 52.9 W/m²K | 82.1 W/m²K |
| 28 A | 73.2 W/m²K | 97.2 W/m²K |

- **C40, then C38 (film Top,max 110 °C), set the requirement at every point.** Next come the R12 2512 terminal derating
  and the laminate.
- **The 2512 gate resistors are covered with room to spare.** R12 terminal needs 38–58 W/m²K; R10 needs 33–49 W/m²K.
- The film caps have no body-to-air path in the model, so their requirement is an upper bound. Jets that reach the cap
  bodies would lower it. The bench measures that.

## D2. Jets, not air blown along the board

- **Air blown along the face** (flat plate over the 90 mm channel) needs:
  - 8.5–18 m/s with turbulent flow, or 16–54 m/s laminar;
  - 4.5–9.6 CFM at 60–270 Pa to reach h 53–97.

  That is a third to two-thirds of the blower's total flow, at more than its working pressure. It would starve the sink
  and the coil. (`delivery.json` → `parallel_flow_alternative`)
- **Eight Ø3 mm jets, 6 mm above the board,** give the design h on far less air:
  - at the blower's 5.5 V floor: 0.41 CFM at 20 Pa, h 90 on the design basis (149 estimate);
  - at drive 0.55: 0.48 CFM at 28 Pa, h 100.

  Design basis is Martin (1977) × 0.6 below its validated Reynolds number, which is how R32 already sizes the coil jets.

## D3. A bleed from the existing push hood; no second or bigger blower

**The bleed.** The jets are a third branch beside the sink and coil branches, between the hood (high side) and the
exhaust plenum (low side). Their air leaves through the bay and a new 30 × 25 mm vent in the plenum wall.

**Why no second or bigger blower.**
- The bleed needs under 1 CFM, at pressures the blower already makes at its floor (20 Pa) and at 0.55 (28 Pa).
- A second air mover would add a part, a supply branch, a noise source and a second failure mode, and buy nothing.
- A bigger blower is not needed for the board.

**What the bleed costs** (`delivery.json` → `cost_to_sink_and_coil`):

| Item | Without jets | With jets | Effect |
|---|---|---|---|
| Sink flow at full speed | 20.4 CFM | 19.9 CFM | R_SA 0.2552 → 0.2576 °C/W (S8); 0.214 → 0.216 °C/W (K1) |
| Basis B at 28 A (73 W, what fet_case uses) | floor drive | floor drive | Sink held at the 88.6 °C setpoint either way, so FET tab temperatures are unchanged |
| Basis A at 28 A (150 W, study 11), K1 sink | drive 0.75 | drive 0.80 | +1.4 dB estimate; S8 cannot hold 150 W either way, as before |
| Coil branch | — | −2 % flow | Winding +1.0 K at the floor (expected Litz, 28 A); the 196 W acceptance case needs drive 0.90 instead of 0.85 |
| Glass | — | — | Cooled through the same coil air, so the same small change |

**Board floor drive: 0.55.** At bay 61 °C and 28 A, the design basis needs drive 0.55; every other case is met at the
floor. At 0.55 the blower is:
- 45.0 dB(A), estimated;
- 2.8 W typical / 5.4 W at Delta's maximum.

Above the 18 A still-air ceiling, the coil and sink loops already run the blower, so the board loop rarely adds noise.

**Ceiling at drive 0.55** (h design 100; `delivery.json` → `ceiling_by_drive`):
- 30.5 A at bay 55 °C;
- 28.5 A at bay 61 °C.

Past 28 A this is extrapolated, and the 28 A cap applies. At bay 61 °C and 28 A, U26 (not in the channel) is then
within about 1 K. That is the next limiter, and airflow does not move it.

## D4. Bay air and recirculation

**The jets ventilate the bay** (study 14's lumped bay plus the jet through-flow, with jet air at 50 °C):

| Case | Still air | With jets |
|---|---|---|
| Expected | 55.4 °C | 54.7 °C |
| 28 A worst | 61.3 °C | 59.8 °C (58.6 °C at full speed) |
| Allowances stacked | 78.1 °C | 74.2 °C |

The sweep in D1 still takes the jet air at bay temperature. That is conservative: the jets carry push-hood air, which
the D-18 basis puts at 50 °C. `jet_air_check.py` gives the estimate with jet-air and ventilated-bay credit (README §2).

**Recirculation.**
- The bay's only new exit is the plenum vent, which leads out through the door. So jet air does not return to the blower inlet.
- The blower breathes room air through the base field, as R32 has it. R32's re-ingestion allowance of 10 K is unchanged.
- Door exhaust rises by 0.26–0.33 K.

## D5. A bay-air NTC goes in the change set

**Include it.** It is one Semitec 104GT-2 bead, the part already used in R40, plus one controller channel.

**Why:**
- **It gates the jets' own ceiling.** The 28 A ceiling holds to bay 61 °C. At the stacked-allowance bay (74 °C even with
  jets) it does not. Only a measurement distinguishes the two.
- **It lets firmware run the power stage's 20 A still-air point** when the bay reads ≤ 55 °C. That is useful if the
  blower fails.
- **It is the soak instrument** for the power stage's ask 3.

**The airflow change matters more than the sensor.** With jets, the 61 °C worst case gives 28.5 A. Without jets, a
sensor alone moves 18 → 20 A.

## D6. What the power stage must re-run (to be relayed; this folder edits nothing of theirs)

1. **Gate the airflow case.** Run `b3_ratings_gate` on a "board-face jets" case: region h_top on the top face over model
   x 0–90, y 7–23.5, in-channel bodies credited.
   - h_top 100 at bay 61 °C and h_top 90 at bay 55 °C (drive 0.55 and the floor).
   - Then set the release ceiling with the airflow present, from the c26/c28 pair as here, or their own c22/c28 pair.
   - `board_h_sweep.py` is a working implementation: it wraps `thermal_body.assemble` / `build_network_parts` and edits
     nothing.
2. **Keep the channel low.** Treat model x 0–92, y 9–24 as a keep-out for any part taller than 4 mm: the jet floor sits
   6 mm above the board. s42 passes (`cad/channel-parts.json`: all SMD).
3. **Add a film-cap body-to-air path** (C38–C41) for the jet case, or take the bench IR. Today it is the limiting, and
   bounding, row.
4. **fet_case and sink:** confirm that the basis-B sink hold at the floor is unchanged. Re-run study 11's basis A (K1)
   at drive ≥ 0.80.
5. **Firmware:**
   - add the board floor term (drive ≥ 0.55 above 18 A);
   - on tach loss, clamp to the still-air ceiling, and set the allowed delay;
   - optionally, add the bay-NTC ceiling table.
6. **U26 at 28 A, bay 61 °C:** about 1 K of margin with jets, and airflow does not move it.
7. **Reply to ENCLOSURE-REQUEST asks 1–3:**
   1. yes: the path, h and flows are above;
   2. the bay is still air only with the blower stopped, which firmware now prevents above 18 A;
   3. the soak is in the R45 bench plan, with the bay NTC.

## Not done here

- No CFD. The jet h is a correlation estimate, used outside its validated Re, with a 0.6 factor. Bench A1/A3 and a
  heated-plate test confirm it.
- No R45 CAD. `cad/fit_check.py` uses plain envelopes against R43's STEP, and R43's native-21 is stage 13.
  `cad/channel_parts.py` checks the s42 placement instead.
