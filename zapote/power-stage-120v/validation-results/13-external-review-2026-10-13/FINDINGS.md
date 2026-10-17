# External review of native-21, checked against the repo (2026-10-13)

An outside agent reviewed the KiCad files alone (revision content is stage 14 or later, although the files say
2026-10-07). This folder checks each claim against the repository and manufacturer data. Board of record: stage 22
(`native21s22`). Scripts: `scripts/review_calcs.py` (writes `results.json`, about 3 s, `python3 -I`) and
`scripts/netq.py` (netlist query). The lead spot-checked D5-BASIS.md, DECISIONS.md line 160 and parts.ato lines
12–13 and reran `review_calcs.py`.

**Netlist trap.** atopile 0.2.69 aliases the netlist `(part …)` field, so the `.net` file shows R3 100 k, R38 100 Ω and
PS2 IRM-20-15. The real parts, from `native-21/frozen/resolved-components.json` and `default.csv`, are R3/R4 220 k,
R38 0 Ω and PS2 IRM-20-24. Anyone reading the `.net` file gets these wrong.

Verdicts:
- **CONFIRMED-OPEN:** a real issue that nothing in the repo closes.
- **ALREADY-ADDRESSED:** the repo handles it; the evidence column cites where.
- **INCORRECT:** the claim is wrong.
- **NEEDS-LAB:** analysis can't settle it.

