# Oracle answer: bus bound, boundary voltages, insulation consequences

Response to the focused questions in [ORACLE-REVIEW.md](ORACLE-REVIEW.md),
2026-09-25. Supersedes the earlier external answer. Numbers come from
`tools/bus_voltage_sim.py` (lumped model: ideal diodes, no stray inductance,
no snubbers). They are design estimates, not measured bounds.

Physical overshoot, touch-current, CT injection, hipot and emissions tests:
**NOT RUN**. No fabrication or certification approval is implied.

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

## Q1: DC-link bound

Assumptions: 127 V + 10 % line (198 V crest), bus 4.5 µF (5 µF − 10 %),
Cr = 0.54 µF, turn-off at the worst switching phase, trip latency 300 ns.

| Case | Worst Vbus |
| --- | ---: |
| Normal shutdown at full power (70 µH / 48 µH loaded) | 222 / 234 V |
| OCP trip at 91 A, driven at resonance (48 / 70 / 100 µH) | 358 / 451 / **469 V** |
| OCP trip at 60 A, driven at resonance (48 / 70 / 100 µH) | 280 / 339 / 356 V |
| Differential surge, limited by RV1 (TMOV20RP175E) clamp | ≈ 460 V |

- Fixed-frequency drive above resonance cannot reach 91 A (53–78 A even with
  the pan removed). The trip is reached only by driving at or near resonance:
  a controller fault, a start-up sweep through resonance, or a lifted pan.
- Line phase: the worst case is turn-off at the line crest. Turn-off near the
  line zero returns little energy, since tank current scales with the bus.
- The film bus is rated 600 VDC and the MOSFETs 650 V. At a 91 A trip the
  469 V estimate plus commutation ringing leaves too little margin.

**Missing controls (recommended source changes):**

| # | Control | Effect |
| --- | --- | --- |
| S1 | Lower the OCP trip from ≈ 91 A to ≈ 60 A (retune R30/R31) | Worst trip return 469 → 356 V. Still 33 % above the 45 A worst normal peak (48 µH, high line). |
| S2 | Add a HOT-side bus over-voltage comparator on the bus divider into the existing fault latch, ≈ 280 V | Hardware restart inhibit. The bus bleed takes seconds, so firmware must not restart into a pumped bus. |
| S3 | Add a bleed resistor across the resonant bank C21–C23 | After a trip Cr can hold up to ≈ ±190 V with no discharge path: a service-shock hazard. |

A bus TVS clamp is not required once S1 is in; the surge case (≈ 460 V) is
the governing transient and is within component ratings. Measure the actual
overshoot on the bench before accepting that.

**Controller ground ↔ PE: keep the single-point bond.** It defines the
controller potential. The externally earthed controller case produces
identical voltages, so the design must meet it regardless.

## Q2: differential voltages at each HOT/SELV crossing

Controller at PE (bonded, or externally earthed with PE intact). N ≈ earth;
the bounds are symmetric in L and N, so reversed polarity (common with
unpolarized Mexican outlets) gives the same numbers.

| Node | Crossing | Rated 127 V | 127 V + 10 % | Band (rms) |
| --- | --- | --- | --- | --- |
| BUS_P, HV_RET, SW_A, SW_B | U1, U2 (UCC21550), U4 (AMC1311), U7 (ISO7710) | 90 V rms, 180 V pk | 99 V rms, 198 V pk | >50–125 |
| RES_A / coil_ret (T1 primary today) | T1 | 165–220 V rms, 457–582 V pk at 33–60 kHz | up to 242 V rms, 640 V pk | >125–250, plus HF |
| PS1 (IRM-20-15) mains input, kept separate from the DC rails | PS1 | 127 V rms, 180 V pk | 140 V rms, 198 V pk | >125–250 (127 V is just above 125) |

The RES_A range spans the 70 µH and 48 µH loaded coils.

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
- IEC 60664-4 applies above 30 kHz. It matters only at the tank node
  (RES_A/coil_ret), i.e. at T1 in the current topology.
- **Recommended basis:** design the entire SELV barrier to **≥ 8.0 mm**
  (PD3, IIIa/IIIb, reinforced). That meets the >125–250 band everywhere, so
  the per-node band argument above never has to be defended to a lab. The
  band results are retained as conditional justification only.
- **Current exception:** U7 (ISO7710FDWR) uses KiCad's stock
  `SOIC-16W_7.5x10.3mm_P1.27mm`, which gives **7.25 mm** copper across the
  barrier. It meets 4.8 mm for its rail crossing but not the uniform 8.0 mm
  basis. Replace it with TI's high-voltage DW land pattern, as was done for
  U1/U2 (`SOIC16W_Isolated`, 8.1 mm). U4's stock SOIC-8 DWV pattern gives
  8.85 mm and is fine.

## Q4: CT relocation

**Current source (confirmed from the frozen netlist):**
SW_A → J2 → coil → coil_ret → T1 → res_a → C21–C23 → SW_B.
T1's primary sits at the resonant node: up to 242 V rms and 640 V pk at
33–60 kHz relative to its SELV secondary.

**Proposed:** SW_A → T1 → J2 → coil → coil_ret → C21–C23 → SW_B.

- T1's primary moves to a switch node: 99 V rms, 198 V pk. The crossing drops
  to the >50–125 band and the IEC 60664-4 HF question at T1 disappears.
- The dv/dt seen through T1's interwinding capacitance is unchanged: the
  res_a node already carries SW_B's edges.
- No BOM change. Firmware may need to flip the current-sense sign.
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

## Source changes to make before placement

Each requires re-audit, re-freeze and a new native build (Parts 1 and 3).

1. Relocate T1 (Q4).
2. S1: OCP trip ≈ 60 A.
3. S2: bus over-voltage comparator into the fault latch.
4. S3: resonant-bank bleed resistor.
5. Replace U7's footprint with an HV DW land pattern (≥ 8.0 mm across the barrier).

Then Part 4 proceeds with D5 set to "uniform ≥ 8.0 mm reinforced, PD3,
IIIa/IIIb", conditional on the Coilcraft evidence.
