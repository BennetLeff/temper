# Oracle answer: bus estimates, boundary voltages, insulation consequences

Response to the focused questions in [ORACLE-REVIEW.md](ORACLE-REVIEW.md),
2026-09-25. Supersedes the earlier external answer. Numbers come from
`tools/bus_voltage_sim.py` (lumped model: ideal diodes, no stray inductance,
no snubbers). They are design estimates, not measured bounds.

Physical overshoot, touch-current, CT injection, hipot and emissions tests:
**NOT RUN**. No fabrication or certification approval is implied.

**Historical parameter notice (2026-09-25):** the bus-voltage simulation and
heuristics below use the earlier 4.5 µF worst-tolerance model of a nominal
5.0 µF/600 V CDE bus. The approved source now specifies two 2.7 µF/1000 V
TDK bulk capacitors plus four 0.1 µF/1000 V local parts, nominal **5.8 µF**.
The numbers below were not recomputed as a fault bound for that hardware;
do not reuse the 468/511 V figures as MOSFET or TVS margins. The capacitor
only sensitivity screen is [BUS-CAP-SCREEN.md](BUS-CAP-SCREEN.md); it does
not simulate tank energy return. The 650 V MOSFET stress, local inductance
and repeated TVS pulse still require measurement and qualification.

## Corrections to the earlier answer

1. **The bridge does not clamp the rails to the mains crest.** The diodes
   give HV_RET ∈ [max(L,N) − Vf − Vbus, min(L,N) + Vf] and
   BUS_P ∈ [max(L,N) − Vf, min(L,N) + Vf + Vbus]. With N near earth,
   |any rail or switch node to PE| ≤ Vbus + Vf. The rectifier blocks while
   Vbus > |v_line|, so returned tank energy raises Vbus and nothing in the
   rectifier limits it. Everything therefore reduces to bounding Vbus.
2. **The 9.1 mm CT gap came from the wrong donor footprint.** The corrected
   CST3015 land pattern gives an 18.5 mm primary-to-secondary copper edge gap
   (FOOTPRINTS.md F7).
3. **The 2.4 nF IRM capacitance was inferred from a leakage rating** and is
   not established. It is withdrawn; IRM leakage must come from Mean Well data
   or measurement.

## Q1: DC-link estimates

The supplied script starts at 127 V + 10 % line (198 V crest) with a 4.5 µF
bus (5 µF − 10 %), Cr = 0.54 µF, zero initial tank current and capacitor
voltage, and an ideal trip 300 ns after `abs(tank_current)` crosses the
threshold. Its starting bus is a chosen case, not the highest voltage at which
the ≈280 V restart inhibit could permit operation.

**Historical heuristic.** Driven at resonance, the tank current envelope grows by about
ΔI ≈ 2·Vbus/Z₀ per half cycle (Z₀ = √(L/Cr): 29 A at 100 µH, 42 A at 48 µH).
If the assumed trip follows the tank current, the envelope might exceed the
threshold by a step. Counting only ½·L·(I_trip + ΔI)² as returned energy gives

  Vbus,heuristic = √(Vstart² + L·(I_trip + 2·Vstart/Z₀)² / Cbus)

This is **not a conservative upper bound**: Cr can hold energy that later
charges the bus, and the actual 1 mΩ DC-return shunt does not measure
`abs(tank_current)` directly. `tools/bus_voltage_sim.py` prints one trajectory
per listed OCP case with pan resistance 0.3 Ω and 300 ns assumed latency. It
does not implement the previously reported damping/100–800 ns sweep.

| Case | 48 µH | 100 µH |
| --- | ---: | ---: |
| Normal shutdown at full power (sampled trace) | 234 V | 222 V (70 µH) |
| OCP trip at 91 A, driven at resonance: heuristic | 477 V | **599 V** |
| OCP trip at 61 A, driven at resonance: heuristic | 390 V | **468 V** |
| OCP trip at 71 A (top of the comparator-offset spread): heuristic | — | 511 V |
| Differential surge, limited by RV1 (TMOV20RP175E) clamp | ≈ 460 V | ≈ 460 V |

