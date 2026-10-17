# M6 (coil studs) and M10 (L outline, J4 harness): recommendations

- **Board:** stage 11, `s11/section.kicad_pcb`, SHA-256 `e85a4c82…98ac`, with its `copper-dump.json`.
- **Enclosure:** `output/temper-manufacturing-r25` (native-21 snapshot 7c55c9ab8, after stage 11).
- **Evidence:** every number below comes from a script in this folder; its output is in `evidence.txt`. Values I could not source are marked **estimate** or **unverified**.
- **Standard text:** IEC 60335-1:2020 clause 29 and Tables 15–18, from the publisher's sample PDF that D5-BASIS cites. The extracted text is in `src/iec60335-1-2020-sample.txt`, lines 160–604.

## Summary

| Item | Recommendation | Layout change |
| --- | --- | --- |
| **M6** | Keep J2/J5 at 15 mm. Replace ASSEMBLY.md's 30 mm target with the derived requirement: 5.0 mm functional creepage under Table 18. Require insulated ring lugs, so that only the ring is bare metal. No barrier. | None |
| **M10** | Record the L outline and J4 on the front of the tongue as an amendment to D-36. R4 and R25 both accept it, and J4 is the right place for R25's front controller. | None (docs only) |

---

## M6: coil studs J2/J5

### Measured facts (stage-11 board)

The topology is SW_A → T1 (one-turn primary) → **J2 `coil_feed`** → coil → **J5 `res_a`** → C21–C23 → SW_B. The J2–J5 voltage is the coil voltage. SW_A copper is at J2's potential, apart from T1's one-turn drop.

| Quantity | Value | Source |
| --- | ---: | --- |
| Stud centres J5 (132, 70.5) to J2 (132, 85.5) | **15.00 mm** | `probe.py` (pcbnew) |
| REDCUBE metal body | 7.0 × 7.0 mm square, 2.5 mm tall | Würth 74650074 drawing rev 002.002 (`src/we-74650074.pdf`, p.1) |
| Body to body | **8.0 mm** | 15 − 7.0 |
| `res_a`↔`coil_feed` copper, plan view | **5.000 mm** (F.Cu and B.Cu pours, at (127.5, 75.1)); In1/In2 5.94 mm | `stud_copper.py` |
| Lug to lug, Würth 5580406 ring lugs (10 mm wide), both pointing +x | **5.0 mm** | `lug_rotation.py` |
| Lug to lug, bare lugs in the most unfavourable rotation | **0 mm (contact)** at 15, 20 **and 30 mm** pitch; 3.5 mm at 37 mm | `lug_rotation.py` |
| Ring to ring, insulated lugs (only the 10 mm ring is bare) | **5.0 mm**, at any rotation | `lug_rotation.py` |
| **Same coil voltage elsewhere on the board:** `res_a`↔`sw_a` (F.Cu) | **5.000 mm**, along **74 mm** of edge | `tank_pairs.py` |
| Capacitor voltage: `res_a`↔`sw_b` (B.Cu) | 5.002 mm, along 43 mm of edge | `tank_pairs.py` |

**Key fact:** the studs do not set the board's worst coil-voltage gap. The SW_A tank lane wraps J5 at exactly 5.0 mm, along 74 mm of edge (`stud-region.png`). Moving J5 cannot raise the board minimum above 5.0 mm. The stud hardware only needs to be no worse than the copper.

### Working voltage across J2–J5

From `coil_voltage.py`: V = I·|R_pan(f) + R_coil + jωL|, applied to task 05's nine retained cases (`05-resonant-tank-envelope/outputs/cases.csv`, cast-iron low-L corner only).

| Case | Time-RMS | Peak |
| --- | ---: | ---: |
| Retained 1710 W cases, 108–140 V (before the 22 A ceiling) | 305–321 V rms | 593–636 V pk |
| **Envelope bound (estimate):** tank ≤ 22 A rms (DECISIONS 2026-10-08), f ≥ highest tank resonance (S4, 48 µH → 31.3 kHz), \|V_coil\| ≤ \|V_drive,1\| + \|V_C\| | **≤ 333 V rms** at 140 V | ≤ 667 V pk |
| ASSEMBLY.md nominal | — | ≈ 540 V pk |

