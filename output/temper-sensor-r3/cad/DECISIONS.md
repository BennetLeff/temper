# CAD decisions: C1 cartridge (sensor-r3)

## Interface changes for PCB/firmware

These change the shared spec (`HANDOFF.md` "What C1 is") or answer `pcb/DECISIONS.md` "For the CAD agent" and its "CAD interface check".

| # | Item | CAD decision | Effect on the other agents |
|---|---|---|---|
| I1 | Hot-zone lead insulation (PCB conflict 1: ≥ 10 MΩ at 300 °C; no PTFE above 260 °C) | **Resolved with separate bores.** A fused-silica 4-bore capillary (OD 1.0, bores on a 0.30 pitch) carries one **bare** manganin Ø0.08 wire per bore, from 0.5 mm below the chip down to the post foot (Z98.3–108.58). Quartz volume resistivity is ≥ 7e7 Ω·cm at 350 °C (UQG sheet, the lowest found), which gives ~100 MΩ between bores over 10 mm. The polyimide enamel (MW 16-C, 240 °C) is used only below the capillary, where the model has it ≤ 210.7 °C (`thermal-axisym.json`, foot potting). The PTFE lead sleeve runs only below the foot, at ≤ 201 °C. The two Kelvin joints (IST Ni lead to two manganin wires each) sit 0.3 mm above the capillary top, ≥ 0.3 mm apart, inside the sealed, fibre-filled post. | PCB fault check: insulation ≥ 10 MΩ holds by construction. The supplier must confirm a quartz 4-bore at OD 1.0 (`QUOTE-LIST.md`). The alternate is 99.7 % alumina 4-bore. |
| I2 | Lead pairing and twist (PCB: S+ with S−, F+ with F−; pitch ≤ 5 mm) | S+/S− share adjacent bores, as do F+/F−. Inside the capillary (10.3 mm) the wires are **straight, not twisted**, because each has its own bore. Their loop lies in a plane through the coil axis, so only B_r threads it. Pickup is 0.077 mV at the study-06 field; scaled to 20 mT and 100 kHz it is ~0.31 mV (`field-screen.json` `capillary_pair_pickup`). That is well under the PCB's 6.6 mV twisted bound. The pairs are twisted at ≤ 5 mm pitch below the capillary, inside the PTFE sleeve. | Deviation from "twist pitch ≤ 5 mm" over 10.3 mm, with a bounded pickup. PCB to accept or object. |
| I3 | Splices | All four manganin-to-pigtail splices sit at one height, in the potted splice cup Z75–80 (Duralco 128, modelled ≤ 148.4 °C). | As requested. |
| I4 | Pigtail | 6 × M22759/12-26, three twisted pairs, in a Ø3.4 bundle allocation through a bonded PEEK strain relief. The allocation fits wires up to Ø1.13. The M22759/12-26 OD is **not confirmed (open)**. The strain-relief bore is re-cut to the measured bundle. | Matches PCB D8. |
| I5 | Inline Micro-Fit 3.0 2×3 | Modelled at (135, 285, 62). It sits under the carrier on the R32 RTD route (Z62), r 137 from the coil axis, outside the Ø247 former. It is 35.4 mm from the ferrite and 36.7 mm from the winding (`checks.json` G11), against the ≥ 8 mm required. The air there is the base-compartment intake air, ≤ 50 °C (R43 `evidence/airflow-r32/coil_thermal.py` T_in cases), within the 85 °C limit. That air temperature is not computed in this folder; it is carried from R43 → **bench EM2 thermocouple to confirm**. Reach with the cover lifted is open: the cartridge drops through the carrier from above, but the connector sits under the carrier, so the harness owner must route about 150 mm of pigtail slack so it can be unplugged once the cartridge is lifted out. | The ≥ 150 °C connector fallback is not needed if the bench confirms the air temperature. |
| I6 | Pinout | `pcb/CHANGE-REQUEST.md` §4 is adopted as is. The drain is not carried into the cartridge. | None |
| I7 | Body material | The body changes from R43's PEEK to **Vespel SP-1 polyimide**. Its collar reaches 256.4–257.9 °C, above PEEK 450G's 240 °C mechanical RTI. | None for the PCB. Cost: see `QUOTE-LIST.md`. |
| I8 | Stroke | 2.2 mm to the hard stop (min 2.11 after tolerances), not just ≥ 1.2. A 1 kg ball needs 2.03 mm to land on the glass (G6). | Firmware: the contact-check travel range. |
| I9 | Firmware G_leak / sink model | Cold-side leak G_cold is 0.32 mW/K (0.39 with fibre k 0.08 and FFKM k 0.30). Hot-side G_hot, to the collar and pan side, is 4.6–4.9 mW/K. The hot side is not a leak to a cold sink; it sits near pan temperature. C_cap is 39.2 mJ/K by the budget method and ~45.4 by the effusivity estimate at τ_ref 1 s. τ63 is 1.10 s at h 888 and 0.79 s at h 1300 (`budget-asbuilt.json`). | Firmware: calibrate C_cap within 39–46 mJ/K. |
| I10 | Glass | Thickness **4.00 ± 0.03 within Ø40 of the bore** must go on the glass RFQ. CERAN thickness tolerance is unpublished. Without it the G2 chain is not closed. | Owner of the glass RFQ. |
| I11 | Rim NTC, cable count, disc, post envelope | Unchanged from the shared spec | None |