- Earlier estimates put some above-resonance, pan-removed currents at 53–78 A.
  The lowered 61 A threshold can therefore trip in that case. Driving at or
  near resonance, a start-up sweep and pan lift need separate fault analysis.
- The 198 V start approximates the high-line crest. A prior trip can leave the
  bus elevated while the restart inhibit remains below ≈280 V; the same
  heuristic then gives ≈556 V at 61 A or ≈597 V at 71 A for 100 µH, before
  accounting for Cr energy or switching overshoot.
- At the time of this simulation, the film bus was rated 600 VDC and the
  MOSFETs 650 V. The 91 A heuristic approached that former capacitor rating
  even from a 198 V start; the approved capacitors are now rated 1000 VDC.

**Controls and follow-up:**

| # | Control | Effect |
| --- | --- | --- |
| S1 | Lower the OCP trip from ≈ 91 A to ≈ 61 A (retune the threshold divider) | The 198 V-start heuristic falls from 599 to 468 V (511 V at the top of the offset spread). The 51 A low end of the stated offset spread is about 6 A above the estimated 45 A loaded normal peak, before other tolerances. |
| S2 | Add a HOT-side bus over-voltage comparator on the bus divider into the existing fault latch, ≈ 280 V | Hardware restart inhibit. The bus bleed takes seconds, so firmware must not restart into a pumped bus. |
| S3 | Add a bleed resistor across the resonant bank C21–C23 | After a trip Cr can hold up to ≈ ±250 V with no discharge path: a service-shock hazard. |
| S4 (controller) | Never drive at or below the highest possible tank resonance: enforce a minimum switching frequency, and detect pan lift from the CT phase before sweeping | Makes the at-resonance trip a double fault. Controller-board firmware and hardware, not this board. |

The current source adds the approved MRT130KP295CV across BUS_P/HV_RET, but
its assembled pulse, surge and clamp performance remains open. A
source-consistent fault analysis must
include the initial bus and Cr charge, the DC-shunt waveform, sense-filter and
comparator delay, isolator/interlock/gate turn-off, and the tank CT protection.
**Measure actual overshoot on the bench** at worst line phase and plausible
restart states before accepting the 650 V MOSFET margin and the TVS stress.
The approved bulk and local capacitors have 1000 VDC nameplate ratings;
their transient current/temperature suitability still requires validation.

**Controller ground ↔ PE: keep the single-point bond.** It defines the
controller potential. The externally earthed controller case produces
identical voltages, so the design must meet it regardless.

## Q2: differential voltages at each HOT/SELV crossing

Controller at PE (bonded, or externally earthed with PE intact). N ≈ earth;
the bounds are symmetric in L and N, so reversed polarity (common with
unpolarized Mexican outlets) gives the same numbers.

| Node | Crossing | Rated 127 V | 127 V + 10 % | Band (rms) |
| --- | --- | --- | --- | --- |
| BUS_P, HV_RET, SW_A, SW_B | U1, U2 (UCC21550), U4 (AMC1311), U9 (ISO7710; U7 before the source change) | 90 V rms, 180 V pk | 99 V rms, 198 V pk | >50–125 |
| RES_A / coil_ret (T1 primary before relocation) | T1 in the earlier source | 165–220 V rms, 457–582 V pk at 33–60 kHz | up to 242 V rms, 640 V pk | >125–250, plus HF |
| PS1 (IRM-20-15) mains input, kept separate from the DC rails | PS1 | 127 V rms, 180 V pk | 140 V rms, 198 V pk | >125–250 (127 V is just above 125) |

The RES_A range spans the 70 µH and 48 µH loaded coils. These rail and
switch-node figures assume a line-following bus in the model. They are not
limits for an elevated DC link or a demonstrated insulation classification.

