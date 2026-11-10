# Datasheet audit, Rev G100: group `protection` (jack protection network)

Auditor pass 2026-11-09, board `cad/temper-lcr.kicad_pcb` at `be071cbcf` (study/lcr-rev-g100), netlist from
`validation/datasheet-audit-rev-g100/parts.txt` / `nets.txt`.

Scope: U18-U21 TLP172AM(TPL,E); D21-D24 H4V5HD3B; D25-D27 H3V3LD5B; D28 BAV99; R122-R125 CRCW-HP; C119/C120 1 nF C0G;
Q7 AO3400A with R134/R135; R132/R133 and the two LED strings from VRLY; the jack-sense dividers R126-R131 with
C121/C122 into GPIO28/29; R105/R106 and K4/R107 on the jack side.

Method for the four cases: the study's own charged-DUT deck (`validation/charged-dut/charged_dut_spice.py` `deck()`,
`judge()`) and network (`validation/rev-g-protection/protection_screen.py` `network()`, candidate `parts_jackside`)
imported read-only from a scratch script that adds the cases the study never ran (powered with the switches open, ±50 V,
10 µF, ESD with the switches open while powered) and records the new parts' stress (the study's `judge()` does not
judge them). Script and results: `/private/tmp/claude-501/-Users-bennet-Desktop-temper/6a92c72a-edd7-4ea9-8623-120b9fa58fa6/scratchpad/datasheet-audit-g100/protection-sim/run50.py`,
`run50.json`, `runc.py` (188 + 36 ngspice runs, 0 errors). The deck has no PCB or package inductance; layout
effects are added by hand below.

## 1. Findings

