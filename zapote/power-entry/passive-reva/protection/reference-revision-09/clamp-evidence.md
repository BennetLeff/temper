# ISENSE clamp evidence — reference revision 09

Status: **source correction and isolated-candidate evidence only**.  This
record does not change the retained Atopile source, select a production diode,
or qualify the UCC28180 ISENSE input.

## Decision

The retained 54-component source names Nexperia **BAT54H,115** in SOD-123F.
Its package pinout is pin 1 = cathode (K), pin 2 = anode (A).  The source
currently connects A to `shunt.p2` and K to `control_gnd`, before the 220-ohm
ISENSE resistor.  Since the sensed shunt excursion is negative, that diode is
reverse biased during the excursion that needs protection.  It is not a
negative ISENSE clamp.

The negative-clamp topology required by TI is a diode on the controller side
of the series resistor: **A = control ground, K = the post-220-ohm ISENSE
node**.  For BAT54H this corrected mapping is pin 2 (A) to ground and pin 1
(K) to `pfc.ISENSE`.  The 1-nF capacitor remains from that controller-side
node to ground.  This is a topology correction, not evidence that BAT54H is
an acceptable selected part.

The BAT54H is a Schottky diode. Nexperia specifies maximum VF of 0.240 V at
0.1 mA, 0.320 V at 1 mA, and 0.400 V at 10 mA (pulses ≤300 µs,
duty factor ≤0.02, ambient 25 °C, Table 7). These are several characterized
points, not just a 10-mA rating. It does not publish a guaranteed low-current
`VF(min)/VF(max)` envelope over the UCC28180 electrical range.  The specified
10-mA maximum is below TI's 0.438-V worst-case PCL threshold, so a corrected
BAT54H orientation can load or cross the PCL threshold before the intended
negative clamp.  Its low-current behavior cannot be inferred from the 10-mA
point.  Therefore the corrected BAT54H is suitable for an isolated polarity
and sensitivity experiment only; it is not a qualified clamp choice.

The existing isolated clamp candidate uses one die of Vishay **BAV23C-E3-08**
(common-cathode SOT-23), not BAT54H.  Its checked graph is:

```text
220 ohm: bridge-minus/shunt.p2 -> controller-side ISENSE
BAV23C die: A = control_gnd (SOT-23 pin 1), K = ISENSE (pin 3)
unused die anode: explicit NC net (pin 2)
```

The candidate source, export graph, and checks are already retained under
`operating-matrix-07/clamp`; revision 09 should reuse those identities rather
than create a second BAV23C experiment.  The candidate source SHA-256 is
`4d63a25896e3bd3ed9cb242c2d074a225de71acdb3351bfcbae24b2f73c6fdbb` and the
worker export graph SHA-256 is
`8b7f452b8a92f410140dfb75476115455f894aba550ea5541976a325cfa6da55`.
The Rust graph check observed pin 1 on control ground, pin 3 on the
controller-side ISENSE node, and pin 2 alone on `a_unused`.

## TI window and what the vendor data says

TI UCC28180 Rev. D, §8.3.14, says that ISENSE should remain from 0 V to
−1.1 V.  The external diode forward voltage must be **greater than the
maximum PCL magnitude, 0.438 V, and less than 1.1 V over temperature and
component variation**.  The same datasheet gives PCL −0.345 V minimum,
−0.400 V typical, and −0.438 V maximum, and shows the 220-ohm series path
and 1-nF-class filter in the reference implementation.  The ±1-mA ISENSE
input-current and −24 V/+7 V pin-voltage numbers are absolute damage limits,
not sensing-error budgets.

Vishay's BAV23C datasheet specifies 250 V minimum reverse breakdown, `VF <=
1.0 V` at 100 mA and `VF <= 1.25 V` at 200 mA, all at 25 °C, with an
operating range of −55…150 °C.  It does **not** specify guaranteed
low-current VF bounds around 0.438 V or 1.1 V across temperature, lot, and
the actual resistor-limited clamp current.  Figure 1 is a typical forward
curve; its apparent conduction around 0.438 V is evidence that PCL loading is
possible, not a production limit.  Consequently BAV23C cannot be said to
“close” the TI window at temperature from this datasheet alone.  The existing
1-µA/2-mV fixture limits remain engineering screens, not TI or Vishay limits.

## Provisional next simulation candidate

An isolated, source-aligned simulation may advance with the following exact
net topology and explicit scope:

1. Keep the 220-ohm resistor between `shunt.p2` and the controller-side
   `pfc.ISENSE`; keep the 1-nF filter to control ground.
2. Put one selected-die diode from controller-side ISENSE to ground with
   **A at ground and K at ISENSE**.  If modeling the physical BAT54H, use
   pin 2/A at ground and pin 1/K at ISENSE.  If reusing the existing isolated
   BAV23C candidate, use SOT-23 pin 1/A at ground, pin 3/K at ISENSE, and
   leave pin 2 explicitly unused as its graph already does.
3. Keep the feedback choice explicit.  The canonical 54-part source is VB
   feedback; revision 08 is a separate VD-feedback candidate.  Do not use a
   clamp result to claim that either feedback ECO is accepted.
4. Preserve F2 as the proposed ideal fuse/open-fault element.  F2 is not a
   controllable precharge or clamp actuator and supplies no diode evidence.

This candidate can be compiled and run as an isolated polarity, PCL-loading,
temperature-sensitivity, and resistor-current experiment.  It may report
conditional model results and the exact netlist/model identity.  It cannot
advance to a source-faithful converter or hardware claim until the selected
part and controller-side transient are separately bounded.

## Remaining qualification data

The following are still missing and cannot be manufactured by another nominal
SPICE run:

* a BAT54H or BAV23C production `VF(min)/VF(max)` envelope at the actual
  sub-mA-to-mA clamp current, over at least the UCC28180 −40…125 °C range,
  including lot/tolerance information;
* diode reverse leakage, capacitance, recovery, and pulse/SOA data in the
  assembled 220-ohm/1-nF topology;
* a bounded shunt transient and resistor/diode pulse-energy calculation (the
  illustrative 5-mA value is not an unconditional inrush bound);
* controller-side measurements or a silicon-anchored model for PCL loading,
  input current, and propagation during the fault waveform; and
* assembled temperature/pulse characterization at the ISENSE node if the
  vendor does not provide the required VF envelope.

The historical 133-part `source-build-07` experiment remains rejected and is
not evidence for this correction.  Revision 08's VD-feedback netlist remains
the unchanged assumed-BAV23C model; it does not represent the physical
BAT54H.  Source correction and component qualification must remain separate
decisions.

## Primary sources

* [TI UCC28180 Rev. D datasheet](https://www.ti.com/lit/ds/symlink/ucc28180.pdf),
  §8.3.14 and pp. 5–6, 18, 27.
* [Nexperia BAT54H product page](https://www.nexperia.com/product/BAT54H) and
  [BAT54H datasheet PDF](https://assets.nexperia.com/documents/data-sheet/BAT54H.pdf),
  pinning table and 10-mA VF specification.
* [Vishay BAV23C datasheet](https://www.vishay.com/docs/86374/bav23c.pdf),
  pp. 1–3; the graph is typical and not a guarantee.
* [TI E2E ISENSE diode discussion](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/877587/ucc28180-isense-pin-diode-requirement),
  application guidance that does not replace the datasheet window.
