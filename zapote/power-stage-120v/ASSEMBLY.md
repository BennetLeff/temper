# Prototype power connections

This is the approved prototype connection scheme, not an instruction to
energize an unreviewed board. Native-02 is still an unrouted shelf. Physical
spacing, insulation, heat, torque retention and powered tests have not run.

## PCB and external parts

| Function | PCB reference / source instance | Exact PCB part |
| --- | --- | --- |
| Mains L/N | J1 / `j_mains` | Phoenix 1711725, 5.08 mm two-position |
| Coil feed | J2 / `j_coil` | Würth 74650074 M4 REDCUBE THR |
| Coil return | J5 / `j_coil_return` | Würth 74650074 M4 REDCUBE THR |
| PE branch | J6 / `j_pe` | Phoenix KDS 3 / 1704004, one potential, two solder pins |

Stage 21 (DECISIONS 25) removed the J7–J10 removable rail links: BR1 feeds BUS_P / HV_RET directly.
The board BOM contains **two** REDCUBE terminals (J2, J5). Each has four same-number
copper pads on one metal terminal; all must land on the intended net. The
central non-plated hole is for the screw, not an electrical pin. Würth rates
the terminal 50 A maximum at 20 °C and specifies a 1.6–2.0 mm PCB and
1.2 N·m torque. Operating current depends on the PCB, lug and wire. This is
a selected component rating, not a 50 A rating for the completed board.
[Würth drawing and ratings](https://www.we-online.com/components/products/datasheet/74650074.pdf).

Würth specifies THR reflow assembly for 74650074; wave soldering is not
applicable. The specified PCB thickness is 1.6–2.0 mm. The planning stackup
is nominally 1.6 mm, so confirm the fabricated thickness and tolerance stay
within the terminal's range before ordering. Also review copper weight,
plated-hole process and the terminal's thermal profile with the assembler.


M4 screws and locking washers must suit the actual coil-lug stack and thread
engagement, without bottoming or contacting other metal below the PCB.
Record screw length, locking method and torque during the enclosure review;
do not call a screw connection vibration-proof before retention testing.
The coil lead termination must match the actual litz/pigtail conductor and
crimp process; the bench-lead lug is not automatically suitable for it.

J2 (COIL_FEED) and J5 (RES_A) are at 15.0 mm centres (decision 2026-10-08, review M6).
- **Insulation basis:** their insulation is functional (IEC 60335-1:2020 29.2.4, Table 18, PD3, group IIIa). The coil-terminal working voltage in normal use is ≤ 362 V rms at the 28 A ceiling (with a pan; the no-pan clamp holds 22 A), so creepage needs ≤ 4.6 mm, covered by the 5.0 mm tank rule (≤ 400 V rms). The no-pan 28 A fault point is 409 V rms / 818 V pk (DECISIONS M6, 28 A update; `owner-items/m6m10/coil-voltage-28a/`). Clearance needs ≥ 1.3 mm (Table 16 PD3 + 0.5 mm for assembled parts), pending the IEC 60664-4 check.
- **Board gap:** the copper gap is 5.0 mm.
- **Terminations:** coil leads end in **insulated M4 ring terminals**, insulated over the barrel and neck up to the ring.
  - The bare ring is ≤ 10.0 mm wide, with a DIN 125 M4 washer (9 mm) and a pan-head M4 screw (head ≤ 8 mm). This keeps exposed metal ≥ 5.0 mm apart at any lug rotation (29.1/29.2 "most unfavourable position").
  - **Bare ring lugs are not permitted on J2/J5:** they can be turned into contact at any pitch below about 37 mm.
  - **Upturned terminals:** the ring tongue is formed 90° upward, so the barrel stands vertical and the Litz leaves within ~10 mm of each stud axis. **J2 constraint (enclosure R26):** J2's barrel axis must be ≤ 8 mm from the stud axis, and/or barrel plus insulation OD ≤ ~7 mm for the first ~12 mm above the ring. It sits beside T1 (CST3015), whose body top is at world Z 42.8. J5 has room. In R26 the Litz drops straight to the barrel top (~Z 57), at world (9, 142.5) for J2 (the coil's outer turn, r 119.8 mm) and (9, 173.5) for J5. Each barrel is offset away from the other stud, along the J2–J5 line. A horizontal barrel in any direction collides with parts: C21/C22, the U16/U26 block, T1, or the other stud and J7 (enclosure R26 screen, 2026-10-08).
  - The lug's insulation temperature rating must exceed the lead temperature measured at the stud. The lug part, for example TE PLASTI-GRIP 2-34853-1 (vinyl, 105 °C), is confirmed against that measurement and the Litz cross-section with the coil supplier. A bare upturned (flag) M4 ring with dual-wall ≥ 150 °C heat-shrink over the barrel and bend up to the ring meets the requirement. A moulded insulated upturned ring does too, if one is found for the Litz size. No straight-barrel part is acceptable. Keep every PE branch pad,