- **PE open:** the PE net floats to ≈ (L+N)/2 through the 2.2 nF Y
  capacitors C3/C4, so every difference roughly halves (≈ 64 V rms on the
  rails). This is not the governing insulation case. It **is** the touch
  current case: ≈ 0.12 mA from C3/C4 at 140 V, plus PS1/PS2 internal leakage
  (unknown), against the class I limit. This must be measured.
- **Externally earthed controller with PE open:** the controller is at earth,
  so the voltages are the same as the bonded case.

## Q3: standard convention and HF treatment

- IEC 60335-1 sizes creepage from the rms working voltage at rated voltage in
  normal operation. Shutdown returns, OCP trips and surges are transients:
  they govern clearance and component voltage ratings, not creepage.
- Reinforced creepage is twice basic (Table 17). Values from
  `creepage_table_lookup`:

  | Band | Basic, PD3, IIIa/IIIb | Reinforced, PD3, IIIa/IIIb | Reinforced, PD3, group I |
  | --- | ---: | ---: | ---: |
  | >50–125 V | 2.4 mm | 4.8 mm | 3.8 mm |
  | >125–250 V | 4.0 mm | 8.0 mm | 6.4 mm |

- Reinforced clearance is set by the impulse step (2.5 kV → 4 kV): about
  3 mm (Table 16). **Verify this.** It does not govern next to 8 mm creepage.
- IEC 60664-4 addresses periodic stress above 30 kHz. Relocating T1 removes
  its connection to the resonant junction but leaves it on switching node
  SW_A. High-frequency treatment at that crossing still needs review.
- **Current conditional basis:** place the entire controller/HOT PCB barrier
  to **≥ 8.0 mm** (PD3, verified material group IIIa or better,
  reinforced objective). This is a placement floor, not proof that the
  >125–250 V band or any package surface/IEC 60664-4 requirement suffices.
  The per-node band results are retained as historical estimates only.
- **Former exception, now changed:** U7 (ISO7710FDWR, now U9) used KiCad's
  stock `SOIC-16W_7.5x10.3mm_P1.27mm` with a **7.25 mm** copper gap. U9 now
  uses TI's high-voltage DW land pattern at 8.1 mm. U4's stock SOIC-8 DWV
  pattern gives 8.85 mm. Package surface ratings still need separate review.

## Q4: CT relocation

**Previous source (confirmed from the earlier frozen netlist):**
SW_A → J2 → coil → coil_ret → T1 → res_a → C21–C23 → SW_B.
T1's primary sits at the resonant node: up to 242 V rms and 640 V pk at
33–60 kHz relative to its SELV secondary.

**Implemented source:** SW_A → T1 → J2 → external coil → J5 RES_A
→ C21–C23 → SW_B.

- T1's primary moves to a switch node. The 99 V rms / 198 V peak figures
  describe the line-following example, not a bound under bus pumping. SW_A
  still switches at tens of kHz, so its IEC 60664-4 treatment remains open.
- Interwinding common-mode injection and current-sense polarity need bench
  verification after the relocation. No CT BOM change was made.
- Either way, the 18.5 mm PCB gap exceeds 8.0 mm. The PCB gap does not add to
  the package's own insulation (≥ 8 mm published).
- **Evidence still required from Coilcraft:** the certificate behind
  "5 kVrms reinforced, ≥ 8 mm" (which standard, which pollution degree) and
  the CTI / material group of the case and bobbin. Without it, T1 is the one
  barrier part whose rating cannot be mapped onto PD3.

Evidence still required for other parts:

- **TI isolators:** package creepage and CTI are stated for PD2. At ≥ 8 mm and
  CTI ≥ 600 (group I) they exceed the PD3 requirement for their >50–125
  crossings; confirm the CTI figure per datasheet.