| ID | Severity | Refs | Requirement (citation, verbatim) | Board fact | Why it matters | Suggested fix |
|---|---|---|---|---|---|---|
| PROT-01 | **VIOLATION (design logic, not a datasheet limit)** | R126-R131, C121/C122, U1 GPIO28/29, `jackguard.c` | Firmware close rule (`jackguard.h`): "Close only below CLOSE ... `JG_CLOSE_MV 1000`", both CUR jacks, 7 polls. Study README phase 6: "The bias pushes 1.0 µA into a jack **at 0 V**". | With the switches open nothing on the jack side returns a CUR jack to GND: JK_HCUR = {D21, J3, K4.3/K4.8 (open), R105, R126, U18.4}, JK_LCUR = {D24, J9, R106, R107→REF_A→K4.7 (open), R129, U21.4}. The sense is a 1.65 V Thevenin source behind 1.5 MΩ + 240k‖240k = 1.62 MΩ (3V3 × 240k/480k). An open jack, or a floating DUT across HCUR/LCUR, therefore sits at +1.65 V and `jackguard_mv()` returns 1650 × 13.5 − 3300 × 6.25 = **+1650 mV > 1000 mV**. Pulling it under 1.0 V needs a leak < 1.62 MΩ × 1.0/0.65 = 2.5 MΩ, i.e. > 0.4 µA at 1 V; the datasheet maxima are IR ≤ 0.2 µA at 4.5 V (H4V5HD3B) and IOFF ≤ 1 µA at 60 V (TLP172AM), far less at 1 V. | The guard never leaves OPEN in normal use (only a jack tied to ground lets it close): the Rev G meter cannot measure. Fail-safe, but a respin-class bug if not fixed in firmware. Nobody modelled the open-switch float: `drive_budget.py` assumes a jack "held at 0 V"; `protection_screen.py` puts the sense resistor "to ground"; `test_host.c` feeds the guard 0 V. | Firmware (no hardware change, no analog cost): judge the DUT charge as |V_HC − V_LC| < 1 V and each jack as |V − V_float| < 1 V with V_float = 3V3 · R_GND/(R_BIAS+R_GND) = 1.65 V, i.e. close when both read 0.65–2.65 V (max jack-to-GND at close 2.65 V < H3V3LD5B VRWM 3.3 V). Update `drive_budget.py` settle check and `test_host.c` with an open-jack case. Hardware alternative: a DC return per CUR jack (1 MΩ gives 0.63 V float, only 0.37 V margin, adds noise gain 1+RF/1 MΩ = 1.1 on the 100k range at LCUR) — add DNP footprints in any case (debug list). |
| PROT-02 | **RISK** (1 µF) / **VIOLATION** (≥ ~3 µF at 50 V) | D21-D24 | H4V5HD3B Rev 2.1 Maximum Ratings: "IPP Rated Peak Pulse Current tp = 8/20 µs 40 A", "PPP ... 400 W"; Fig. 3 "Peak Pulse Power vs. Pulse Time" (read: ~1.0 kW at 1 µs, ~0.75 kW at 2.5 µs, ~0.12 kW at 1 ms). | ±50 V, 1 µF, every pattern/state: **47.7 A peak** (h_to_gnd), FWHM 0.65-0.8 µs, 510 W peak, 0.54 mJ; VC (model) 10.7 V. Bracket vs DUT C at 50 V (h_to_gnd): 2.2 µF 814 W @ 0.89 µs (Fig. 3 ~1.04 kW, ok); 3.3 µF 1.03 kW @ 1.48 µs (Fig. 3 ~0.89 kW, **over**); 4.7 µF 1.27 kW @ 1.6 µs (over ×1.5); 10 µF 1.93 kW, 116 A @ 2.5 µs, 4.5 mJ (over ×2.6). At 30 V the curve is reached at ~10 µF (749 W @ 2.5 µs). | At the brief's ±50 V the jack TVS is already 19 % over its only tabulated current rating at 1 µF (inside the PPP curve ×2.1), and outside the curve above ~2.5-3 µF. The study's "class A to 50 V / 200 V" never judged this part (see §2). An LCR meter is routinely given µF capacitors. | State the protected envelope as ~1 µF at 50 V / ~10 µF at 30 V (≈ 1.3-4.5 mJ) in the user docs and README; or move to a 600 W-class SMB/SMF jack TVS where capacitance allows (trade against the LCUR/HPOT capacitance the study protects). Bench: no change needed for 1 µF. |
| PROT-03 | **RISK** | U18-U21 (COFF), U6A/U7A, case (b) | TLP172AM Rev 9.0 §10: "Output capacitance COFF V = 0 V, f = 1 MHz — 20 — pF" (typ only, no max, no C(V)). | Unpowered, ±50 V, 1 µF: nominal (20 pF) class A, worst U6A input 7.28 mA (limit 10 mA, ×1.37). With COFF 40 pF: U6A input 14.6 mA, U7A 10.8 mA → class B in 6 of 20 runs (h_to_gnd, l_to_gnd). U6A current scales ~linearly with COFF: 10 mA is reached at **~27 pF**. | The ±50 V unpowered case rests on an unbounded typical. The study's argument that 40 pF is "pessimistic" uses the Panasonic AQW212EH C(V) curve, not a TLP172AM figure. | Bring-up acceptance for COFF(0 V) should be ≤ ~27 pF for the 50 V case (the study's ≤ 40 pF only covers 30 V). Measure COFF at 0/5/10 V on 5 parts. |
| PROT-04 | **RISK** | D21-D24 returns, U18-U21 VOFF, case (c) | TLP172AM §6 abs max: "OFF-state output terminal voltage VOFF 60 V"; §6 note "This device is sensitive to electrostatic discharge (ESD)" (no rating). HJC gives no TLP / dynamic-resistance data. | Model (no L): open switch sees 7.6-8.6 V at 8 kV. Layout: TVS GND = 0.5 mm × 1.1 mm F.Cu + one 0.3/0.6 mm via through 0.21 mm prepreg to In1 (FULL connection), in parallel with 0.5 mm × ~4 mm to the J3 shell pin: ≈ 0.3 nH. SOD-323 package ESL not given (assume 0.5-1 nH). 8 kV first peak 30 A in 0.8 ns → di/dt ≈ 30 A/ns → +9 V (board) +15-30 V (package) → **~33-48 V for ~1 ns** on U18-U21 pin 4/6. At 15 kV (56 A/ns): ~55-83 V. | Within 60 V at the 8 kV target, over it above ~12-15 kV; the H4V5HD3B is rated ±30 kV so the switch, not the TVS, sets the ESD ceiling. No datasheet basis either way. | Add a second GND via at each D21-D24 pad 2 (board share → ~0.2 nH); keep the 8 kV claim, do not quote 30 kV; bench IEC 61000-4-2 contact at 8 kV unpowered and powered on one board before release. |
| PROT-05 | **RISK (low)** | R132/R133, U18-U21 LEDs | TLP172AM §7 recommended: "Input forward current IF 5 (min) 7.5 25 (max) mA"; §11: "RON ION = 500 mA, IF = 5 mA ... 2 Ω max"; "IFT ... 3 mA max" (25 °C); Fig. 14.1.6 IFT rises ~1.5× from 25 to 85 °C (typ). | I = (VRLY − 2·VF − VDS)/R. Low corner: VRLY 4.31 V (5 V rail 4.32 V at VBUS 4.40 V − 10 mA × R101 1 Ω), VF 1.40 V, R 303 Ω (1 %): **4.98 mA**; during the 4-coil RESET (VRLY 4.18 V): **4.55 mA**. The study's 5.03 / 4.59 mA use 300 Ω exact. | Below the recommended minimum IF at the resistor-tolerance corner, so RON max is not guaranteed there; IFT max at 85 °C scaled from Fig. 14.1.6 (~4.5 mA) meets the RESET-pulse current. | R132/R133 300 → 270 Ω (basic UniOhm 0603): 5.54 mA min, 5.06 mA in RESET, 12.3 mA max; +1.5 mA USB (0.478 A typ). |
| PROT-06 | OK-NOTE | R132/R133, LEDs | TLP172AM §6: "IF 30 mA", "ΔIF/ΔTa −0.3 mA/°C (Ta ≥ 25 °C)", "PD 50 mW", "VR 6 V". | High corner: (5.478 − 2 × 1.1)/297 = 11.0 mA (11.7 mA with hot VF ~1.0 V); PD ≈ 14.6 mW. IF limit at 70 °C 16.5 mA, at 85 °C 12 mA. No reverse bias path. | Inside abs max to 85 °C ambient. | — |
| PROT-07 | RISK (low) | U18-U21, VBUS loss | TLP172AM §13: "tOFF ... 0.5 ms max"; §11 "IFC 0.1 mA min". | Study/firmware: "open within 0.5 ms of losing VBUS". In fact the LEDs keep IF > IFC until VRLY falls below ≈ 2·VF(0.1 mA) ≈ 2.1 V, i.e. the 5 V rail's hold-up time, then tOFF. The ±12 V rails collapse in the same window. | A partly powered state (rails down, switches closed) is not in the surge deck. Low probability. | Note in README; optionally open the switches in firmware on the USB_SENSE falling edge. |
| PROT-08 | OK-NOTE | U18-U21 pinout | TLP172AM §4: "1: Anode 3: Cathode 4: Drain 6: Drain"; §5 internal circuit: two MOSFETs in anti-series between 4 and 6. | U18/U21: pin 4 = jack, 6 = board; U19/U20: pin 6 = jack, 4 = board. Symmetric switch, so either orientation is correct. Strings: VRLY-R132-U19(1→3)-ISO_S1M-U18(1→3)-ISO_SINK; VRLY-R133-U20(1→3)-ISO_S2M-U21(1→3)-ISO_SINK: polarity correct. | — | — |
| PROT-09 | OK-NOTE | Footprints | HJC H4V5HD3B "Suggested Pad Layout": J ≥ 0.80, K ≤ 1.40, M ≥ 0.80 mm. HJC H3V3LD5B: X 0.55-0.65, Y 0.65-0.75, Z 1.37-1.47 mm. Toshiba 11-4M1S package: span 7.0 ± 0.4, lead 0.4, foot ≥ 0.5, pitch 2.54 ± 0.25, body 4.55 +0.25/−0.15 (no land pattern given). Nexperia BAV99 Fig. 8 SOT23 reflow footprint, pinning Table 2. AOS AO3400A pinout (G 1, S 2, D 3). | LCR:D_SOD-323_HJC 0.8 × 0.8, gap 1.4 (at both limits). LCR:D_SOD-523 0.6 × 0.7 at 1.4 pitch (nominal). LCR:Toshiba_11-4M1S: KiCad SO-4 lands 1.8 × 0.6 at ±3.15 / ±1.27; toe fillet 0.35-0.75, heel ~0.45-0.65, side 0.1 mm; pin 1 opposite 6, 3 opposite 4 as in the datasheet top view. LCR:SOT-23: IPC land 1.48 × 0.6, rows 1.875 apart (longer than Nexperia's); D28 pin 3 = DUT_LO, 1/2 = GND → antiparallel pair; Q7 G/S/D correct. CRCW 0805/0603 lands within ~0.2 mm of Vishay's reflow table. | — | — |
| PROT-10 | RISK (low) | JK_HCUR/JK_HPOT/JK_LCUR/JK_LPOT routing | No layout guidance in any of the HJC, Toshiba or Nexperia datasheets (see PROT-15). | Each jack TVS sits at the BNC courtyard edge (J3 courtyard to y 56.8, D21 from 57.2), 7.2 mm of 0.2 mm F.Cu below the centre pin; the switch pin is 2.1 mm after it (good). But R126, R105 and the 5.3 + 63 + 18.5 mm B.Cu run to K4 (JK_HCUR), R105 and the 2.8 + 51 + 18.4 mm run to K4 (JK_HPOT), R129 and R106 (LCUR/LPOT) leave the **centre pin, upstream of the clamp**. At 8 kV they see ≈ 9 V + 2.5 nH × 30 A/ns ≈ 85 V for ~1 ns. The B.Cu runs have no plane on In2/B.Cu in that band (pour keep-out) and run 0.21 mm over / 0.5 mm beside JACK_LC (In2) for 63 mm (~2-3 pF, into C122 100 nF: 3e-5). | Parts on the branches survive (UniOhm 0603: overload 150 V; TQ2SA open contacts 1000 Vrms; 1.5 MΩ), so no rating is broken; it is avoidable unclamped copper. | Take the R105/R126/K4 and R129/R106 branches from the TVS pad (pin 1) instead of the BNC pin when convenient. Not order-blocking. |
| PROT-11 | OK-NOTE | D21-D28 returns, clamp placement | as PROT-10 | Jack TVS: return described in PROT-04 (In1 filled at every via; vias FULL-connected). Second stage: D25 0.6 mm stub at R122's output; C119/D26 1.1/0.9 mm stubs on HPOT, U6 pin 5 6.7 mm on; C120/D27 likewise, U7 pin 5 ~10 mm on; returns 0.2 mm × 0.6-1.0 mm to one via (≈0.4-0.5 nH, ≤ 0.3 V at the 0.5 A ESD residual). D28 at R125's output, 26 mm (≈9 nH) of F.Cu before R94/C78. | Order jack → TVS → switch → R → second stage → op-amp is right everywhere. The 9 nH to C78 (100 pF) rings at ~170 MHz but R94 22 Ω + C78 sit between it and U7A. | Optional second via at each jack-TVS return. |
| PROT-12 | OK-NOTE | R126-R131, U1 GPIO28/29 | RP2040 datasheet Table 622: "Voltage at IO VPIN −0.5 ... IOVDD + 0.5 V"; Table 627 "ADC Input Voltage Range 0 ... ADC_AVDD". | Powered: pin = 1.528 V + 0.0741·Vjack → 0.73-2.32 V for ±10.7 V. Unpowered (3V3 ≈ 0): pin = 0.0741·Vjack; the 11 ms filter removes µs peaks; the clamp residual ±(4.5-6.5) V gives ±0.33-0.48 V, current ≤ 4.5 µA. ADC_AVDD and the bias share 3V3, so the reading is ratiometric (gain error only). `adc_gpio_init()` clears the default pull-down (main.c 658-659). | At the −0.5 V edge only for a > 6.7 V residual, and current-limited. | — |
| PROT-13 | OK-NOTE | Q7, R134, R135 | AO3400A Rev 3: "VGS(th) 0.65 1.05 1.45 V", "RDS(ON) VGS = 2.5 V ... 48 mΩ", "IDSS VDS = 30 V ... 1 µA", VDS 30 V, VGS ±12 V. | VDS ≤ 5.5 V; drop 22 mA × 48 mΩ ≈ 1 mV; off-state leak ≤ 1 µA ≪ IFC 0.1 mA (switches stay open); GPIO15 reset state input + pull-down, plus R135 100 kΩ → off through boot/BOOTSEL; main.c drives it low before enabling the output. | — | — |
| PROT-14 | RISK (low) | K4, R107 (jack side) | TQ catalog (Rev F RC-04): "The relay is shipped in the reset position. But jolts ... can change the reset position"; TQ2SA "Max. switching current 2 A". | K4 latching: unpowered with K4 SET (transport, power lost during REFCAPTURE) puts R107 across HCUR-LCUR and pole 1 shorts HCUR-HPOT. ±50 V/1 µF: R107 sees ≈ 21 V for ~1 µs then ~11 V decaying with τ = 1 kΩ·C (≈ 60 µJ; 0.6 mJ at 10 µF; ~0.12 W for ms on a 0.1 W 0603). In sense_first, pole 1 carries part of the TVS current (tens of A for ~1 µs), no pulse rating. The surge deck has no K4 ("the surge deck has no K4"). | Low: thin-film 0603 takes ms pulses at ~1×P70; relay contacts closed, not switching. | Note in README; bring-up: power-cycle with K4 set and confirm boot RESET. |
| PROT-15 | MISSING | All protection parts | — | HJC TVS sheets: no TLP/dynamic resistance, no CJ max (H4V5HD3B), no C(V), no IR(T), no layout guidance. TLP172AM: COFF typ only, no ESD rating, no transient SOA. BAV99: no layout guidance. | The ESD and unpowered margins cannot be closed on paper (PROT-03, PROT-04). | Bench items: COFF(V), CJ(0 V), leakage at 40 °C, IEC 8 kV contact on one board. |
| PROT-16 | OK-NOTE | D25-D28, R122-R125, C119/C120, U18-U21 on-state | H3V3LD5B: "IPP 8 A (8/20)", Fig. 3 ~22 W at 1 ms; BAV99: "IFSM tp = 1 µs 4 A; 1 ms 1 A", "IF 215 mA"; CRCW-HP single-pulse curve (0805 ~500 W, 0603 ~250 W at 1 µs), "Operating voltage 150 V / 75 V"; TLP172AM "IONP 1.5 A (t = 100 ms)"; C0G 50 V. | Worst over (a)-(d), 1-10 µF: D25 0.91 A; D26/D27 0.11 A; BAV99 1.1 A for 3.4 µs; R125 14.4 W / R122 9.0 W peak (µs); R123/R124 1.24 W, 11 V; LCUR switch on-state 1.2 A (10 µF) / 0.76 A (1 µF); C119/C120 ≤ 11 V; R105/R106 ≤ 12.8 V, 0.16 W µs. | ≥ ×3 margin everywhere except the switch at 10 µF (×1.25 against a 100 ms rating, so conservative). | — |
| PROT-17 | OK-NOTE | U18-U21 | TLP172AM §7: "Supply voltage VDD ... 48 V (max)". | Open switch sees ≤ 10.7 V (1 µF) / 16.7 V (10 µF) at 50 V. Only a jack TVS failed open would put the full 50 V on it (< 60 V abs max, > 48 V recommended). | — | — |

### The four cases, part by part (±50 V, 1 µF unless stated; worst over kelvin / sense_first / current_only / h_to_gnd / l_to_gnd, all ranges, both polarities)

**(a) Powered, switches open** (the power-up default; never run by the study, whose "powered" means closed). 40 runs, all class A.

| Part | Sees | Limit | Margin |
|---|---|---|---|
| D21-D24 | 47.7 A, 510 W, 0.54 mJ, 0.65-0.8 µs FWHM | IPP 40 A (8/20); Fig. 3 ~1.1 kW at 0.76 µs | ×0.84 on IPP; ×2.1 on PPP |
| U18-U21 off | 10.7 V | VOFF 60 V | ×5.6 |
| R105/R106 | 9.75 V, 0.095 W (µs) | 75 V working | ok |
| R123/R124 / R122/R125 | 3.1 V, 0.098 W / ≤ 0.45 V | 75 / 150 V; pulse curves | ok |
| D25 / D26, D27 / D28 | 22 mA / < 1 mA / 1.1 mA | 8 A / 8 A / 4 A | ok |
| U6/U7 (OPA2810) | U7A input 0.25 mA, Vdiff 0.29 V | 10 mA, 7 V | ok |
| GPIO28/29 | 0.73-2.32 V (filtered lower) | 0-3.3 V | ok |

**(b) Unpowered, switches open.** 20 runs, all class A at nominal COFF; 6 of 20 class B at COFF 40 pF (PROT-03).

| Part | Sees | Limit |
|---|---|---|
| D21-D24 | 47.7 A, 510 W (1 µF); 116 A, 1.93 kW, 4.5 mJ (10 µF) | as above; 10 µF over Fig. 3 ×2.6 (PROT-02) |
| U18-U21 off | 10.7 V (1 µF), 16.7 V (10 µF) | 60 V |
| U6A / U7A input (via COFF) | 7.28 / 3.71 mA (20 pF); 14.6 / 10.8 mA (40 pF) | 10 mA |
| R105/R106 | 10.2 V, 0.10 W | 75 V |
| GPIO28/29 | ≤ ±0.48 V residual, ≤ 4.5 µA | −0.5 … IOVDD + 0.5 (= 0.5 V) |
| K4/R107 if K4 latched SET | ~21 V µs, then ~11 V, τ 1 ms | PROT-14 |

**(c) IEC 61000-4-2 contact, 8 kV, each centre pin** (model without PCB L, then PROT-04 adds it).

| State | Part | Sees | Limit |
|---|---|---|---|
| closed (powered) | D21-D24 | 30.4 A, 278 W, 28 ns | ±30 kV contact |
| | U18 / U21 on-state | 0.49 / 0.65 A, ~0.2 µs | IONP 1.5 A (100 ms) |
| | R122 / R125 | 2.4 / 4.3 W peak | ~500 W at 1 µs |
| | D25 / BAV99 | 0.49 A / 0.59 A for 0.22 µs | 8 A / 4 A at 1 µs |
| | U7A | input 0.58 mA, Vdiff 1.86 V | 10 mA, 7 V |
| open, powered | U18-U21 off | 8.6 V model; **~33-48 V for ~1 ns with layout + package L** | 60 V |
| | op-amps | ≤ 0.32 mA | class A |
| open, unpowered | U6A / U7A | 13.9 / 10.6 mA for ns (class B, as the study reports) | 10 mA (HBM-scale pulse) |

**(d) Firmware closing onto a still-charged jack.**
- As built the guard never closes (PROT-01), so (d) cannot happen through the guard.
- With PROT-01 fixed as proposed, the worst permitted close is |V_HC − V_LC| < 1 V (≤ 2 V across a floating DUT) and each jack ≤ 2.65 V to GND, below the H3V3LD5B's 3.3 V VRWM.
  - HCUR goes into RG (≥ 100 Ω) through 12 Ω: ≤ 9 mA.
  - LCUR at −1 V goes into BAV99 through R125 + RON: ≈ (1 − 0.72)/12 ≈ 23 mA, against IF 215 mA.
  - The photoMOS ramps through its linear region during tON (0.6-2 ms): P ≤ V²/4R ≈ 21 mW.
- If the guard is bypassed (bug), it closes onto the clamp residual (≤ ~6.5 V):
  - D25 conducts ≈ (6.5 − 4.4)/12.4 ≈ 0.17 A with τ = 12 Ω·C. That is 21 µJ at 1 µF; at 1000 µF it is ~0.85 W for ~12 ms, against Fig. 3 (~22 W at 1 ms, ~10 W extrapolated at 10 ms).
  - The photoMOS sees ≤ 6.5²/48 ≈ 0.9 W for ~1 ms. It has no SOA figure, only PO 300 mW continuous: RISK only in a firmware fault.

## 2. Versus the protection study (`validation/rev-g-protection/`)

There is no Rev F report for this group. Where the board as built, or the datasheets, depart from the study:

1. **Open-jack float (PROT-01).** The study sized the sense for a jack "held at 0 V" (`drive_budget.py` `i_bias = mid / R_TOP  # into a jack held at 0 V`) and modelled the sense resistor to ground (`protection_screen.py` `sense`: "to ground here"). With the switches open the jacks float at +1.65 V. The guard's 1.0 V close rule, the "settle from a clamped jack to half the close threshold" check and the host test all assume the wrong rest point.
2. **"Class A" never judged the new parts.** `charged_dut_spice.judge()` checks only Rev F parts; `protection_screen.py` says the network's parts "are reported ..., not judged". So "class A up to 50 V (unpowered) and 200 V (powered)" and "nothing goes past the HBM pulse up to 30 kV" are statements about the OPA2810, LDOs, TAC5112 and passives only. At 50 V/1 µF the jack TVS already exceeds its IPP (47.7 A vs 40 A). At 200 V it would be several times over (the 1000 V row is 1.09 kA). Fig. 3 (PPP vs tp), the right basis for ~1 µs pulses, is never used. The stress table stops at 30 V.
3. **Powered with the switches open is the real power-up state and was never simulated.** The screen maps powered → closed (`network()`: RON when powered). Run here: class A at ±50 V, switch 10.7 V.
4. **COFF sensitivity.** The study's acceptance "COFF ≤ 40 pF" holds the 30 V target only. For the brief's ±50 V unpowered case the limit is ~27 pF (PROT-03). "40 pF at every voltage is pessimistic" rests on the AQW212EH's published curve, not on any TLP172AM data.
5. **LED drive.**
   - `drive_budget.py` uses 300 Ω exact, giving 5.03 mA. 1 % parts give 4.98 mA, below the 5 mA recommended minimum (PROT-05).
   - The RESET-pulse check compares 4.59 mA with IFT max 3 mA. That 3 mA is a 25 °C figure; Fig. 14.1.6 shows IFT rising with temperature.
6. **VBUS loss.** "Open within 0.5 ms of losing VBUS" omits the 5 V hold-up before the LED current falls below IFC (PROT-07).
7. **ESD model has no layout or package inductance.** The study's open-switch figures (7.6-15.6 V up to 30 kV) understate the switch's ns-scale VOFF; with ≈ 0.3 nH board return plus the SOD-323 package the 8 kV figure is ~33-48 V and 15 kV approaches or exceeds 60 V (PROT-04). The study's "30 kV" headline should be quoted as 8 kV.
8. **K4 latched SET while unpowered** is outside the surge deck ("the surge deck has no K4"). The Rev F audit (RC-04) records that K4's state is arbitrary after transport. It is low risk (PROT-14).
9. **Board as built otherwise matches the study's schematic delta**, in parts, values and nets:
   - R105/R106 and K4 + R107 are on the jack side.
   - K4 pole 1 shorts HCUR-HPOT.
   - The sense divider is 1.5 MΩ / 240 k / 240 k / 100 nF on GPIO28/29.
   - The strings are 300 Ω from VRLY, with Q7 on GPIO15 through R134 100 Ω and R135 100 k.
   - Layout details the study did not fix:
     - the K4 bypass and the reference path run HCUR/HPOT 90/73 mm across the board on B.Cu (≈ 0.2-0.3 Ω, ≈ 150 nH added to the bypass loop, 3e-4 of R105 at 85 kHz: the bypass still works);
     - `jackguard.h` says the 100 nF is "at the jack end of its run". That is true for C121; C122 sits 86 mm from R129, at the west end (no electrical consequence).

## 3. Debug and bring-up features worth adding

| Feature | Why | Cost / risk |
|---|---|---|
| DNP 0603 footprint from JK_HCUR and from JK_LCUR to GND, beside D21 / D24 | Hardware fallback for PROT-01, so a respin is not needed if the firmware fix is not wanted. Fit 1 MΩ only on HCUR first. | Pad pair on a jack node: ~0.1-0.2 pF beside 100 pF of TVS: negligible. Risk of a wrong fit on LCUR: noise gain. |
| Test pads on JACK_HC and JACK_LC at C121/C122 | Read the float, the settle and the residual decay directly; check the ADC reading against a DMM | Pads on a 100 nF node: nil |
| Test pad on ISO_SINK (Q7 drain) | Confirm the LED drive (VRLY − 2VF − I·R) and measure the string current with R132/R133's own pads | Nil (digital side) |
| Test pads on ISO_HCUR and ISO_LCUR (board side of U18 / U21) | Measure RON in place (drop at a known current) and COFF (open-switch coupling), the two TLP172AM numbers the datasheet leaves open | ~0.1 pF on board-side nodes behind 10 Ω: negligible |
| Second via at each D21-D24 GND pad | Reduces the ESD L·di/dt on the switch (PROT-04) | None |
| Firmware `JACKS` already prints both readings and the state | Keep it; add the raw codes to separate float vs threshold at bring-up | None |

## 4. Parts checked and datasheets used

All downloads are in `/private/tmp/claude-501/-Users-bennet-Desktop-temper/6a92c72a-edd7-4ea9-8623-120b9fa58fa6/scratchpad/datasheet-audit-g100/pdfs/protection/`. Each SHA256 matches `validation/rev-g-protection/part-selection/parts.json`.

| Refs | Part | Datasheet | Source |
|---|---|---|---|
| U18-U21 | Toshiba TLP172AM(TPL,E) | "TLP172AM Photocouplers Photorelay", Rev. 9.0, 2021-01-29 | https://datasheet.lcsc.com/datasheet/pdf/e218c185f9de7d12e9901cb4aacd6b92.pdf?productCode=C2152276 (sha256 9dd4fb2a…) → `tlp172am.pdf` |
| D21-D24 | HJC H4V5HD3B | "Bi-directional 4.5V High Capacitance ESD", Rev 2.1 | https://datasheet.lcsc.com/datasheet/pdf/8cf618ab0929fb7bcb33095267dcf307.pdf?productCode=C20615803 (de8693aa…) → `h4v5hd3b.pdf` |
| D25-D27 | HJC H3V3LD5B | "Bi-directional 3.3V Low Capacitance ESD", Rev 2.1 | https://datasheet.lcsc.com/datasheet/pdf/48a204db1fd1ee39954f1d7bb7377d32.pdf?productCode=C20615817 (c2fa0b85…) → `h3v3ld5b.pdf` |
| D28 | Nexperia BAV99,215 | Product data sheet, 1 July 2022 | https://datasheet.lcsc.com/datasheet/pdf/8b7720fc960f8626e375ebd15030b1eb.pdf?productCode=C2500 (826c982f…) → `bav99.pdf` |
| R122-R125 | Vishay CRCW0805/0603…HP | "CRCW-HP e3", doc 20043, rev 08-Sep-2021 | https://datasheet.lcsc.com/datasheet/pdf/b52727c8a24a0894dd7fb2427e3eb3c7.pdf?productCode=C844598 (c08f5011…) → `crcw_hp.pdf` |
| C119/C120 | Yageo CC0603JRNPO9BN102 | "Surface-mount ceramic multilayer capacitors, General purpose Class 1 NP0 16-250 V", Product Specification V.21, 2025-03-14 | https://datasheet.lcsc.com/datasheet/pdf/4eca2bb4b507f1633db47e922d632b95.pdf?productCode=C106246 (495287fc…) → `cc0603_np0.pdf` |
| Q7 | AOS AO3400A | "30V N-Channel MOSFET", Rev 3, Dec 2011 | https://datasheet.lcsc.com/datasheet/pdf/130876b936da464599428c58fd8de8f6.pdf?productCode=C20917 (e5bfeef6…) → `ao3400a.pdf` |
| R105, R106, R126-R135 | UniOhm 0603WAF thick film | Royalohm thick film chip resistor sheet (Max working 75 V, overload 150 V, 0603 1/10 W) | `sources/C23345-0603WAF220JT5E.txt` |
| U1 GPIO15/28/29 | RP2040 | RP2040 Datasheet: Table 622 (abs max), Table 627 (ADC), §4.9.2, E6/E11 errata, pin table (default pull-down) | `sources/new/RP2040-datasheet.txt` |
| K4 (pole 1, COM2/NO2) | Panasonic TQ2SA-L2-5V | TQ SMD 2006 sheet (pin map per Rev F RC-03; contact ratings) | `sources/rev-e/TQ2SA.txt`, `validation/datasheet-audit-rev-f/relays-connectors.md` |
| R107 | Yageo RT0603BRD071KL | not re-fetched (0603 thin film, covered by the Rev F audit); stress only checked here | — |
| J3/J7/J8/J9 | BNC footprint courtyard only | — | board file |