Frequency is 31–55 kHz, so the IEC 60664-4 (> 30 kHz) clauses apply.

### Requirement, derived from IEC 60335-1:2020

- **Insulation type.** J2–J5 is **functional** insulation: two points of one HOT circuit. The D5 8.0 mm HOT↔SELV/PE floor does not apply between them. The project's 3.2 mm (HOT groups) and 5.0 mm (tank) rules are Table 18 values (native-04 PLACEMENT-REVIEW rules table).
- **Creepage.** Clause 29.2.4 requires Table 18. Use **PD3, material group IIIa/IIIb** (D5-BASIS: PD3, CTI ≥ 175). The rows are 250 V → **3.2 mm**, 400 V → **5.0 mm**, 500 V → **6.3 mm**; NOTE 3 allows interpolation.
  - 333 V rms bound → **4.20 mm**.
  - Retained-case maximum (320 V) → 4.05 mm.
  - **The 5.0 mm tank rule covers working voltages up to 400 V rms.**
  - Above 30 kHz, 29.2.4 also requires IEC 60664-4:2005 Table 2 "if larger". **Unverified here:** I have no copy of 60664-4. D5-AUDIT expects these values to be well below 8 mm at these voltages.
- **Clearance.** Clause 29.1.4 takes the largest of three values:
  - Table 16 at the rated impulse voltage. Table 15 gives 120 V, OVC II → 1500 V → 0.5 mm. Footnote c raises this to **0.8 mm at PD3**. Add 0.5 mm because 29.1 covers movable or assembled parts: **1.3 mm**.
  - IEC 60664-4 Clause 4 at the recurring peak (≤ 0.67 kV). **Unverified:** expected to be sub-millimetre at 31–55 kHz.
  - F.7a, which applies only at ≤ 30 kHz.
  - **All the measured gaps (5.0 / 8.0 mm) clear 1.3 mm by a wide margin.**
- **Most unfavourable position.** Clause 29.1/29.2 places "parts … that can be tightened to different positions during assembly" in the most unfavourable position. A ring lug is such a part. Bare lugs can be turned into contact at 15 mm **and also at the 30 mm target** (16 mm lug reach × 2 > 30 mm). So the 30 mm target in ASSEMBLY.md does not meet the clause either. The real requirement is that **exposed metal stays ≥ 5.0 mm apart at any lug rotation**.
- **Short-circuit route** (29.2.4, last paragraph; estimate). A J2–J5 short leaves the bridge driving C21–C23 alone: 22–51 A pk, 11–26 A rms over 108–140 V and 34–60 kHz (`coil_voltage.py`). This produces no heating. It is at or below the 22 A ceiling except at 60 kHz high line, where OCP (47.5–98 A pk) or the ceiling acts. A Clause 19 test with the gap shorted is therefore a fallback route to qualify the gap, not a design input.

**Derived requirement:** J2↔J5 exposed metal and copper ≥ **5.0 mm** creepage and ≥ 1.3 mm clearance, at any lug rotation. This holds for a working voltage ≤ 400 V rms, with the envelope bound at ≤ 333 V. The 30 mm target has no basis in the standard.

### Options

**(a) Move J5 to ≥ 30 mm from J2.**
- **Straight up (132, 55.5):** the courtyard lands on H6, a nylon hole frozen to the enclosure (`neighbours.py`), and on the HV_RET/BUS_P planes (`slot_check.py`).
- **Diagonal sites (145–147, 55–58):** about 30 mm from J2, but the courtyard sits on **68–89 mm² of the SW_A F.Cu tank lane** (`slot_check.py`).
- **What moves with it:**
  - re-route the SW_A tank lane (the 7.0 mm section that sets the 22 A ceiling) and the `res_a` B.Cu pour;
  - re-run the task 04 tank screen, both barrier gates, DRC, D5 and Gerber review;
  - R25 moves its carrier Ø7 and Nomex Ø10 coil-lead holes (world (9, 165.5)).
