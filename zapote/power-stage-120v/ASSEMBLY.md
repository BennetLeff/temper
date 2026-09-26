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
| Positive removable link | J7 / `link_pos.terminal_rect` to J8 / `link_pos.terminal_bus` | Two Würth 74650074 |
| Negative removable link | J9 / `link_neg.terminal_rect` to J10 / `link_neg.terminal_bus` | Two Würth 74650074 |

The board BOM contains **six** REDCUBE terminals. Each has four same-number
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

Each removable link is a rigid **strap** fitted over the two studs of one row
(J8–J7, J10–J9; 13.0 mm stud pitch): tinned copper flat bar 10.0 × 1.5 ×
23.0 mm with two 4.3 mm holes at 13.0 mm centres, 5.0 mm from each end, held
by M4 × 8 pan-head screws with spring and plain washers. This is a custom part
(PROVISIONAL): confirm the drawing, plating and at least 20 A continuous
capability at the actual enclosure temperature, including both contacts,
before powered service. A cable jumper with two ring lugs does not fit this
pitch: two 10 × 21 mm lugs facing each other at 13 mm overlap by 19 × 10 mm
(`terminal_envelopes.json`, checked by `tools/placement_metrics.py`).
Bench-supply leads in bring-up use **Würth 5580406** M4 ring lugs on J8/J10,
leaving the left board edge.
[Würth lug](https://www.we-online.com/components/products/datasheet/5580406.pdf).

M4 screws and locking washers must suit the actual strap or lug stack and thread
engagement, without bottoming or contacting other metal below the PCB.
Record screw length, locking method and torque during the enclosure review;
do not call a screw connection vibration-proof before retention testing.
The coil lead termination must match the actual litz/pigtail conductor and
crimp process; the bench-lead lug is not automatically suitable for it.

The bare REDCUBE has no manufacturer voltage rating. Use at least 30 mm
centers between the coil studs as an initial placement target (about 20 mm
between 10 mm lug envelopes), and check actual exposed metal, screw heads,
wire bend envelopes and both PCB faces. The approximately 540 V peak nominal
coil voltage is not a maximum fault bound. High-frequency creepage and
clearance remain part of the insulation review. Keep every PE branch pad,
lug, screw and trace at least 8 mm from HOT under D5's provisional basis.

## Protective earth

Cord PE bonds **directly** to the chassis/heatsink stud. A separate branch
wire connects that stud to J6. The board and R38 are never in series with
the primary protective-earth connection. R38 joins PE to controller ground
for functional earthing only. Mains neutral is not PE. The PE stud's locking,
torque, continuity and strain relief belong to the enclosure assembly.

## Normal and bring-up configurations

| Mode | Positive strap | Negative strap | External DC input |
| --- | --- | --- | --- |
| Normal mains run | J7 RECT_P to J8 BUS_P fitted | J9 RECT_N to J10 HV_RET fitted | None |
| Floating 30–60 V bench bus | Removed | Removed | Positive J8 BUS_P; negative J10 HV_RET |

The source deliberately keeps each link's endpoints on separate nets and
represents the physical landings. **The external straps, not PCB copper,
complete the normal circuit.** The audit requires each RECT net to contain
only its BR1 output and rectifier-side terminal. All bulk and local bus
capacitors, the TVS, bus bleed, divider and shunt stay downstream.

Both straps must be removed while all supplies are disconnected and the
bus and resonant capacitors are verified discharged. Secure the removed
straps so they cannot fall onto the board. Connect the floating supply only
to J8/J10; connecting its negative to LEG_RET bypasses the OCP shunt.
Independent verification of both open paths is required before mains or
bench power is applied. A single open positive link is insufficient.

With mains present, the filter, BR1, J7/J9 and both IRM primaries remain live.
The IRM-05 output still powers V15_LS, HOT5 and gate drivers when the thermal
loop is closed. The IRM-20 still powers the controller domain. Their isolation
barriers and the two open link gaps remove intended galvanic mains paths
to the bridge rails; leakage and capacitive coupling remain. This does not
make the entire PCB touch-safe. Guard the live section and use appropriately
isolated differential measurement equipment; ordinary grounded probe clips
are not a substitute for the intended isolation.

Before a powered procedure is released, verify on the assembled unpowered
board that neither RECT terminal has continuity to either bus terminal with
both straps removed, and verify the absence of unintended PCB or hardware
bridges. The source and unrouted-native checks do not perform this physical
test. Interlock startup, current limit, fault shutdown and supply sequencing
remain bench-validation items.
