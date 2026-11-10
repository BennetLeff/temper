# Rev G100 independent layout review — 2026-11-10

Reviewer: independent senior PCB layout pass on the frozen export `build/rev-g100-review-2026-11-10/`.
Board file sha256 `4911a3cb…` (the one the evidence files cite). KiCad 10.0.4. Every number below was re-derived
by a script in `work/`; the script and its output file are named at each finding. Coordinates are KiCad mm
(outline x 50–150, y 45–145, y grows south; the BNC row is north). `prior/` was opened only after the sections
up to "Checked and found fine" were written; the last section is the comparison.

## Verdict: ORDERABLE

No BLOCKER and no MAJOR. Two conditions belong on the order, not on the copper:

1. **Select "Plugged" via covering on the JLC order** (fab note 4 already intends it, but words it as "plugged
   from the bottom only", which is not a JLC option). Every exposed-pad thermal via on U1 / U11 / U12 / U13 / U14
   sits under a paste window; with the default "Tented" covering the barrels are open under paste (m1).
2. **The JLC placement preview is a hard gate** for the 78 polarised parts whose CPL rotation rests on the
   "EasyEDA pad-number audit" (n9). That is already the project's listed step.

The one item the earlier reviews fought over, the 0.2 mm USB_VBUS neck at J1's A4/B9 pads, fails the intent's
rule as literally written (an infinite 0.2 mm trace at 1.17 A runs 22–28 °C hot) but is a 4.3 mm neck anchored by
the connector pad and 0.4–0.5 mm copper at each end; a 1-D fin estimate puts its peak at ≈ 3 °C above its ends,
≤ 10 °C in any real case. I rate it MINOR (m0) and ask for the intent and the evidence text to be made consistent
with the copper, because today they contradict each other (see "Against the earlier reviews").

Everything else: DRC is clean on the board's rules and on JLC's limits; the shipped Gerber / drill / IPC-356 set is
a byte-identical re-export of the board; the netlist matches `design.json` pin for pin; the analog core and jack
band are Rev G's copper to the micron; In1 is one solid plane except the deliberate Rev G voids; every
intent-specific requirement (TVS vias, LDO pin-4 bridges, D29 and its vias, two 5V vias at U16, no VBUS under the
J1 shell, TP8/TP9/TP22 placement, button and LED access) is met.

---

## BLOCKER

None.

## MAJOR

None.

## MINOR

### m0. USB_VBUS A4/B9 exit is 0.2 mm wide for 4.3 mm; the intent, the evidence and the copper disagree

- **Where:** F.Cu, net USB_VBUS, from pad J1.A4/B9 (centre 57.67, 129.60; the pad spans x 57.10–58.24,
  y 129.30–129.90 because J1 is rotated −90°) east to (58.29, 129.60), north along x = 58.49 from y 129.12 to
  127.45, then diagonally to the via at (57.20, 126.20). Five segments, all 0.20 mm, 4.3 mm in total. From the
  via on, the trunk is 0.5 mm B.Cu and 0.4 mm F.Cu to U16.
- **Evidence:** `work/path_trace.py` → `work/path_trace.txt` (widest-bottleneck path J1.A4 → U16.1 bottlenecks at
  those five segments); `work/supply_current.py` → `work/supply_current.txt`; `work/followups.txt` (pad boxes and
  the fix corridor).
- **Arithmetic, as the intent words it** (each VBUS pin pair its own 1.17 A source, ≤ 10 °C):
  - Cross-section 0.20 mm × 35 µm = 7.87 mil × 1.378 mil = 10.85 mil².
  - IPC-2152 fit the project uses, `A = (117.555·ΔT^-0.913 + 1.15)·I^(0.84·ΔT^-0.108 + 1.159)`: at 1.17 A and
    10 °C it needs 20.6 mil² (0.38 mm outer); solving it for 10.85 mil² gives ΔT ≈ 22 °C.
  - IPC-2221 external, `I = 0.048·ΔT^0.44·A^0.725`: 10.85 mil² carries 0.048 × 2.754 × 5.63 = 0.74 A at 10 °C;
    at 1.17 A, ΔT = 10 × (1.17/0.74)^(1/0.44) ≈ 28 °C.
  - So by the letter of the intent the single-pair case fails, and `evidence/current_check.json` passes it only
    because its solver tied all of J1's VBUS pins into one source: it reports this segment and the via
    (57.20, 126.20) at 0.747 A and the other pair's via (61.225, 135.90) at 0.423 A (sum 1.17 A), while its own
    method text says "each receptacle VBUS pin is a separate source case". The JSON contradicts itself.
- **Arithmetic, as the copper actually behaves.** The IPC curves are for a long trace. This is a 4.3 mm neck
  whose south end is the J1 pad (soldered to a connector whose shell is a heat sink) and whose north end is
  0.5 mm B.Cu via a 0.3 mm barrel. One-dimensional fin: the thermal length of a 0.2 mm 1 oz trace is
  L = √(k·A / G′) with k·A = 400 W/m·K × 7e-9 m² = 2.8e-6 W·m/K and G′ from the IPC-2221 point itself
  (0.74 A → P′ = I²·ρ/A = 0.548 × 2.46 Ω/m = 1.35 W/m at 10 °C → G′ = 0.135 W/m·K), so L = 4.6 mm. For a neck of
  half-length a = 2.15 mm with its ends held at the end temperature, the peak rise above the ends is
  ΔT∞ × (1 − 1/cosh(a/L)) = ΔT∞ × (1 − 1/1.112) = 0.10 × ΔT∞ ≈ 2.8 °C (IPC-2221) or 2.2 °C (IPC-2152). Even with
  the north end at the 0.4 mm copper's own infinite-trace figure (≈ 9 °C at 1.17 A) the peak is ≈ 12 °C, and the
  In1 plane 0.2 mm below (which G′ ignores) only lowers it. The current flows only in a downstream short at the
  TPS2553's limit, until its thermal shutdown. Thermally benign.
- **Room to widen.** The GND pad A1/B12 spans x 57.10–58.24 and the CC1 track runs at x = 58.86 (west edge
  58.76): a 0.52 mm corridor, so a 0.2 mm track at the 0.15 mm rule is the most that fits from y 129.6 up to
  the shell pad's north edge at y 127.17 (2.4 mm) — the designer's "no room" is right there. North of
  y 127.17 the corridor opens: the last 1.9 mm (58.49, 127.45) → (57.20, 126.20) can be 0.4 mm, or the via can
  move to ≈ (58.49, 127.0) with a 0.5 mm B.Cu link to the feed at y 126.2. That shortens the neck to 2.4 mm
  (peak ≈ 1 °C above its ends). Optional.
- **Disposition I ask for:** either shorten the neck as above when the area is next touched, or leave the
  copper and (a) amend `intent/README.md` so the VBUS rule reads "J1's four VBUS contacts are one source"
  with the double-fault reasoning, and (b) correct the `current_check.py` method text in the evidence so the
  report no longer claims a per-pin case it does not run. Today the three artefacts disagree and a later
  reviewer will trip over it again, as three already have.

### m1. Paste apertures sit directly on the exposed-pad thermal vias

- **Where:** U13 (137.5, 135.0): all 9 EP vias inside 0.66 mm paste sub-pads; U14 (64.0, 98.5): 4 of 4 inside
  0.94 mm sub-pads; U11 / U12 (130/143, 110): 4 of 6 inside 0.63 × 0.76 sub-pads; U1 (74.0, 133.5): 3 of 8 inside
  1.29 mm sub-pads. All vias 0.30 mm drill, tenting flag set both sides.
- **Evidence:** `work/ep_vias_paste.py` → `work/ep_vias_paste.txt`.
- **Why it matters:** with JLC's "Tented" covering the barrel is open under the paste and solder wicks through
  (voids under the EP, solder balls on B.Cu). It is acceptable with "Plugged" (mask ink in the barrel), which
  fab note 4 intends; but the note's wording ("plugged from the bottom only, top lands left clean") is not a JLC
  option and will be ignored. The order form decides.
- **Fix:** select "Plugged" on the order and reword fab note 4 to say exactly that; or, better craft, shift the
  paste windows by half a window so no barrel is under paste while keeping 50–60 % EP coverage.

### m2. Relay RESET margin is 24 mV; the VRLY / RLY_RST copper is a free ≈ 20 mV

- **Where:** VRLY trunk In2.Cu 0.20 mm from (100.0, 113.6) to (100.0, 71.0) (42.6 mm, taps to K3/K2/K1) and
  (100.0, 113.6) → (131.4, 113.6) (31.4 mm, to K4); RLY_RST return 104.8 mm of 0.20 mm on F.Cu / B.Cu.
- **Evidence:** `evidence/drive-budget.json` (the designer's): coil voltage during the RESET pulse at VBUS 4.40 V
  is 4.149 V against 4.125 V must-operate at a 45 °C relay — margin 0.024 V. `work/lengths.txt` for the lengths.
- **Arithmetic:** 0.20 mm × 17.5 µm (0.5 oz) = 3.5e-9 m²; ρ = 1.72e-8 Ω·m → 4.9 Ω/m. Four 28.1 mA RESET coils
  (112 mA) tap off the In2 trunk: 13.7 mm at 84 mA (0.067 Ω, 5.6 mV) + 15 mm at 56 mA (4.1 mV) + 15 mm at
  28 mA (2.1 mV) ≈ 12 mV to K1 plus the F/B.Cu stubs; the project's own figures are 18 mV (VRLY) + 16 mV
  (RLY_RST).
- **Fix:** widen the VRLY In2 runs to 0.5 mm (nothing is within 0.5 mm of them on In2 along x = 100) and the
  shared RLY_RST segments at Q2 to 0.4 mm: ≈ 20 mV back, doubling the margin, no circuit change. The bring-up
  plan's R101 → 0 Ω rework stays as the fallback.

### m3. B.Cu GND pour reaches 0.2 mm from the H3 / H4 unplated hole walls

- **Where:** B.Cu and In2.Cu GND pour around H3 (54, 141) and H4 (146, 141): pour edge 1.80 mm from the hole
  centre, hole radius 1.60 mm. The intent asks for B.Cu copper ≥ 3.5 mm from the hole centres "or flag it".
- **Evidence:** `work/hole_pour.txt`; `work/mech.txt` (no non-GND B.Cu copper within 3.5 mm of any hole; the
  only other item is JK_HPOT B.Cu at exactly 3.50 mm from H2).
- **Why it matters:** 0.2 mm is JLC's NPTH-to-copper minimum; drill wander exposes copper at the hole wall under
  a standoff. It is GND, so the consequence is chassis-to-GND contact, not a short. Flagged as the intent asks.
- **Fix:** a 3.5 mm-radius B.Cu copper keep-out at H3 / H4, or a 0.5 mm pad clearance on the hole footprint; or
  record the insulating-standoff decision in the intent so the 3.5 mm rule stops asking.

### m4. Crystal is 7 mm from the RP2040 and XOUT changes layer twice

- **Where:** Y1 at (75.0, 123.0); U1 XIN / XOUT pins at (74.6 / 74.2, 130.06). XIN 11.1 mm F.Cu. XOUT: via
  (74.13, 131.05) → In2 5.4 mm → via (71.90, 123.80) → R10 → XTAL_OUT. C12 7.7 mm from pin 20.
- **Evidence:** `work/signals.py` → `work/signals.txt`; `work/lengths.txt`.
- **Why it matters:** the RP2040 hardware guide §2.3 asks for small trace capacitance: ≈ 1 pF per 10 mm of
  0.2 mm track over a 0.2 mm dielectric on both legs, against 15 pF load parts for CL = 10 pF. It will
  oscillate; it is further from the pins than it needs to be, with two vias in the loop. Inherited from Rev F/G.
- **Fix:** if J4 / TP22 can move 3 mm east, Y1 and C12 / C13 fit under pins 20 / 21 with no vias. Else accept.

### m5. R13 (QSPI CLK series) sits mid-run, not at the U1 end

- **Where:** U1.52 (75.00, 136.94) → R13.1 (74.33, 143.50) 7.1 mm; R13.2 → U2.6 (65.69, 142.09) 7.7 mm.
- **Evidence:** `work/intent_items.txt`.
- **Why it matters:** the intent says "R13 at the U1 end". At ~1 ns edges 7 mm is ≈ 47 ps, so the source
  termination still works; it is an intent deviation, not a performance problem.
- **Fix:** swap R13 into R7 / C10's spot at ≈ (74, 139), or accept and record it.

### m6. USB D+ / D− are not a pair: 6.4 mm mismatch, different layers, 4 vs 2 vias

- **Where:** USB_DP 37.0 mm (F 9.8 / In2 13.0 / B 14.2, 4 vias), USB_DM 43.4 mm (F 27.8 / B 15.6, 2 vias), plus
  7.8 / 8.3 mm on the `_MCU` side of R3 / R4. DM detours north to y = 124.2 around J1's CC pads. Closest
  neighbours: DP to RUN on In2 0.29 mm at (65.9, 132.5); DM to CC1 0.18 mm at (58.29, 131.25). D1 (SRV05-4) is
  flow-through at (63.0, 132.0).
- **Evidence:** `work/lengths.txt`; `work/signals.txt`.
- **Arithmetic:** FR-4 εr ≈ 4.3 → 6.9 ps/mm; 6.4 mm → 44 ps skew < 100 ps Full-Speed limit. 0.2 mm singles over
  a 0.2 mm dielectric are ≈ 60 Ω single-ended, far from 90 Ω differential — but so is every Pico.
- **Fix:** none required for FS; if touched, run DM beside DP on In2 from (59.6, 131.9) to (65.9, 137.9).

### m7. TPS65131 small-signal input and VNEG output capacitors are further than "as close as possible"

- **Where:** C81 (CONV_VIN 100 nF) at (141.5, 140.0), 5.3 mm from U13.4 (137.75, 136.99). C91 / C92 (RAW_N
  10 µF) at (140.5 / 144.5, 122.0), 9.9 mm from U13.15 (137.75, 133.01). C89 / C90 (RAW_P) 9.6 mm from U13.23 but
  3.7 mm from D2's cathode, where the boost hot loop closes. C85 (CN) GND pad 2.35 mm from its via. L2.2 (GND)
  returns through a 4.6 mm 0.5 mm stub.
- **Evidence:** `work/switcher.py` → `work/switcher.txt`; `work/decoupling.txt`; `work/gnd_stubs.txt`.
- **Why it matters:** datasheet §9.1: "input capacitors (C1, C2, C3), output capacitors (C4, C5) … as close as
  possible". Both hot loops run over the solid In1 plane 0.2 mm below F.Cu, so the enclosed area is ≈ path ×
  0.2 mm (≈ 5 mm² for the inverter loop C82 → INN → SW_N → D3 → C91 → plane); the VNEG loop is 24 mm long. The
  feedback nets come within 1.0 mm of the SW nodes only at the U13 pins themselves. Victims are ≥ 55 mm away.
- **Fix:** C81 fits at (139.5, 138.5) beside C83; C91 can move to (140.5, 124.5) if D3 moves 1 mm south.
  Otherwise accept and keep the bring-up scope check on SW_P / SW_N.

### m8. 0.12 mm silkscreen lines on footprint outlines (JLC minimum 0.15 mm)

- **Where:** 762 footprint silk graphics (KiCad library outlines) at 0.12 mm; all text is 1.0 mm / 0.15 mm.
- **Evidence:** `work/mech.txt`.
- **Why it matters:** JLC prints them but says lines < 0.15 mm may be illegible; the polarity bars on D2 / D3 /
  D29 and the LED cathode marks are among them. Not a build risk.
- **Fix:** bulk-set footprint silk line width to 0.15 mm, or accept.

### m9. Craft-rule deviations not listed in `craft_exceptions`

- **Evidence:** `work/craft.py` → `work/craft.txt`; `work/followups.txt`. T-junctions: 0. Bends off the 45° grid
  outside pads with both legs > 0.3 mm: 174, nearly all two-step ≈ 110–160° chamfers in the re-routed south
  (e.g. 3V3 F.Cu (68.00, 131.78) / (67.22, 131.50) 109.5°; USB_VBUS (58.49, 129.12) 157°). Pad entries off-axis
  or off-centre: 12 — C74.2 (77.45, 88.67), C75.2 (77.45, 94.33), C77.2 (77.45, 106.53) 0.51 mm off-centre at 45°
  in Rev G copper; C65.1 (59.17, 100.58) 0.34 mm, SW1.2 (89.85, 138.00) 0.27 mm, C110.1 (91.78, 136.68) 0.34 mm
  off-centre in new copper; U13.25, U11.9, U12.9, C3.1, SW2.1 diagonal through the centre. Dangling ends: 3 —
  USB_VBUS F.Cu (60.075, 115.05) 0.37 mm past C113.1; RUN (84.375, 141.90) past SW2.1; LDOIN_N (145.43, 111.25)
  0.28 mm past U12.5.
- **Fix:** list them in `craft_exceptions` with a reason, trim the three stubs, or re-enter the three new
  off-centre pads along the axis.

### m10. Decoupling that is further than it needs to be

- U1 1V1: C9 5.8 mm from pin 23; C8 4.6 / 6.1 mm from pins 45 / 50 (guide §2.1.3: 1 µF close to VREG_IN and
  VREG_OUT). U1 IOVDD pins 1 / 10: C6 / C2 at 3.8 mm. U3 output cap C17's GND pad returns through a 3.2 mm
  0.3 mm track to the via at U3.2 (acceptable, it ties to the LDO's GND). U16 C15 2.8 mm from pin 3 ("as close
  as possible") with a 1.9 mm GND stub. U14 IOVDD C65 2.95 mm from pin 6.
- **Evidence:** `work/decoupling.txt`, `work/gnd_stubs.txt`.
- **Fix:** C9 fits at (71.5, 128.3) under pin 23's exit; C15 at (58.2, 114.0). Otherwise accept (Rev F carry-over
  for U1).

## NOTE

- **n1. 5V single via at (54.46, 99.60) carries the full 1.17 A fault to FB1 / U15.** Barrel π × 0.30 × 0.018 mm²
  = 26.3 mil²; IPC-2152 fit → 1.34 A at 10 °C, so ≈ 7.7 °C at 1.17 A (IPC-2221 internal would say 0.71 A). Add a
  twin if convenient. `work/supply_current.txt`.
- **n2. The project's current check omits 3V3A, 5VA, LDOIN_P / LDOIN_N and VRLY.** 3V3A on In2 at 0.20 mm (23 mm):
  0.2 mm × 0.5 oz = 5.4 mil² → 0.56 A at 10 °C by IPC-2152 against the AP2112's 0.6 A rating (≈ 11.5 °C). Only a
  codec-AVDD short draws it.
- **n3. 5V In2 trunk (1.6 mm) at 0.40 mm from the back edge and 0.40 mm from the H3 hole wall.** Meets JLC (0.2)
  and the fab note (0.4). By IPC-2221 internal 1.6 mm × 0.5 oz carries 1.0 A at 10 °C (≈ 14 °C at 1.17 A); by
  IPC-2152, which the intent names, 0.76 mm suffices. Accepted as the intent states.
- **n4. J1 overhang vs the left-edge V-cut rail** (fab notes 6 / 7): the rail is coplanar with the board, so the
  0.2 mm shell lip rests on it; harmless, confirm in the assembly preview.
- **n5. Tombstoning:** C16 (0805, 5V/GND) sees 1.5 mm of copper on pad 1 vs 0.2 mm on pad 2; C113 1.2 vs 0.4.
  0805 is tolerant; no 0402 / 0603 asymmetry found. `work/padgap_tombstone.txt`.
- **n6. Sixteen 45° same-net junctions** (e.g. GND F.Cu (76.78, 75.50) 55°, 3V3 (58.95, 103.70) 45°, USB_VBUS
  B.Cu (57.20, 126.20) 45°): acid-trap candidates in theory, harmless with modern etch. `work/signals.txt`.
- **n7. References:** 73 designators are not on silk (TPs, fiducials, holes, tight passives, U13, U16, J1) — on
  F.Fab as the intent allows. J3 / J7 / J8 / J9, K1–K4, D4 and U14 carry no F.Fab reference in the board file;
  `renders/assembly-top.png` shows them because `assembly_preview.py` adds them. `work/followups.txt`.
- **n8. CPL rotations:** 78 polarised parts rely on "LCSC EasyEDA pad-number audit; final JLC preview required"
  (`orientation-audit.csv`). The offsets are internally consistent (SOT-23-5 +270, SOT-23-6 +180 for the TI
  parts, HVSSOP +270, SOT-23 +180, VQFN 0) but I could not re-derive them against EasyEDA. Preview is the gate.
- **n9. Thermal (arithmetic):** U11 (14.74 − 11.36 V) × 36 mA = 0.12 W, DGN high-K θJA ≈ 55 °C/W → +7 °C; U12
  (14.81 − 11.55) × 40 mA = 0.13 W → +7 °C; U13 Pout ≈ 14.2 V × 76 mA = 1.08 W, η ≈ 0.8 → 0.27 W × 34.1 °C/W =
  +9 °C; U16 0.45 A² × 0.135 Ω = 0.03 W; U3 (5 − 3.3) × ~0.1 A = 0.17 W in SOT-23-5 (θJA ≈ 250 °C/W) → +43 °C,
  the warmest part and unchanged from Rev G. EP via counts U1 8, U13 9, U11 / U12 6, U14 4.
- **n10. Hot-plug copper:** J1.A4 → U16 is 14.6 mm of 0.2–0.5 mm track over a 0.2 mm dielectric,
  L′ ≈ µ0·h/w ≈ 0.6 nH/mm → ≈ 9 nH, < 1 % of the 0.3–1.5 µH cable range swept in `hotplug-spice.json` (worst
  6.25 V < 6.5 V). Not re-simulated.
- **n11. Fab note 5 drill counts** (41 + 27 + 367 vias, 4 slots, 2 + 4 + 16 PTH, 2 + 4 NPTH = 467) match the drill
  files and `drill-report.txt` exactly.

---

## Checked and found fine

- **DRC:** board rules (`work/drc.json`): 0 errors, 0 unconnected, 0 schematic-parity issues; the 199 warnings
  are library-lookup notices. JLC limits applied as rules on a scratch copy (`work/jlc-drc/drc-jlc.json`:
  clearance 0.09, track 0.09, via ring 0.05, hole-to-hole 0.2, edge 0.2, silk-to-pad 0.15, text 1.0 / 0.15):
  clean.
- **Gerber set vs fresh export** (`work/gerber_compare.sh` → `work/gerber_compare.txt`): F / In1 / In2 / B copper,
  both masks, paste, edge, User.Drawings, job file, NPTH drill and IPC-D-356 (0 diff lines) are byte-identical
  modulo dates. PTH drill differs only in slot syntax (shipped routed G00 / M15, fresh G85; both JLC-readable).
  Silk differs only because my export subtracted the mask.
- **Netlist vs design.json** (`work/netlist_vs_design.txt`): 253 parts, 0 pin mismatches; the 29 extra board
  footprints are TPs, fiducials and holes.
- **Rev G copper** (`work/revg_compare.txt`): for y < 107 every signal-net track and via is identical to Rev G;
  the only differences are the documented additions (TVS GND vias, LDO pin-4 bridges, D29 and its vias,
  3V3 / −12V stubs) and three In2 runs (JACK_HC, JACK_LC, STATUS) whose south endpoints moved. Value changes are
  exactly the intent's list; J5 gone, TP22 and D29 added.
- **In1 plane** (`work/plane_voids.txt`): one outline; voids only at the deliberate Rev G windows (U5 10 × 8 mm,
  U7 / TIA 6.3 × 11.4 mm, U6 4.1 × 6.3 mm), the four M3 antipads and small via clusters. Nothing crosses a void
  except the nets that belong to it (TIA_SUM, DUT_LO, the amplifiers' ±12 V) and 1.2 mm of 3V3 over a
  via-cluster slot at (79.1–80.4, 128–135). Every B.Cu / In2 GND island has a stitching via.
- **Switcher vs victims** (`work/switcher.txt`): U13 / L1 / L2 / D2 / D3 are 55–90 mm from U7, U6, U14, U5 and
  the range resistors; nearest D3 → U7 54.6 mm. Hot loops close over the solid In1 plane; nine EP vias.
- **Decoupling that meets the datasheets:** OPA2810 §11.1 0.01 µF < 2.54 mm: U6 C50 1.85 / C51 1.65 mm, U7 C52
  1.80 / C53 1.77 mm, GND pads 0.9–1.2 mm from their vias. TPS7A49 / 30 §11.1: C95 / C97 and C100 / C102 same
  side, 1.9–3.1 mm; pin-4 → EP bridges on F.Cu at (127.85 → 129.00, 110.97) and (140.85 → 142.00, 110.97),
  0.25 mm. U14 AVDD C61 1.27 mm, VREF C62 1.72 mm. U17 C118 1.7 mm. U2 C11 1.9 mm at the VCC pin. TPS2553 RILIM
  R110 2.6 mm from pin 5.
- **Intent items** (`work/intent_items.txt`): D21–D24 each have two GND vias within 1.9 mm; U16 5V leaves on two
  vias (54.46, 117.75) / (55.06, 118.35); D29 at (137.9, 99.6), 4 mm from C100, with its −12V via (136.2, 97.6)
  and GND via (137.9, 103.6); only pad exits of USB_VBUS lie under J1's shell footprint.
- **Jack band** (`work/jackband.txt`): smallest gap from any jack-side net to any other net on any layer is
  0.15 mm (pin pitch at U6 / U7) and 0.20 mm elsewhere (JK_HCUR B.Cu at x 131.5 to the RLY_RST via (130.9, 70.9));
  IPC-2221 B4 needs 0.10 mm at 31–100 V, so ±50 V is covered 2×. JACK_HC / JACK_LC are 1.6 MΩ / 100 nF
  low-voltage sense nodes.
- **Return paths:** I2S (72 mm, 3 vias each), I2C, QSPI (7–31 mm) and USB all reference the solid In1; B.Cu / In2
  pours exist only south of y ≈ 108 and are stitched; no layer change in the digital area is further than
  1.6 mm from a GND via.
- **Supply widths otherwise** (`work/supply_current.txt`, `work/path_trace.txt`): 5V trunk U16 → U3 0.5 mm;
  U16 → L1 / C80 via B.Cu 0.6–1.0 mm and In2 1.6 mm; RAW_P / 12V / RAW_N / −12V at 0.2 mm carry 0.74 A outer /
  0.23 A inner at 10 °C by IPC-2221 against a 0.5 A fault (IPC-2152 needs 0.08 / 0.16 mm); 3V3 0.2–0.3 mm outer,
  0.27 mm In2 against 0.6 A (IPC-2152 0.11 / 0.23 mm).
- **Mechanical / assembly** (`work/mech.txt`, `work/padgap_tombstone.txt`): no copper pad of one part within
  0.30 mm of another part's pad; nothing but J1 (0.17 mm shell lip) and the four BNCs (hand-fitted; the front
  edge has no rail) crosses the outline; D4's pad is 0.40 mm from the front edge as fab note 8 promises; SW1 / SW2
  at (87.1, 138.9 / 142.9) have nothing taller than 1 mm within 10 mm; HB (D19) and FLT (D20) are 0603s on open
  board; TP8 (3V3) / TP9 (GND) 5 mm from the buttons; three 1 mm fiducials with 2 mm mask windows and copper
  keep-outs; no via touches a non-EP SMT land; mask webs ≥ 0.2 mm at the 0.4 mm QFN; bottom silk empty.
- **Silk legends:** "DISCHARGED DUT ONLY", HCUR / HPOT / LPOT / LCUR, rail and relay TP labels, revision string,
  all 1.0 mm; "+" on C117, bars on D2 / D3 / D29.
- **Teardrops** on (`teardrops: true`, 400+ teardrop zones present); **0 T-junctions**.

---

## Against the earlier reviews

Read after the above: `prior/FINDINGS.md` (the consolidated audit with dispositions),
`prior/independent-review-2026-11-09.md` (review 1), `prior/independent-review-2-2026-11-09.md` (review 2, with
the designer's dispositions) and `prior/independent-recheck-2026-11-09.md` (re-check of the 5V corner).

### Where they were right, and I confirm it on this export

- Review 1 B1 (stale Gerbers) was real at the time; the set in this export is a byte-identical re-export (0 diff
  lines on every copper / mask / paste / edge / drill / D-356 file). Closed.
- Review 2 M2 (0.9 mm In2 corner) and the re-check: the corner is 1.6 mm In2 with two vias at each end and
  B.Cu ≥ 3.5 mm from H3; my path trace and supply-width check agree.
- Review 2 m3 (549 DRC errors) was an export omission; with `temper-lcr.kicad_pro` present the DRC is 0 / 0 / 0.
- Review 1 M3 / review 2 n2 (12V 0.2 mm In2 jogs): the project's answer — IPC-2152 is the named standard, 0.5 A
  is a fault level — is right; the 0.23 A figure is IPC-2221's retired internal derate. I agree with the
  disposition.
- Reviews 1 and 2 on R13, the crystal, the USB pair, the silk line width, C15, references: same findings as
  mine (my lengths 37.0 / 43.4 mm are theirs minus the `_MCU` side of R3 / R4; same 44 ps skew).
- Re-check finding 3 (B.Cu 0.4 mm × 1.35 mm neck at (54.46, 116.4–117.75)) is a fair pre-existing note; the same
  fin argument as m0 applies to it.

### What they missed

1. **Paste windows directly over the EP thermal vias** (m1). Review 1 N7 and audit SL-9 note that the EP vias
   are the only vias on SMT lands and that "plugged" is allowed by the TI note, but nobody looked at the paste
   layer: every U13 / U14 EP via and most of the U1 / U11 / U12 ones sit under a paste aperture, and fab note 4
   asks JLC for a one-sided plug that is not an option. It is an order-form item, but it is the one thing on this
   board that can quietly cost yield, and it was not written down.
2. **The current check's scope and its internal contradiction.** `current_check.json` claims a per-pin VBUS source
   case in its method text and then reports 0.747 A on the A4/B9 neck, which only a one-node J1 produces. The
   FINDINGS table says "its docstring is corrected", but the evidence shipped in this export is the uncorrected
   version, so the claim and the number disagree. The check also never looks at 3V3A, 5VA, LDOIN_P / LDOIN_N or
   VRLY (n2); review 1 N4 saw LDOIN_P but not the rest.
3. **The relay RESET margin after the R101 fix is 24 mV** (4.149 V against 4.125 V at 45 °C, in the project's own
   `drive-budget.json`). RCG-01 asked for "R101 value, trunk"; only R101 changed. Nobody pointed out that the
   remaining margin is one resistor tolerance wide, or that widening the VRLY / RLY_RST copper buys ≈ 20 mV for
   free (m2). The bring-up ladder (R101 → 0 Ω, 4.5 V coils) is a rework plan for a margin a hand route could have
   restored before the order.
4. **The In2 1.6 mm run's 0.4 mm clearance to the H3 hole wall** is the same NPTH-wall exposure the re-check
   flagged for the GND pour; it was accepted silently because it meets JLC's 0.2. Fine, but it belongs in the
   same note (n3).
5. Three dangling stubs and the 174 two-step chamfers were partly seen (review 1 m2, review 2 m4) and
   dispositioned as "inherited style"; 95 of the bends and all three stubs are in the new copper, so the
   `craft_exceptions` list is still not the complete record the intent says it is (m9).

### What they got wrong

- Review 1 N4: "the 2152 chart wants ≈ 0.6 mm" for 1.17 A on 1 oz outer copper. The project's own IPC-2152 fit
  gives 20.6 mil² → 0.38 mm; 0.6 mm is the 0.5 oz inner figure (0.76 mm) misapplied. Not consequential.
- Review 1 M2 and review 2 M1 both proposed widening the A4/B9 neck to 0.4–0.45 mm "there is clear F.Cu east of
  the pad row". There is not: J1 is rotated −90°, the GND pad A1/B12 ends at x 58.24 and the CC1 track starts
  at x 58.76, a 0.52 mm corridor (`work/followups.txt`). I made the same mistake in my first draft. Only the last
  1.9 mm north of the shell pad can widen. The designer's "no room" was correct for the corridor.
- Review 1 claimed 2 T-junctions and a 23 µm I2S_DOUT segment; review 2 and I find 0 T-junctions (sub-µm endpoint
  rounding). Review 1 counted 74 off-centre entries; with the land-entry test the project uses and pads excluded
  I find 12.
- Review 2's "ORDERABLE" verdict with two MAJORs was self-contradictory under its own severity definitions;
  this review resolves that by rating m0 on the physics rather than the letter.

### Dispositions I disagree with, and why

- **G-PE-8 / review M2 / review 2 M1 — "Accepted: the intent's 'each pair is its own source case' overstated the
  requirement."** The engineering (a plug bonds all four VBUS contacts; 1.17 A needs a downstream short at the
  same time; the neck is thermally anchored) is sound and I reach the same conclusion by a different route (m0).
  What I disagree with is accepting it while leaving `intent/README.md` saying the opposite and shipping an
  evidence file whose method text says the opposite of what it computed. Three reviewers in a row have flagged
  this neck as MAJOR because the record told them to. Either change the two documents or shorten the neck; do
  not leave all three disagreeing.
- **MD-1 / MD-2 — "Accepted as a Rev F carry-over" (U1's 1 µF and 100 nF distances).** I measured C8 at 4.6 /
  6.1 mm from pins 45 / 50 and C9 at 5.8 mm from pin 23 (m10). The carry-over argument is fair, but the stated
  reason ("U1's south side is closed by the QSPI fan-out and the USB pair on all signal layers") does not apply
  to pin 23 on the west side, where (71.5, 128.3) is free. A 100 nF there costs nothing.
- **Review 2 m2 / re-check 4 — GND pour at H3 / H4 accepted "as on Rev F / G: insulating standoffs".** If the
  standoffs are insulating, the intent's 3.5 mm B.Cu rule has no purpose and review 1 M1 (the 5V trunk at
  2.5 mm) was fixed for a reason that does not exist. Pick one: record the insulating standoff in the intent and
  drop the rule, or keep the rule and give H3 / H4 the keep-out (m3). Both are fine; the current state is neither.
- **Review 2 m5 — "all 253 are on the assembly drawing" via `assembly_preview.py`.** True for the PNG / PDF; the
  board file's F.Fab still lacks references for the BNCs, the relays, D4 and U14, so any assembly drawing
  produced by KiCad itself (or by the next person) will not have them (n7). Add the four `${REFERENCE}` F.Fab
  texts to the library footprints.
- **SL-2…4 — switcher loops "not done, respin item".** I agree with not touching it for this order, but the
  reason given (no via spots on the cap pads' axes) is not the constraint: C81 and C91 can move (m7) without
  new vias. Record it as a choice, not an impossibility.

### Work products

All under `work/`: `lib_board.py`, `inventory.py` (→ `inventory.json`, `inventory-summary.txt`), `decoupling.py`,
`plane_voids.py`, `supply_current.py`, `path_trace.py`, `craft.py`, `mech.py`, `padgap_tombstone.py`,
`jackband.py`, `lengths.py`, `gerber_compare.sh` (+ `gerb-fresh/`), `revg_compare.py`, `netlist_vs_design.py`,
`switcher.py`, `ep_vias_paste.py`, `intent_items.py`, `signals.py`, `hole_pour.py`, `gnd_stubs.py`,
`followups.py`, `drc.json`, `jlc-drc/` (scratch copy with JLC limits as rules, `drc-jlc.json`), and the `.txt`
outputs named above (one per script).

---

## Dispositions (designer, 2026-11-10)

Every row was rechecked against the board before it was decided. The fixes were rebuilt with `sh validation/rev-g100/gates.sh`: pre-DRC 0, KiCad DRC 0, 0 unconnected, every screen 0 findings, and the analog core still 403 / 403 identical to Rev G.

| Finding | Disposition |
|---|---|
| Verdict, condition 1 (Plugged covering) | **Already the order instruction.** JLC's quote page offers Plugged as the 4-layer default and greys out Tented (`docs/rev-f-handoff.md`, `manufacturing/FABRICATION.md`). Fab note 4 asked for "plugged from the bottom only", which is not an option: it now says the EP vias sit under paste and JLC's plugging fills them |
| Verdict, condition 2 (placement preview) | Already the open pre-order step (`docs/rev-g100-plan.md`) |
| m0 VBUS A4/B9 0.2 mm exit | **Accepted, record corrected.** `current_check.py`'s docstring now says J1's pins are one node (FINDINGS G-PE-8 claimed this before it was true). The committed intent (`review-intent.md`) states the per-pair case as an accepted deviation. Your corridor measurement (0.52 mm) is adopted |
| m1 paste on EP vias | As condition 1. A paste-window shift is a better craft, and a respin item |
| m2 relay RESET margin | **Fixed.** VRLY and RLY_RST are 0.5–0.6 mm wherever there is room (`rev_g100_routes.py` §10). They stay 0.2 mm where they pass the RLY_RST via at (102, 113) and the GND via at (124.2, 114.2), and RLY_RST stays 0.2 mm into the jack band. Copper drop VRLY 18.3 → 6.4 mV, RLY_RST 15.5 → 7.5 mV; coil 4.149 → 4.169 V at VBUS 4.40 V (`drive-budget.json`) |
| m3 H3 / H4 pour | **Record fixed.** Only GND is inside 3.5 mm of any hole, so a metal standoff that wears through the mask ties GND to GND. The plan no longer asks for insulating standoffs |
| m4 Y1, m5 R13, m6 USB | Accepted: Rev F placement; 47 ps and 44 ps, against 100 ps |
| m7 TPS65131 caps | Accepted as a choice (FINDINGS SL-2…4 reworded): Rev F's block moved as one, victims ≥ 55 mm away. Bring-up scopes SW_P / SW_N |
| m8 0.12 mm footprint silk | Accepted: outline lines only, and text is 1.0 / 0.15 mm |
| m9 craft | **Stubs fixed:** USB_VBUS past C113.1 and LDOIN_N past U12.5 are removed. RUN, which ended on SW2.1's corner, now enters its centre. The off-grid chamfers and off-centre entries are the craft pass's output and are accepted |
| m10 decoupling | Not done; respin items (FINDINGS MD-1 / MD-2 row): C9 to (71.5, 128.3), C15 to (58.2, 114.0) |
| n2 current check gap | **Fixed.** `current_check.py` now covers 3V3A, 5VA, LDOIN_P and LDOIN_N. 3V3A failed (0.2 mm on In2 against 0.26 mm at 0.6 A) and is now 0.4 mm; all nets 0 FAIL. VRLY stays out, with its reason stated (coil and LED current only; `drive_budget.py` solves its drop) |
| n1, n3–n11 | Noted; no change |
| Against the earlier reviews | Adopted: G-PE-8 and H3 / H4 records corrected; MD-1 / MD-2 and SL-2…4 reworded as choices |