- **What it doesn't fix:** bare lugs can still touch at 30 mm, and the board minimum stays 5.0 mm (SW_A↔RES_A).
- **Verdict: rejected.** It costs a tank-path re-layout and fixes nothing that governs.

**(b) Insulated ring terminals plus a barrier.**
- **Insulated lugs alone** make the exposed metal the 10 mm rings: **5.0 mm at any rotation** (`lug_rotation.py`). This equals the copper gap and meets the derived requirement, with 0.8 mm margin over the 4.20 mm bound.
- **A barrier adds no distance that governs:**
  - A slot fits only at x 123.5–136.5 (12 mm). SW_A F.Cu and RES_A B.Cu fill the rest of the inter-stud strip (`slot_check.py`).
  - Clamping a fence under the screw puts plastic in a 22 A clamped joint, so torque relaxes. Avoid it.
  - A barrier only matters if the lab rules a conservative RMS convention (see owner item 1). Then 5.65 mm is needed at the 636 V pk case, and **the whole board's 5.0 mm tank rule must change**, not just the studs.

### Recommendation: option (b) without the barrier. No layout change.

Exact changes:

1. **ASSEMBLY.md.** Replace the paragraph that starts "The bare REDCUBE has no manufacturer voltage rating. Use at least 30 mm centers…" with:

   > J2 (COIL_FEED) and J5 (RES_A) are at 15.0 mm centres. Their insulation is functional (IEC 60335-1:2020 29.2.4, Table 18, PD3, group IIIa). The coil-terminal working voltage is ≤ 333 V rms (estimated bound at the 22 A tank ceiling; ≤ 667 V pk, 31–55 kHz), so creepage needs ≥ 4.2 mm (5.0 mm rule, covering ≤ 400 V rms). Clearance needs ≥ 1.3 mm (Table 16 PD3 + 0.5 mm for assembled parts), pending the IEC 60664-4 check.
   >
   > The board copper gap is 5.0 mm. Coil leads terminate in **insulated M4 ring terminals** whose insulation covers the barrel and neck up to the ring. The bare ring is ≤ 10.0 mm wide, washer DIN 125 M4 (9 mm), pan-head M4 (head ≤ 8 mm). This keeps exposed metal ≥ 5.0 mm apart at any lug rotation (29.1/29.2 "most unfavourable position"). Bare (uninsulated) ring lugs are not permitted on J2/J5: they can be turned into contact at any pitch below about 37 mm. Dress both lugs to point +x (board frame), clear of each other. The insulation rating must cover the measured lead temperature at the stud.

2. **Coil pigtail termination (coil supplier, R25 harness):**
   - insulated M4 ring, 2.6–6.6 mm², for example **TE PLASTI-GRIP 2-34853-1**. This is a candidate only: its vinyl sleeve is rated 105 °C, and its ring OD and temperature must be checked against the measured lead temperature;
   - or a non-insulated flag lug with dual-wall heat-shrink to the ring, rated ≥ 150 °C.
   - R25 drops both leads onto the stud axes (`harness_r19.py`, (9, 150.5/165.5)). That is not physical, because the screw head sits on the axis. The drop points need offsetting by the lug barrel offset (≈ 8–10 mm, **estimate**) in world −x (= board +x), so both lugs are parallel.
3. **DECISIONS.md entry, ready to paste:**

   > **2026-10-08, coil-stud spacing (review M6), owner decision:** J2/J5 stay at **15.0 mm**. The J2–J5 insulation is functional. IEC 60335-1:2020 29.2.4 / Table 18 (PD3, IIIa) needs 4.2 mm creepage at the estimated ≤ 333 V rms coil-voltage bound (22 A ceiling, f ≥ 31.3 kHz), and the 5.0 mm tank rule covers ≤ 400 V rms. Clearance needs ≥ 1.3 mm (Table 16 PD3 + 0.5 mm).
   >
   > The board's own minimum for this voltage is 5.0 mm: SW_A↔RES_A along 74 mm and RES_A↔COIL_FEED at the studs. Moving J5 cannot raise it. With bare lugs, even 30 mm centres fail the "most unfavourable position" rule, because the lugs can be turned into contact. **Requirement:** insulated M4 ring terminals on J2/J5 (bare ring ≤ 10 mm, ring-to-ring ≥ 5.0 mm at any rotation). ASSEMBLY.md's 30 mm target is withdrawn.
   >
   > **Reverses if** the certification lab rates the line-modulated HF working voltage as carrier-crest RMS (5.65 mm at 636 V pk). That changes the board-wide tank rule to ≥ 5.7 mm (a re-layout of the SW_A/RES_A lanes), not just the studs. It also reverses if IEC 60664-4 Table 2 exceeds 5.0 mm. Evidence: `m6m10/` scripts and `evidence.txt`.