| # | Claim | Verdict | Severity | Evidence | Action |
|---|---|---|---|---|---|
| 1 | Keep the IPW65R018CFD7; validate ZVS, losses and overshoot | ALREADY-ADDRESSED on paper; NEEDS-LAB for switching loss and dv/dt | low | F6 decks pass 252/252, worst die VDS 490 V vs the 520 V screen (DECISIONS.md:197). ZVS: f/f_res ≥ 1.17 and phase ≥ 50° over 2,475 cases (05/round6-full-power/README.md:53). No better drop-in in stock (11-candidates/g02-g03-power-path). F7 loop re-extraction still open (DECISIONS.md:918). | Keep the part. Do F7 before mains. Bench: switching loss, S4/S5 dv/dt, VDS. |
| 2 | No active PFC; PF near 1 with the small film DC link; "1,800 W at PF 0.95 is 15.8 A" | ALREADY-ADDRESSED for PF and input current; the 1,800 W / 15.8 A premise is INCORRECT for this design; NEEDS-LAB for harmonics | low | The inlet is regulated to 13.5 A and trips at 15 A; the power stage is held at 11.1 A (about 1.33 kW at 120 V; DECISIONS.md:168–182). The repo already assumes PF ≈ 1 (DECISIONS.md:178). Round 6 shows PF falling to 0.95 under crest clipping. Rubric OTT-31 says harmonics are unassessed. Model (`results.json` claim2_pf): PF 0.997 at 1.33 kW, 0.987 at 600 W, 0.854 at 160 W. | Bench: PF and harmonics at 108/120/132 V. Ask the certifier which harmonic rule applies at 120–127 V; IEC 61000-3-2 is written for 220–240 V systems, a reading not checked against the standard text. |
| 3 | BR1 GBJ2510-F needs an engineered heatsink | ALREADY-ADDRESSED: true, and BR1 is already on the main sink | low | 28.4 W at 15 A, 21.0 W at the 11.1 A hold. Mounted on AlN tile B through a 1.0 mm gap pad, about 0.37 K/W (DECISIONS.md:412–421; owner-items/m11/SINK-DRAWING-NOTES.md). Case about 82.5 °C at 15 A. | Bench: thermocouple on BR1's case. |
| 4 | J1 Phoenix 1711725 is 24 A IEC but only 15 A cULus use-group B / 10 A use-group D | **CONFIRMED-OPEN**; the CSA rating is worse still | **med** | Phoenix MKDS 3/2-5,08 data sheet p.8 (2025-03-21 PDF, RS copy https://docs.rs-online.com/7382/0900766b81380186.pdf, fetched 2026-10-13): cULus E60425 group B 300 V 15 A, group D 10 A; CSA 13631 group B 10 A; IEC 24 A / 400 V. DigiKey lists 15 A / 300 V. parts.ato:12–13 still says the UL rating "must be checked"; the F1 note cites the IEC 24 A. J1 runs at 90 % of 15 A when regulated (13.5 A), 100 % at the trip and 110 % at the recorded 16.5 A envelope. | Record 15 A in parts.ato and correct the F1 note. Then either a ≥ 20 A UL group-B terminal at the next re-spin (a candidate, below) or an end-product temperature-rise test at 13.5–15 A and maximum ambient. Ask the lab whether cULus covers Canada. |
| 5 | Is R38 (PE to SELV GND, 0 Ω 0603) a protective bond? TO-247 tabs sit at drain potential | ALREADY-ADDRESSED by design; NEEDS-LAB for hipot and bond tests | safety (closed by design) | D5-BASIS.md: R38 is a removable functional link that "must not carry protective-earthing responsibility"; cord PE bonds directly to the chassis/heatsink stud, and J6 and R38 are never in series with the primary PE bond. M11 stack (DECISIONS.md:266–302, 376–384): AlN tiles, G-10 clamp, bond ≤ 0.1 Ω at 25 A for 120 s, hipot 3,000 V type / 2,000 V routine. D5 HOT-to-PE 8.507 mm. The open leakage failure (F5, 0.974 mA) is partly because R38 earths SELV. | Close M11's open items (AlN quote, compound dielectric data, lab ruling on basic vs reinforced). Hipot and bond tests. Candidate 23 fixes the leakage. |
| 6 | The J3 TCO breaks only PS2's AC feed: does losing 24 V turn off all four FETs, and is the bus still treated as live? | ALREADY-ADDRESSED by design; NEEDS-LAB (ECO.md capture) | safety (by design) | Losing V24_RAW kills U26 (V15_LS), U41/U42 (the high-side rails) and U3 (HOT5). The driver supplies collapse and the 10 k pull-downs hold the gates low; the ISO7710 default-high output asserts BAD, so BIAS_GOOD drops and DIS = NAND(PERMIT, BIAS_GOOD) goes high; U9 defaults to bus_fault; AMC1311 fail-safe makes the controller declare SENSOR_INVALID. The TCO removes gate drive, not the power path, so the bus stays live while the unit is plugged in (DECISIONS.md:103). | Bench capture of TCO removal (listed in ECO.md). Service note: the bus is live while plugged in. Certifier: whether a TCO that removes gate drive is acceptable. |
| 7 | Resonant bank 5 × 100 nF: is there a current and thermal analysis across the coil range? | ALREADY-ADDRESSED on paper; NEEDS-LAB for the hot spot | low | TDK p.57 current curve: J-grade bank 1.022× at 28 A / 40 kHz (DECISIONS.md:853; s22 scorecard). 70/80/90 µH and bank-size sweep in round 6. Double-fault over-voltage case covered. Release gate: hot-spot rise ≤ 20 K before running at 22 A (DECISIONS.md:371–374). | None beyond the existing gate. |
| 8 | 18 "ReviewOnly" footprints; C5/C6 use a footprint named after a different part | Mostly INCORRECT as a defect; CONFIRMED-OPEN (low) for stale names, the RECOM land and the D3/D17 lead bend | low; D3/D17 med until checked | 10 footprints, 18 placements, each with a recorded drawing check (table below). C5/C6 re-checked against the TDK B3267* data sheet (June 2026, https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32674_678.pdf, fetched 2026-10-13): p.4, 4-pin, lead spacing 37.5 ± 0.4 mm, Ø1.2 mm leads; p.10, B32676G1905 body 30 × 45 × 42 mm, row spacing P1 20.3 mm. That matches the pads (0,0)/(0,20.3)/(37.5,0)/(37.5,20.3) and the Ø1.8 mm drills. | Rename or re-describe the C5/C6 footprint. Fix parts.ato:6–7 and RADIAL-FOOTPRINTS.md. Review the RECOM SSOP-36 land pad by pad. Check a formed D3/D17 sample before ordering. |
| 9 | No inrush limiter | ALREADY-ADDRESSED; new observation O1 (low) | low | 630 A / 4.0 A²s at 2 µH lossless: 1.8 % of KLDR025's 226 A²s melting I²t and 0.8 % of BR1's 510 A²s. C5/C6 pulse rating 765 A per part (ALT-C5C6.md:143–148). Reproduced: 624 A / 3.9 A²s at 140 V. | No limiter needed. Bench: plug in at the line crest and measure the bus peak (O1). |
| 10 | Discharge τ ≈ 7.9 s; service-discharge requirement | The number is roughly right; the requirement is CONFIRMED-OPEN | low | The bus divider (R26–R30, 1.896 MΩ) also bleeds the bus, so 357 kΩ total: τ 6.6 s nominal, 7.2 s at +10 % C; 198 → 60 V takes 7.9–8.6 s. ALT-D3.md:243 says the requirement "needs review" and it was never closed. Option N1 (R3/R4 → 100 k) gives 4.0–4.4 s. The only discharge limit in the repo is plug pins < 34 V in 1 s, which is met. | Set the basis with the certifier. Add a "wait 15 s" service label, or take N1. |
| 11 | F1 (25 A) vs J1's rating: overcurrent coordination | **CONFIRMED-OPEN** (documentation and certification); short-circuit protection is fine | **med** | No line-current sensor: the limit is a firmware estimate with an unqualified 10 % error (DECISIONS.md:168–182). A 25 A UL 248 fuse carries its rating indefinitely, so F1 never interrupts 15–25 A through J1. Short circuit: KLDR025 clears at 1,710 A²s, far below the cord's fusing I²t. | Record the overload basis (firmware plus branch breaker, J1 at 15 A). Certifier: an abnormal-operation test with the firmware limit defeated, measuring J1, L1 and cord temperatures. If it fails, add hardware line-current sensing or fit a larger J1 (folds into #4). |
| 12 | vbus comes from isolated AMC1311 U4; 3.3 V comes in on J4; R38 ties control ground to PE | Correct description, not a defect | — | U4.7/.6 → J4.11/.12; v3v3 = J4.3, and nothing on the board makes 3.3 V; R38 joins pe and selv_gnd. U4's high side runs from HOT5, so a TCO trip invalidates vbus (fail-safe, #6). | None. |

## ReviewOnly footprints at stage 22 (10 footprints, 18 placements)

The `_ReviewOnly` suffix is a legacy name kept so library references don't change (FOOTPRINTS.md, last paragraph).
The stale comment at parts.ato:6–7 is what misled the reviewer.

| Part | Footprint | Recorded check |
|---|---|---|
| RV1 TMOV20RP175E | TMOV20RP | FOOTPRINTS F4. Provisional: the offset lead needs forming. |
| C1/C2 R463N410050N1K | KEMET_R463N410000N1M_P22.50 | footprint-specs YAML (KEMET p.3/p.10); same N1 body as the drawn part |
| L1 B82726S2203A020 | B82726S2 | F5, verified |
| C3/C4 DE1E3RA222MA4BP01F | Murata …P10.0_Pad1.5 | RADIAL-FOOTPRINTS, verified |
| C5/C6 B32676G1905K000 | TDK_B32656G0275J000_4Pin | ALTERNATES:72, ALT-C5C6:126 and the re-check above. Geometry correct; name and description stale. |
| D3/D17 30KPA150CA | P600_Axial_P12.70mm | ALT-D3:285–334 (Good-Ark p.1). No FOOTPRINTS row; lead-bend concern below. |
| J6 1704004 | Phoenix_KDS3 | RADIAL-FOOTPRINTS, verified |
| C38–C41 B32652A0104K000 | TDK_B32652A0104K000_P15.00 | RADIAL-FOOTPRINTS, verified |
| U41/U42 R24C2T25/R-R | RECOM_SSOP-36 | Only the footprint's own description cites RECOM p.11; no independent pad review recorded. **Open.** |
| U36 VOL628A-2X001T | VOL628A_LSOP4 | F11 plus the 2026-10-08 independent review |

**D3/D17 lead bend (an assumption; verify):** the hole centre is 1.8 mm from the body end (12.7 mm pitch, 9.1 mm
maximum body). IPC practice, as recalled and not checked against the standard, is a straight section of at least one
lead diameter, then an inside bend radius of 1.5–2 × the 1.3 mm lead. That needs about 3.4–4.6 mm, so the bend would
stress the diode's seal. Check a formed sample, or move to stand-off mounting or a longer pitch (which moves R3).

## O1: plug-in overshoot (not in the outside review)

Plugging in at the line crest rings the bus to about twice the crest voltage: about 370 / 390 V lossless at
132 / 140 V; 321–341 V with 60 mΩ of series resistance; 362–384 V with the required ≥ 100 µH inlet module. That
exceeds two thresholds:
- the 335 V minimum breakdown of D3 + D17 in series, which then absorb about 0.4 J, within their rating;
- the about 280 V bus OVP, so bus_fault asserts for about 1.3–2.2 s while the bleed brings the bus back down.

This is fail-safe: at worst a start delay. Firmware must not latch a permanent fault on an overvoltage at power-up.
Confirm on the bench with the real inlet module, whose damping branch was not modelled.

## What this adds up to

- **Proven defects** (manufacturer data plus repo):
  - #4: J1 is rated only 15 A UL / 10 A CSA, against 13.5–15 A in normal use.
  - #11: nothing in hardware limits a 15–25 A overload through J1.
  - #8: stale footprint names and comments.
- **Depends on assumptions or the certifier:** #2 harmonic rule, #10 discharge requirement, #6 whether the TCO
  approach is acceptable, and the D3/D17 lead bend.
- **Not defects:** #1, #3, #5, #7, #9, #12, apart from bench confirmations already planned.