## Decisions

**D1. Tool.** I used build123d 0.11.1, not CadQuery. Both run on the same OCCT kernel, and build123d is what the R43 sources use. The STEPs are OCCT exports.

**D2. Post: integral inner support tube.** An unbacked Ø7.5 span gives 392 MPa at 20 N, which is SF 1.8 and fails G6. An inner Ø3.8/Ø3.4 tube, machined from the same blank, backs the disc around the chip pocket: 298.7 MPa, SF 2.34 (`budget-asbuilt.json`). It adds 0.126 mW/K to the hand bound into the post. The FV cold leak still passes at 0.32–0.39 mW/K.

**D3. Guide: three pads, not a full land.** A full Ø8.10 land at 0.05 radial gap coupled the neck to the hot collar. The model gave G_hot up to 34 mW/K, which buries the disc in its own collar. Three pads, 0.6 mm wide at 90/210/330°, keep the rocking pivot 0.75 below the disc face and cut G_hot to 4.6–4.9 mW/K. They are rigid pads, not slots or pins (P1).

**D4. Stroke and hard stop.** The hard stop is 2.2 mm: the cup pilot landing on the PEEK washer's stop tube. The ball-drop reasoning (G6) needs 2.03. The spring is specified by two loads, 1.30 N at rest and 1.70 N at the hard stop, ±0.08 N each. That keeps 1.21–1.79 N over the whole stroke.

**D5. Wiper: FFKM (Kalrez 6230), not PTFE.** The handoff allows PTFE at ≤ 250 °C, and the lip tip now models at 241.3 °C (part max 243.5). FFKM is kept anyway:
- An unenergised PTFE lip takes a permanent set near 240–250 °C, so its interference is gone after the first hot cycles.
- A metal energiser is not allowed in the eye (G7).
- FFKM is elastic, with a 260 °C maximum application temperature and FDA 21 CFR 177.2600.
- Friction stays ≤ 0.185 N even with a dry μ of 1.0.

**D6. Polymers by temperature.**
- Body, post and stop collar are polyimide; the post top models at 259.8 °C.
- The cup (200.8 °C), washer (180.3 °C) and strain relief (148.2 °C) are PEEK 450G, within its 240 °C mechanical RTI.

**D7. Spring alloy: A-286, not 316.** The spring models at 192.1 °C. That leaves 316 only 12 K below its 204 °C relaxation limit. A-286 is rated 538 °C. Eddy heating at the study-06 eye field is 0.69 K.