---

## M10: L outline and J4 harness

### Measured facts

- **Outline:** Edge.Cuts is 290 × 140, plus a 91 × 50 tongue at x 0–91, y 140–190 (`probe.py`).
- **J4:** Molex 43045-1612 at (30.4–59.6, 177.1–186.9), on the front of the tongue. In R25 world coordinates, J4's mate is at x 83–109, y 51–58.
- **Pose:** world = (141 − x, 236 − y), so the tongue occupies world x 50–141, y 46–96. RELAYOUT L11 (D-36) allowed y 96…236 only.

### Does the enclosure accept the L?

**R4 fit gate (repo).** `board_in_enclosure.py` models the L (hard-coded two rectangles) on the stage-11 boxes: **417 bodies, 0 hits**. I re-ran it (`rerun-native21-in-r4.json`, exit 0), and it matches `native21-in-r4.json`.

**R25 (latest enclosure).** R25 models the board as the L ("L outline 290 × 140 plus a 91 × 50 tongue", `src/electronics_r17.py` l.7–9, 81, 133).
- The R25 all-pairs screen reports **1054 candidates, 0 unresolved** (`evidence/full-assembly-interferences.json`, `PASS_NOMINAL_SAVED_PAIR_SCREEN`).
- All 18 hits on native-21 parts are documented dispositions: through-hole bodies, threaded standoffs, and cable entries at J3. None of them involves the tongue.
- Parts over the tongue, from `catalog.json`:
  - the encoder (z 57.5–94.9) and knob;
  - H2/H3 nylon standoffs at world (135, 56) and (55, 56). **The enclosure has already adopted the tongue's fixings** (R24/R25 hole table).
  - The controller board ends at world x 38, which is 12 mm left of the tongue's edge.

### Does the J4 harness route work in R25?

`harness_SELV_J4_to_controller` runs from J4's mate (96, 54.7, 49.5) to the controller's right edge (42.2, 42, 34).
- **Developed length 74 mm**, tightest bend 11.2 mm (catalog evidence).
- The route-landing check passes: **50/50 ends land** (`evidence/route-landings.json`).
- No interference with any part.
- **Clear of HOT:** the whole run lies at world y 40–56.5. That is in front of the Nomex 410 SELV/HOT barrier's edge (y 76), over the SELV tongue only. It never crosses HOT board area.

**Counterfactual: J4 on the rear band, as FLOORPLAN/L15 said (estimate).** J4 would sit near world y ≈ 226. The controller is at y 14–90, so the lead would be ≥ 140 mm long and cross the HOT power core, through the Z ≥ 77.9 SELV channel above the barrier. The current placement is shorter and has no HOT crossing.

L15's owner input ("enclosure connectors on the rear wall") is about the **enclosure's external** connectors. J4 is internal.

### Recommendation: record the L outline and J4's front position

Exact changes:

1. **DECISIONS.md entry, ready to paste:**

   > **2026-10-08, native-21 outline and J4 position (review M10; amends D-36 / RELAYOUT L11, L15), owner decision:** the outline is **290 × 140 plus a 91 × 50 SELV tongue (board x 0–91, y 140–190; R4/R25 world x 50–141, y 46–96)**, 290 × 190 overall. It grew during routing to hold J4 and the SELV island's tongue fixings (H2/H3). **J4 stays on the tongue's front edge.** The R25 controller sits at the front (world y 14–90), and the J4 lead is 74 mm long, lands at both ends, and stays entirely in front of the Nomex SELV/HOT barrier (route landings 50/50, all-pairs 0 unresolved, R25 evidence). A rear-band J4 would need a ≥ 140 mm SELV lead across the HOT core (estimate).
   >
   > L15's "rear" applies to the enclosure's external connectors (mains, inlet) and to the coil leads (which drop from the carrier). It does not apply to the internal SELV harness. **Fit:** `board_in_enclosure.py` (L modelled) gives 417 bodies, 0 hits in R4, and R25 carries the L with H2/H3 standoffs adopted. **Reverses if** the controller moves rearward or the encoder/knob stack moves over the tongue. Re-run `board_in_enclosure.py` and the R25 all-pairs and route-landing checks.

