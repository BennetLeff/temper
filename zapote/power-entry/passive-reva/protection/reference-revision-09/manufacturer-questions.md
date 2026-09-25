# Application-data questions — drafts, not sent

These drafts name the missing evidence that prevents qualification. The project
is simulation-only; no supplier has reviewed or approved this application.

## TI / Vishay: UCC28180 with BAV23C-E3-08

Our proposed negative ISENSE clamp uses one BAV23C die: anode at controller
ground, cathode at ISENSE after 220 Ω, with 1 nF from ISENSE to ground. The
unused common-cathode package anode is left unconnected. The shunt is 10 mΩ.
We need to preserve UCC28180 current limiting through the worst-case −0.438 V
threshold while limiting negative excursions to the recommended −1.1 V.

Please provide or identify:

1. Guaranteed forward-current bounds near 0.345–0.438 V, and forward-voltage
   bounds over the actual clamp-current range, across −40 to +125 °C and
   production variation. Typical curves alone cannot supply these bounds.
2. TI's allowable clamp-induced ISENSE error/current around PCL, including
   input bias and blanking effects. Our 1 µA/2 mV screen is a chosen engineering
   screen, not a TI requirement.
3. Application-qualified alternatives or topology guidance if this exact diode
   cannot meet the window. Is there a validated external-clamp design with
   appropriate guarantees rather than only a typical model?
4. Pulse-energy, capacitance/recovery and input-current conditions needed to
   validate inrush/fault operation. The project has not yet established a
   worst-case shunt waveform; a −5 V stimulus is only an illustrative fixture.

The existing assumed diode model fails its chosen hot PCL-loading screen at
85 and 125 °C. We are not asserting this is a measured failure of BAV23C.

## Mersen: A70QS50-14F with US141/Z331153

The proposed fuse lies between a boost diode's cathode/local reservoir (VD)
and a 2240 µF capacitor bank (VB). Nominal regulation is about 390 V; the bulk
capacitors are rated 450 V. A 500 V screen in an authored simulation is not
an allowed continuous operating voltage. In the bank-discharge fault, both
the boost diode and MOSFET may be shorted. The bank loop bypasses the mains
fuse and current shunt. Its ESL, ESR, failed-device impedances and peak current
are not yet bounded; the boost inductor's 180 µH must not be assigned to this
different loop.

Please clarify:

1. Applicability of the published 890 Vdc capacitor-discharge rating to this
   lower-voltage application, and the exact test circuit/waveform and meaning
   of the stated 2.5 ms time constant. We have not assumed it means L/R.
2. Minimum breaking current, allowed prospective peak, arc voltage, and
   capacitor-discharge total-clearing I²t or let-through envelope, with
   voltage, C, ESR, ESL, temperature and mounting conditions.
3. Whether the published 700 Vac clearing I²t has any authorized DC
   application conversion. We currently do not use it as a DC guarantee.
4. Fuse/holder thermal compatibility at the actual pulsed charging RMS current,
   ambient and enclosure conditions; the 50 A nameplate alone is insufficient.
5. Recommended protection arrangements for the local capacitor on the VD side,
   whose discharge loop can bypass F2 when the boost diode also fails short.

## Schurter: 0034.3129 in 0031.2510

Our baseline names a 16 A FST 5x20 link in the AC line before the bridge, over
a 108–132 VAC study range. Its published breaking-capacity condition is
10×In at 250 VAC. The physical prospective short-circuit current is unknown;
the simulation's 0.25 Ω source resistor is not a measured installation bound.

Please identify applicable 120 VAC interrupting and total-clearing data,
including coordination with upstream protection. If the existing low-breaking-
capacity link cannot cover the intended prospective current, please identify
appropriate high-breaking-capacity options and compatible holders, with
inrush, thermal and approval constraints. No replacement is selected by this
draft, and the typical melting I²t is not treated as a clearing guarantee.