lug, screw and trace at least 8 mm from HOT under D5's provisional basis.

**THT lead trim (insulation, 2026-10-09):** after soldering, trim every through-hole lead to **≤ 2.5 mm below the board bottom**. That covers Q2/Q3/Q5/Q6, BR1, the film capacitors, the resonant bank and the connectors. Untrimmed TO-247 leads reach 14 mm below the board, to within 0.8 mm of the PE base. Trimmed, all HOT metal stays ≥ 12.5 mm from the base (enclosure R31). Inspect it as part of the board's visual check.

**X2 capacitors C1/C2 (R463N410050N1K):** these come with 25 mm leads. Cut them to 4 mm before insertion (KEMET R46 p.2).

## Protective earth

Cord PE bonds **directly** to the chassis/heatsink stud. A separate branch
wire connects that stud to J6. The board and R38 are never in series with
the primary protective-earth connection. R38 joins PE to controller ground
for functional earthing only. Mains neutral is not PE. The PE stud's locking,
torque, continuity and strain relief belong to the enclosure assembly.

## Normal and bring-up configurations

| Mode | BR1 | External DC input |
| --- | --- | --- |
| Normal mains run | Fitted (on the heatsink) | None |
| Floating 30–60 V bench bus | **Not fitted** | Positive into BR1's `+` hole (BR1.1, BUS_P); negative into BR1's `−` hole (BR1.4, HV_RET) |

Stage 21 (DECISIONS 25) replaced the J7–J10 removable rail links. BR1's DC pins sit
on the BUS_P / HV_RET planes, so the bench build simply leaves BR1 out: with no
bridge fitted there is no galvanic path from the mains filter to the bus, on
either rail, and the empty BR1 holes are the bench landings. All bulk and local
bus capacitors, the TVS, bus bleed, divider and shunt stay downstream of them.

- Connect the floating supply **only** to BR1.1 (+) and BR1.4 (−). Connecting
  its negative to LEG_RET bypasses the OCP shunt (the audit pins BR1.4 to HV_RET,
  never LEG_RET).
- Solder the bench leads into the holes (or use a pin adapter); do not fit BR1 and
  bench leads at the same time.
- Verify on the unpowered board, before bench power, that BR1 is absent and that
  neither BR1 AC hole (BR1.2 L_FILT, BR1.3 N_FILT) has continuity to BR1.1 or BR1.4.
- With mains present on a bench build, the filter, the BR1 AC holes and both IRM
  primaries remain live. The PS2 IRM-20-24 output still powers V15_LS, HOT5 and the
  gate drivers when the thermal loop is closed; the PS1 IRM-20-15 still powers the
  controller domain. This does not make the entire PCB touch-safe. Guard the live
  section and use isolated differential measurement equipment; ordinary grounded
  probe clips are not a substitute for the intended isolation.
- Fitting BR1 for mains operation is a heatsink assembly step (thermal interface,
  clamp torque) followed by the same continuity checks in reverse. Interlock
  startup, current limit, fault shutdown and supply sequencing remain
  bench-validation items.
