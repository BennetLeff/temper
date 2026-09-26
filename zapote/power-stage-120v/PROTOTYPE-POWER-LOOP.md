# Prototype power loop and approved parts

The 2026-09-25 source revision implements the owner's power-loop and connector
choices. The regenerated native-02 board matches the revised source; it is an
unrouted shelf, as recorded in [NATIVE-02.md](NATIVE-02.md). The positions, copper,
insulation, heat and assembled wiring still require review. The physical
connection scheme and exact terminal hardware are in [ASSEMBLY.md](ASSEMBLY.md).

## DC link and local commutation loops

C5/C6 are TDK **B32656G0275J000**, 2.7 µF ±5%, 1000 VDC four-pin radial
polypropylene parts. Each has two BUS_P pins at one end and two HV_RET pins
at the other. Their 5.4 µF bulk bank replaces 5.0 µF. Four TDK
**B32652A0104K000**, 100 nF ±10%, 1000 VDC, 15 mm pitch radial parts add
0.4 µF: C38/C39 by leg A and C40/C41 by leg B. The nominal total is
**5.8 µF**. The four-pin part's height is 48 mm; vibration retention and
heatsink clearance require placement and assembly review.

Every local capacitor returns to **HV_RET**, not LEG_RET. A LEG_RET return
would let shoot-through current bypass R5 and blind the DC over-current
comparator. Put two near each MOSFET pair while keeping the path through
R5's power pads short and broad; the Kelvin sense path stays separate.
Each local part is rated 5.4 A RMS at 85 °C/100 kHz and 975 V/µs, but
these conditions do not establish current sharing or temperature in the
assembled loop. Measure capacitor heating and bus/MOSFET overshoot.
[TDK film-capacitor tables](https://product.tdk.com/en/system/files/dam/doc/product/capacitor/film/mkp_mfp/data_sheet/20/20/db/fc_2009/mkp_b32651_658.pdf).

The selected MRT130KP295CV TVS D3 connects BUS_P to HV_RET at the bulk
capacitors. Its datasheet pulse clamp excludes lead and PCB inductance;
[DC-LINK-CLAMP.md](DC-LINK-CLAMP.md) records the surge-coordination work.
The [Rust capacitor screen](BUS-CAP-SCREEN.md) compares 5.0, 5.4 and
5.8 µF. At fixed assumed ripple current, the ideal 33 kHz capacitive
voltage term falls 13.8% from 5.0 to 5.8 µF. The script assumes 0.95
power factor; it cannot confirm actual PF or line-current harmonics.

## Resonant bank

Keep CDE **942C12P22K-F** at C21/C22 and **942C12P1K-F** at C23. The
0.54 µF bank is unchanged. The screened TDK 0.22 µF radial alternative
has 132 A derived peak versus CDE's 628 A; the 0.10 µF alternative has
60 A versus CDE's 285 A. Those pulse comparisons favor retaining the CDE
parts. Actual tank waveform, loss and temperature still need measurement.
[CDE 942C](https://www.cde.com/resources/catalogs/942C.pdf),
[TDK series](https://product.tdk.com/en/system/files/dam/doc/product/capacitor/film/mkp_mfp/data_sheet/20/20/db/fc_2009/mkp_b32651_658.pdf).

## Entries, coil leads and protective earth

J1 is the two-position Phoenix **1711725**, 5.08 mm pitch, for L/N.
Cord PE bonds directly to a chassis/heatsink stud; a separate branch
goes to J6, Phoenix **1704004**. J6 and PCB copper are never the primary
protective-earth path. Keep J6 pads and its hardware at least 8 mm from HOT
under the provisional D5 placement basis. C3/C4 keep their 10 mm Murata
lead pitch with smaller 1.5 mm pads, giving an 8.5 mm nominal copper gap;
inspect both PCB faces and the component's own insulation path.

J2 and J5 are separate Würth **74650074** M4 threaded terminals for the
coil lead ends. The published 50 A maximum is at 20 °C; the assembled
PCB/lug/wire path is not thereby rated 50 A. The bare terminal has no
manufacturer voltage rating. Start with at least 30 mm centers, then check
the coil's differential voltage, exposed metal, lugs, wiring, clearance and
high-frequency insulation. The coil voltage estimate of roughly 540 V
peak is a nominal operating example, not a maximum fault bound.

J7/J8 and J9/J10 form two independent, external, removable links between
BR1 and the bus rails. Both links fitted give normal operation. With both
removed, a floating 30–60 V bench supply connects to **J8 BUS_P and J10
HV_RET**. BR1, J7/J9 and both IRM primaries remain mains-live when mains
is present; the IRMs can still power their respective auxiliary domains.
The open links do not make the whole board touch-safe. The assembly plan
specifies the provisional 6 mm² jumpers, lugs, current check and unpowered
continuity checks before any bring-up procedure is released.

## Placement holds

Allocate probe access to gate/source returns, both switch nodes, shunt
Kelvin nodes, CT output and a tank lead current-probe segment. Place the
heatsink, loop, barrier, links and connector wiring as a system. D4 still
requires written approval of the deliberate placement before routing.
The certification-lab call and RCA 12A3 teardown remain open; neither has
been performed. D5 authorizes an 8.0 mm provisional placement floor,
not final insulation qualification.
