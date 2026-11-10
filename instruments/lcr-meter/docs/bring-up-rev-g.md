# Rev G bring-up, and what Rev F bring-up feeds into Rev G

**Status, 2026-11-09: no Rev F or Rev G board exists.** Rev F has not been ordered (`rev-f-handoff.md`). So open item 2 of [rev-g-plan.md](rev-g-plan.md) §6, "Rev F bring-up findings on the band nodes", cannot be closed yet. This page prepares it in two parts:
- **Part A** says, step by step, which Rev F bring-up result changes Rev G, and where.
- **Part B** lists the steps only a Rev G board has.

[bring-up-rev-e.md](bring-up-rev-e.md) stays the procedure for both boards, with the Rev F notes in [rev-f-handoff.md](rev-f-handoff.md) "When boards arrive".

**How a Rev F fix reaches Rev G.**
1. `cad/tools/rev_g.py` executes `cad/tools/rev_f.py` and its routes, then applies the Rev G edits. A value or copper fix made in `rev_f.py` / `rev_f_routes.py` therefore reaches Rev G on the next `cad/rebuild.sh`. Make the fix on `study/lcr-in-box` first, then merge it here.
2. After the rebuild, run `sh validation/rev-g/copper_shift_delta.sh`. If the fix moved analog copper inside the reused Rev F zoom windows, its `reused_rev_f_zoom_windows` count is no longer 0. In that case rerun those zooms (`run_reve.sh revg` without the reuse), then the stability matrix `revgxcng100`.
3. Rerun the gates in `rev-g-plan.md` §2. A copper change also gets the independent review again (frozen export, files not conclusions).

## Part A: Rev F bring-up results and their Rev G consequence

| Rev F step ([bring-up-rev-e.md](bring-up-rev-e.md)) | Same circuit on Rev G? | If Rev F finds a problem |
|---|---|---|
| §1 Inspection | yes, plus 31 new parts | — (Part B, G1) |
| §1a Indicator LEDs | yes | fix in `rev_f.py`; reaches Rev G on rebuild |
| §2 / §2a Power, start-up, hot-plug (U16, U17, C117, R121) | yes, the same parts and copper moved 10 mm | the same value fix applies. Rev G draws 0.476 A typical against Rev F's 0.46 A at attach, so rerun `startup_surge.py` with the Rev G load if the fix touches the current limit |
| §3 Firmware, codec clock, I2S edges | yes; one firmware tree (`LCR_REV_G=1`) | firmware fixes reach both builds; rebuild both UF2s |
| §4 Relays, coil identity (SET on pins 1–5 or 6–10) | yes, K1–K4. K4's second pole is used on Rev G (it shorts HCUR to HPOT during the reference check) | a firmware-only fix covers both. Check that `jackguard.c` drives K4 with the same polarity |
| §5 Quiet board | yes | the same fix |
| §6 Source, analog levels, stability | the core is the same; the jack side is not | a value change in the drive, TIA or follower loops (RISO, C104, RF / RG) goes into `rev_f.py`. Rerun `revfcng100` and `revgxcng100`: Rev G has more margin in TIA (69.7° vs 57.3°) but the same in drive (47.4° vs 47.8°) |
| §7 Internal reference (K4 + R107) | no: on Rev G the reference sits on the jack side, behind the LCUR switch and its 10 Ω | the Rev F number does not carry over. Measure it again on Rev G (Part B, G6) |
| §8 Calibration with the cal kit | the procedure, yes; the constants, no | Rev G calibrates on its own. Open compensation includes the jack TVS and switch capacitance |
| §9 Gate B-E1, DAC images | yes | applies directly |
| §10 80–85 kHz | yes | applies directly |
| §10 Unpowered ESD knee (`bench-esd-knee.json`) | no: on Rev G, unpowered, the photoMOS is open and the TVS takes the current | **the Rev F result is one of the three protection-study inputs.** The model expects 0.52–0.71 V. Outside that range, rerun `protection_screen.py` with the measured cell. The stronger-cell variant `jackside_esd_alt` raises the unpowered limit from 50 to 100 V |
| §10 3V3A under overload (AFE-07) | no: Rev G clamps in front | Rev F only |
| §10 Relay capacitances | yes | the measured values feed both stability decks; rerun both |

