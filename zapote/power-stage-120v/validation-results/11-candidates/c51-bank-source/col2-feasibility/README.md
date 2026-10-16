# Second bank column for O6 (28 A from stock): not feasible on the s51 floorplan

Read-only study on the s51 lane board 9afc509b (`c51/section.kicad_pcb`), 2026-10-16. Plan view:
`bank-col2-plan.png` (KiCad plotter, proposed outlines on a scratch copy). Scripts in `scripts/`
(dump, occupy, dist, heightmap, composite, annotate); measurements in `dist_c*.json`, `heightmap.json`.

**Verdict: no place for a 5-body column 2.** Option O6 (`../README.md` "28 A options": 10 × R76UR24704030J
+ 1 × B32654A2333K000, 0.503 µF) needs 11 bodies; the bank slot holds at most 6 bodies of about 11 mm.

- No free 33 × 58 mm rectangle anywhere (largest near the bank: 55 × 33 at x 100.5–155.5, y 9.5–50.5).
- Right (x > 193): 9.4 mm to C5, SELV spur, U36, C3/C4. Left (x < 161): 23 mm to J5/J2/T1. Below: 19 mm to the
  edge, SELV islands, line_zc_raw, J6, H8/H10.
- Above (y 0–50, x 100–213) is the only corridor from the FET/BR1 edge to the board: AC pair, sw_a, the sw_b feed
  and the hv_ret / bus_p trunks. A res_a pin column at 11.5 mm pitch is a wall on every layer
  (11.5 − 2.4 − 2 × 5.0 = −0.9 mm).
  - Standard orientation: H7 (frozen to the enclosure) 3.1 mm from the sw_b pins; trunks and AC pair cut.
  - Rotated: sw_a (Q2 → T1) has no path; rotated flow is outside the bank_air model (est. strict gate ≈ 0.98);
    pads est. 79–92 °C against KEMET's ~92 °C.
- One long column: needs 56.5 mm more span; split 8 + 3 / 7 + 4 also fail (PS2 courtyard, H9–H7 gap).
- Bottom side: 14.5 mm under the board against R76's 20 mm.
- Column 1 alone at 11.5 mm pitch (6 bodies) fits (courtyard y 47.2–119.2) with an In1 n_ls / v24_raw reroute;
  bottom res_a hole to the In1 v3v3 / In2 selv_gnd islands 9.515 mm (C152 today 8.325 mm).
- A second column is a re-floorplan of the y 0–50 corridor (PS2, AC pair, sw_a, sw_b, trunks, R22–R25, possibly
  H7/H9 = an enclosure change): roughly 4–6 stages. Spine lock (x 30–110, y 130–180) unaffected.