- **Mean Well IRM-20-15:** the safety approval and leakage current data sheet
  values.

## Source changes made before placement

The five source changes required re-audit, re-freeze and a new native build
(Parts 1 and 3).

1. Relocate T1 (Q4).
2. S1: OCP trip ≈ 60 A.
3. S2: bus over-voltage comparator into the fault latch.
4. S3: resonant-bank bleed resistor.
5. Replace U7's footprint with an HV DW land pattern (≥ 8.0 mm across the barrier).

The owner has conditionally approved D5 for provisional placement with an
8.0 mm floor and verified group IIIa-or-better laminate. The former IIIa/IIIb
wording is superseded: IIIb is restricted above 50 V. Coilcraft evidence and
final working-voltage/HF insulation qualification remain open (D5-BASIS.md).

## Implementation status (2026-09-25)

All five source changes were made on `feat/ps-oracle-source-changes` and
are integrated in `codex/power-stage-120v-build`. The later REF25 correction
uses 5.6 kΩ (see REFERENCE-BIAS.md). A subsequent integration update uses
U8 NAND and U9 non-F isolation, so J4.10 BUS_FAULT now matches the existing
active-high interlock input. The owner approved a conditional D5 placement
basis and R38 implements its functional PE link. HOT5 brownout and whole-chain
qualification remain open; see FAULT-INTERFACE.md and D5-BASIS.md.

| Change | Source | Evidence |
| --- | --- | --- |
| T1 on the switch node | SW_A → T1 → `coil_feed` → J2 → external coil → J5 `res_a` → C21–C23 → SW_B | Audit asserts the primary side; `ct_on_resonant_node_fails` mutation test |
| OCP ≈ 61 A | `r_th_bot` 9.76 k → 10.0 k (R35); threshold 1.2195 V | Audit pins the threshold MPNs; `old_91a_threshold_fails` |
| Bus OVP ≈ 280 V | U7 TLV3201 on the `vsense_in` tap vs 2.333 V (R36 10 k / R37 140 k); U8 SN74LVC1G00 NANDs OCP-OK and OVP-OK into U9 ISO7710DWR (BUS_FAULT high on either trip) | `swapped_ovp_comparator_inputs_fail`, `ovp_bypassing_isolator_path_fails` |
| Resonant-bank bleed | R22–R25, 4 × 470 k from `res_a` to SW_B | `missing_resonant_bleed_fails` |
| U9 HV land pattern | `lib:SOIC16W_DW0016B_HV`, TI DW0016B HV option (SLLSER9E p. 33) | 8.1 mm measured across the barrier on the generated board |

The axial TVS/J2 intermediate build measured 104 components and 73 nets;
its audit passed 37/37 tests and its native projection had 104 footprints,
296/296 source pin connections and zero schematic parity errors. **Those
numbers are historical.** The later approved source revision changes C5/C6
to 2.7 µF/1000 V TDK four-pin parts, adds four 100 nF/1000 V local capacitors
on BUS_P/HV_RET, splits cord PE into chassis stud plus J6 PCB branch,
replaces coil termination with separate J2/J5 M4 studs, makes C3/C4 pads
smaller, and adds both external removable rail links J7–J10. This revision
is now compiled and audited: 114 components, 75 nets and 48 passing audit
tests. [NATIVE-02.md](NATIVE-02.md) records the regenerated native evidence.
The links are external assembly connections; BR1 outputs and J7/J9 remain
mains-live with mains present and the links removed. Designators after
`u_ocp` moved in the earlier source changes (for example `u_iso` U7 → U9).

The OCP comparator's ±5 mV offset alone corresponds to a 51–71 A threshold
spread; other component and timing tolerances are not included. The 511 V
figure at 71 A is a 198 V-start heuristic, not a rating margin or an upper
bound (Q1). The OVP threshold is a restart inhibit through the controller
latch, like the OCP; it does not clamp an already rising bus.