**What Rev F can measure for Rev G even with no Rev G board.** Rev F is an LCR meter. Once it is calibrated (§8), measure loose parts on the 100k range at 100 kHz, with Kelvin clips on the bare part and open compensation done at the clips. These are the three pass limits the protection study sets (`rev-g-protection/README.md`, "Open items"):

| Part | Measure | Pass | If it fails |
|---|---|---|---|
| TLP172AM (C2152276), output pins 3–4, LED off | C at 0 V bias | ≤ 40 pF (2 × the datasheet's 20 pF typical) | at 40 pF the unpowered 30 V target is met exactly (`jackside_coff2x`), so above it the target is no longer shown: rerun `protection_screen.py` with the measured value |
| H4V5HD3B (C20615803) | C at 0 V | ≤ 200 pF | `jackside_tvs_c2x` (both TVSs × 2) still meets 50 V and moves one accuracy cell; above the limit, rerun `protection_screen.py` and `normal_operation.py` with the measured values |
| H3V3LD5B (C20615817) | C at 0 V | ≤ 25 pF | as the row above |

Order a few loose parts with the Rev F parts if Rev F goes first. LCSC sells all three.

## Part B: steps only a Rev G board has

Run these after bring-up-rev-e.md §1–§3 pass, and before §6. Until G3 passes, the firmware keeps the jack switches open, so the front end sees no DUT.

| Step | What | Expect | Record |
|---|---|---|---|
| G1 | Inspection: U18–U21 pin 1 (anode) as on the silk; D28 pin 3 toward DUT_LO; D21–D24 cathode on the jack centre pin | as on the assembly drawing | photos |
| G2 | Switch drive. Command the switches on, then measure the voltage across R132 and R133 (the LED-string resistors) | ≥ 5.03 mA per string at 5 V; at least the 3 mA IFT while a relay pulse runs (`drive-budget.json`) | V and computed I |
| G3 | Isolation. Power off: jack centre pin to DUT_HI, HPOT, LPOT and DUT_LO with a DMM | > 10 MΩ (switch open) | four readings |
| G4 | Continuity. Switches on, power on: jack centre to node | 10 Ω + RON (HCUR / LCUR) and 100 Ω + RON (HPOT / LPOT); RON ≤ 2 Ω | four readings |
| G5 | Residual-voltage sense. Jacks open: `JACK_HC` / `JACK_LC` read at mid-scale. Apply +5 V and −5 V from a current-limited supply (≤ 1 mA) to HCUR, then LCUR | about 11 mV per code (1.5 MΩ / 240 kΩ / 240 kΩ); the guard opens the switches above 1 V and closes them after 7 calm polls (35 ms) | readings and trip times |
| G6 | Internal reference (bring-up-rev-e §7) through the jack side: K4 set also shorts the HCUR and HPOT jacks | the model puts the worst 85 kHz cell at 0.014 % (5k range) and 0.024 % (100k) (`rev-g-protection/README.md`, "The HPOT reference residual") | readings |
| G7 | Accuracy against Rev F (if built) on the same cal-kit parts | the same verdict cells, since the map gives 144 / 22 / 43 for both | captures |
| G8 | Charged-part check, last and optional. With the meter powered, touch HCUR–LCUR with a 1 µF film capacitor at 10 V, then 30 V, through two-terminal leads. Scope 3V3A | the guard trips. 3V3A stays under the TAC5112's 3.9 V (the model never ends class A on 3V3A). The meter measures normally afterwards | scope shots |
| G6a | Relay state check (G100's RESET margin: 4.149 V at the coils against 4.125 V for a 45 °C relay, `drive-budget.json`). Jacks open. Run `temper-lcr relaycheck PORT 1000` at 5.0 V, then at VBUS 4.40 V from the bench supply with the board warmed to about 45 °C (closed enclosure or hot air), 20 runs. Scope VRLY on one run | PASS on every run. A FAIL names the relay that missed its RESET: then the RESET pulse needs more voltage (4.5 V-coil relays, `rev-g100-plan.md`) or a longer pulse | pass count, VRLY minimum in the pulse |
| G9 | IEC 61000-4-2 contact on each centre pin (lab, if a gun is available), powered and unpowered, both polarities | class A powered, class B unpowered (nothing past the op-amp ESD cell's HBM pulse); the model holds both up to its 30 kV sweep top | lab report |

Commit everything to `validation/bring-up-rev-g/` with the step number, as on Rev F.