**D8. Hot-zone insulation: fused-silica capillary.** This answers PCB conflict 1 (I1 above). It adds ~0.09 mW/K into the post (hand bound). Glass-fibre sleeving was rejected: it does not fit four Ø0.08 wires in the Ø1.2 lead bore with a defined spacing.

**D9. Manganin.** Adopted, as the PCB requested. Its k is equal to constantan's.

**D10. Bond: EPO-TEK 930-4 stays the choice, but G8 is OPEN.**
- 930-4 publishes only "< 325 °C intermittent". A continuous ≥ 260 °C statement from Epoxy Technology is needed.
- The alternate, Duralco 128 (k ≈ 4.3, 10^15 Ω·cm), is rated 260 °C. That is zero margin at a 259.9 °C bond.
- No rated choice exists yet. This is recorded, not hidden.

**D11. Vespel SP-1 RTI is OPEN.** The continuous 288 °C rating is a distributor figure. DuPont's UL file E530329 exists, but I have not read its RTI values. To close it, get a DuPont statement or the UL iQ entry. The body is not an insulation barrier in G11, because no solid insulation is credited, so the RTI matters only for mechanical holding.

**D12. G2 tolerance chain.**
- The cartridge contributes ±0.06: neck ±0.015, glue ±0.01, stop collar ±0.02, disc ±0.015.
- The glass contributes ±0.03, which needs I10.
- Total ±0.09, inside the ±0.10 band.
- The stop collar is set by fixture, not by machined stack, because a machined stack would add ±0.04.

**D13. Sump instead of a drain.** A drain from the eye would have to cross the coil zone. Instead, the body bore below the wiper is a sealed blind sump (G9). The bayonet slots are filled by the splice potting.

**D14. Up-stop: a bonded collar, not a snap ring.** A metal snap ring would add a conductive closed loop near the eye. Pins would violate P1. So the stop is a bonded Vespel collar.

**D15. No P1 conflicts arose.** No requirement needed a forbidden feature (G12 table in `checks.json`). The wiper lip (D5) slides; it does not flex to give the stroke. Counsel's item on US11378463B2's "flexible diaphragm" stays open in `PATENTS.md`.

**D16. Bayonet groove widened to Ø13.6.** At Ø13.2, the corners of the washer lugs (3.0 wide to r6.5, so the corner is at r6.67) cut the body by 0.049 mm³ (G1 rest pairwise). Ø13.6 clears them. The body wall there is still 1.2 mm.

**D17. G10 turn: the cartridge is held down while it turns.** The turn follows the R43 `check_assembly_sequence` bayonet poses: drop at +60°, then turn at Z0 with the hand holding the body 0.5 mm down on the wave spring. If the hand lets go mid-turn, the wave spring lifts the body. The only interference is then the R16 detent bump riding on the carrier underside: 0.72–0.84 mm³ of the 1.57 mm³ bump, and 0 with the bump removed. That is the detent doing its job. It drops into the carrier dimple at 0°, where the overlap is 0.

**D18. G11 floating wave spring.** The wave spring is the unchanged R43 part. Its straight distance to the tank parts is 7.42 mm to the coil lead and 7.43 mm to the winding. That passes the 3.0 mm clearance but is under the 8.0 mm creepage if the wave spring were itself a SELV conductor. It touches no SELV conductor. Its nearest SELV part is the NTC lead, 5.95 mm away through and around the polyimide body. The tank → wave spring → SELV path is therefore 13.37 mm, with both legs ≥ X = 1.5 mm (PD3), which passes under the 60664-1 floating-part rule. **Not credited:** any solid insulation. **Open for the safety reviewer:** whether UL 60335-1 accepts the floating-part sum here. If it does not, the fix is to move the wave spring 0.6 mm outward, which needs an R43 interface change. The main spring is 21.65 mm from the nearest tank part and passes directly.