2. **Edits that follow:**
   - **RELAYOUT-REQUIREMENTS.md:** L11 becomes "290 × 140 + 91 × 50 tongue at world x 50…141, y 46…96". L15 drops "J4" from the rear-edge list.
   - **native-21/FLOORPLAN.md:**
     - remove "owner confirmation open";
     - the SELV island row should say "J4 (harness exits forward to the front controller)";
     - the connector sentence "(J1, J2, J5, J3, J6, J4 pigtail) on or near the top edge" becomes "J1, J3 on the rear edge; J2/J5 under the coil carrier; J4 on the tongue's front edge; J6 front edge of the main body".
   - **REVIEW-TRIAGE.md, M10 row:** status becomes **decision**.
3. **Optional, not blocking:** a ≥ 1 mm inside radius at the L corner (91, 140) (review m13). Do it at the next outline touch.

---

## What still needs the owner

1. **Approve the two DECISIONS entries above.** M6 withdraws ASSEMBLY.md's 30 mm target. M10 amends D-36.
2. **Certification-lab question (add to R25 CERTIFICATION-QUESTIONS.md).** For a 31–55 kHz tank voltage modulated at 120 Hz, is the Table 18 working voltage the time-RMS (≤ 333 V → 5.0 mm rule holds) or the carrier-crest RMS (up to ≈ 470 V → ≈ 5.9 mm)?
   - The second answer moves the **board-wide** tank rule, not just the studs.
   - The lab should also confirm the IEC 60664-4:2005 Table 2 creepage and Clause 4 clearance values, which I could not obtain.
3. **Coil lead termination:** lug part, sleeve temperature rating against the measured lead temperature at the stud, and crimp process. This goes with the coil supplier (ASSEMBLY.md already flags that the bench lug is not automatically suitable). The R25 coil-lead drop points also need offsetting for the lug barrel (enclosure session).
4. **Coverage caveat on the voltage numbers.** The task 05 cases cover only the cast-iron low-L corner. The 333 V rms bound is an analytic estimate: it assumes a sinusoidal line envelope (I_pk = 2·I_rms), f ≥ 31.3 kHz, and the 22 A ceiling enforced by firmware that does not exist yet. The bench must measure the J2–J5 voltage (R25 BENCH-PLAN P-series).
5. **Unchanged and outside this decision:** M11 (sink HOT↔PE stack). Also the REDCUBE screw-tip-to-chassis distance (M10 "Also"): from R25 bounding boxes, the board bottom is Z26 and the floor top about Z11, roughly 14 mm (**estimate**, above the 8 mm D5 floor). Confirm it with the real screw length.

## Files in this folder

| File | Purpose |
| --- | --- |
| `probe.py` | Footprints, pads and outline from the board (KiCad 10 pcbnew) |
| `neighbours.py` | Courtyards around the studs |
| `stud_copper.py`, `tank_pairs.py`, `slot_check.py` | Copper gaps, facing lengths, slot and relocation keep-outs (shapely on the copper dump) |
| `lug_rotation.py` | Most-unfavourable-rotation sweep for bare and insulated lugs |
| `coil_voltage.py` | Coil-voltage estimates, envelope bound, Table 18 interpolation, shorted-coil currents |
| `plot_region.py` → `stud-region.png` | Per-layer copper map around J2/J5 |
| `rerun-native21-in-r4.json` | Repo fit-gate re-run (L outline) |
| `evidence.txt` | Output of every script |
| `src/` | IEC 60335-1:2020 sample text (clause 29, Tables 15–18), Würth 74650074 drawing |
