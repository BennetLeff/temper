# PFC power-entry functional review

Review date: 2026-09-11.  Scope is the current prototype
`/private/tmp/temper-power-entry-20260912/elec/src/power_entry_unit.ato`.
This is a source-and-datasheet review; it is not a thermal, EMC, insulation,
or mains safety qualification.

## Highest-priority blockers

1. **The bypass relay is overdriven and overrated in the source.** `RT33K012`
   is a 12 V dc coil, with 360 ohm nominal resistance and a 16 A contact
   rating in the TE/Schrack product data. The source applies `aux_15v`
   directly to `coil1` and declares `contact_current = 20A`. At 15 V, the
   nominal coil current is about 41.7 mA and dissipation 0.625 W, versus
   about 0.4 W at its 12 V rating. Use a specified 12 V coil supply or a
   documented current-limiting/drop arrangement, and change the contact
   assumption to the exact relay rating and load category. The source's
   AO3400A low-side topology and SS14 flyback polarity are structurally
   plausible after that correction. Evidence: [TE RT33K012 product data](https://www.te.com/en/product-2-1393240-3.html).

2. **The controller passives are unresolved and cannot support a build claim.**
   Every `PfcResistor` and `PfcCapacitor` still has an unresolved generic
   MPN. In particular, `r_vtop = 768k` is one 1206 resistor directly across
   the approximately 390 V bus; its working-voltage, pulse, and power
   ratings are unspecified (and a generic 1206 should not be assumed to
   tolerate that voltage). Split the feedback resistor into a rated series
   string or bind a part with an explicit working-voltage rating. `r_freq =
   10k`, `r_vcomp = 10k`/`c_vcomp = 10nF`, and the ICOMP network are labelled
   “starting values” but have no switching-frequency, loop-gain, current
   limit, or compensation calculation for this power stage. The TI example
   uses a different VCOMP network (including a 4.7 uF, >=10 V capacitor), so
   these values cannot be treated as copied design values. The unresolved
   0805 `c_vcomp` also has no voltage rating; TI specifies the VCOMP pin
   absolute limits and compensation parts must be selected against them.
   Evidence: [TI UCC28180 datasheet, pp. 6, 17–18, 27–28, 36–37](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).

3. **The auxiliary interface contradicts the “SELV” comment.** `aux_15v_return`
   is explicitly tied to `control_gnd`, and `control_gnd` is the rectifier
   negative / PFC bus negative. Thus the two-pin AUX header is not an
   isolated SELV interface in this netlist. The comment says the source must
   be a separately qualified isolated source, but an isolated supply's
   secondary return cannot be bonded to this HV reference without an
   intentional isolation decision. Define the actual bias-supply topology,
   isolation barrier, creepage/clearance, and connector touch-access
   assumptions before treating AUX or the relay-control header as SELV.

4. **The bridge current field omits its required heatsink condition.**
   `GBU2510A` is 25 A only with the manufacturer's specified heatsink; the
   no-heatsink rating is 3.6 A. Its pin order in the source (`-`, AC1, AC2,
   `+`) agrees with the manufacturer drawing, but `current_rating = 25A`
   is not a valid standalone thermal claim. The C3D20065D pin declaration
   (`A1/K/A2`) also agrees with the Wolfspeed drawing, while its 20 A field
   likewise needs a junction/case temperature and heatsink path; at hot
   case limits the allowable current is lower than the 25 C headline value.
   Evidence: [Diodes GBU2510 datasheet, pp. 1–4](https://www.diodes.com/datasheet/download/GBU2510.pdf),
   [Wolfspeed C3D20065D datasheet, pp. 1 and 6](https://assets.wolfspeed.com/uploads/2023/12/Wolfspeed_C3D20065D_data_sheet.pdf).

5. **The input protection and EMI BOM is not yet traceable to a verified
   physical assembly.** The fuse link `0034.3129` exists only in a comment;
   the actual component is the holder `0031.2510`, so fuse type, interrupt
   rating, voltage rating, and replacement identity are absent from the
   compiled component inventory. The CMC's custom footprint and pin naming
   (`B82726S2163N030`) need the manufacturer's terminal drawing checked
   against the footprint; its declared 16 A is not evidence of hot RMS
   capability. The NTC and 150 uH inductor similarly need the actual
   temperature/current curves in the assembled thermal environment.

## Checks that are presently structurally consistent

The source routes bridge `MINUS -> shunt.p2`, with controller ISENSE through
220 ohm to that rectifier-side node and the clamp diode anode there, while
shunt.p1 is the controller return. That matches the negative-current-sense
polarity and clamp arrangement in TI's Figure 26, subject to confirming the
physical shunt pad orientation. `FREQ` has a resistor to controller ground,
VCC has a local capacitor, and the GATE has an external resistor and 10 k
pulldown, all consistent with the controller's required topology. The
boost diode's two anodes at MOSFET drain and common cathode at `hv_plus`,
and the GBU `- ~ ~ +` declaration, are the right electrical relationships.

The four 560 uF / 450 V capacitors are all placed in parallel between
`hv_plus` and `hv_minus`; this is an active-boost bus bank, not a passive
voltage-doubler pair. That is structurally fine for the PFC architecture but
must not be reported as evidence for the earlier doubler calculation. The
exact `B43504A5567M000` identity and the declared 3 A ripple figure still
need a current manufacturer datasheet or controlled distributor record.

## Qualification gaps to keep explicit

Structural net checks can establish pin connectivity, polarity, and that
the intended feedback/sense components exist. They do not establish the
UCC28180 loop stability, 130 kHz operating point, current-limit margin,
startup/inrush behavior, bridge/diode/MOSFET junction temperature, CMC or
NTC hot impedance, capacitor ripple life, relay contact inrush endurance,
EMI performance, or insulation/SELV compliance. The source currently has no
measurement or calculation artifact closing those gaps. The Y1 connection
from `hv_minus` to PE is a deliberate functional-earth path, but its safety
class, AC rating, leakage, and exact approved part must be verified from the
actual B81123C1562M000 datasheet rather than inferred from `dielectric =
"Y1"` and `voltage_rating = 500V`.