**D19. G1 at travel 0 with tilt.** With the shoulder seated on the up-stop, a 5 mrad tilt about the pad pivot pushes the shoulder edge 0.026 mm into the collar: 0.17 mm³, accepted as a compliant pair. At travel 0 no pan is on the disc, so nothing tilts it. Seated, the post would rock about the shoulder edge. From travel 0.03 onward the shoulder is clear. The wiper lip (≤ 0.02 mm³) and the spring top coil (≤ 0.08 mm³) are the other two compliant pairs.

## Gate results

See `checks.json`, produced by `python checks.py`. The sub-scripts write `thermal-axisym.json`, `budget-asbuilt.json`, `tilt-follow.json` and `field-screen.json`.

Environment (same as R43; not in the repo `.venv`): `uv venv -p 3.12 cadenv && VIRTUAL_ENV=cadenv uv pip install build123d==0.11.1 ezdxf shapely pyvista scipy matplotlib`, then `cadenv/bin/python checks.py`.

Last full run: `python checks.py`, then `--only G1 G9 G10 G11` and `--only G8 G11` after D16–D18.

| Gate | Status | Numbers |
|---|---|---|
| G1 collisions | PASS | Travel 0 / 0.6 / 1.2 × tilt 0 / ±5 mrad about X and Y. Overlaps are only the three compliant pairs (D19): up-stop 0.17, spring top coil 0.08, wiper lip 0.02 mm³. All parts single valid solids. No fixed-part or R43-interface overlap. |
| G2 protrusion / stroke | PASS | 0.60 nominal, 0.51–0.69 worst case: cartridge ±0.06 plus glass ±0.03 (I10). Bore read from the R43 glass: r9.00. Stroke to the hard stop 2.2 (min 2.11). At the hard stop the disc is ≥ 1.42 below the glass top. |
| G3 C_cap | PASS | 39.2 mJ/K by the budget method (limit 45). The effusivity estimate is 45.4 (I9). |
| G4 cold leak | PASS | FV split: G_cold 0.32 mW/K, 0.39 with the sensitivity case (limit 0.8). Hand upper bound into the post: 0.86. |
| G5 tilt / spring / friction | PASS | Worst residual tilt 0.68 mrad (dry μ 1.0; 0.39 at μ 0.3), limit 2. Pivot 0.75 under the face. Spring 1.21–1.79 N, τ 317/490 MPa. Wiper friction 0.056 N (μ 0.3), 0.185 N (μ 1.0). |
| G6 disc | PASS | 298.7 MPa at 20 N over the Ø3.4 pocket, SF 2.34. Ball drop needs 2.03 mm of stroke; 2.11 is available. |
| G7 field | PASS | Only the chip and the capillary are inside Ø20 above the coil plane. Spring: 2.9 mW and 0.69 K at the FEM eye field; 11.3 K at the 20 mT / 100 kHz corner. Wave spring 0.09 W. Pair pickup 0.08 mV. |
| G8 ratings | **OPEN** | Every part is under its continuous rating; tightest are the gasket at 251.1 vs 260 and the wiper at 243.5 vs 260. **Open items:** a continuous rating for the bond (D10), and the Vespel SP-1 UL RTI (D11). PEEK parts are within RTI 240: the cup at 200.8 is the hottest. Micro-Fit at ≤ 50 °C air vs 85 °C. |
| G9 spill | PASS | Sealed sump of 2047 mm³ at full stroke (≥ 2000). Body intrusion 0. |
| G10 assembly | PASS | Drop plus 60° turn: 0 collisions. Cover off: lifted 0.5, detent in the dimple, 0 overlap. Cover on: glass lowered from +30, 0 collisions. Detent ride per D17. |
| G11 insulation | PASS | Worst SELV-envelope straight distance: rim NTC to the winding, 13.13 mm (≥ 8). Wave spring per D18: 7.42 direct, 13.37 series. Connector ≥ 35.4 mm from the tank. |
| G12 P1 | PASS | Part-by-part table in `checks.json`; no rule hit. |
