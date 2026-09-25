# ISENSE clamp datasheet audit

This is a read-only audit of the bounded clamp experiment in
`operating-matrix-07/clamp`. It does not change the canonical circuit or
replace the assumed SPICE model.

## Primary documents

The retained documents are:

* Texas Instruments, **UCC28180**, SLUSBQ5D, November 2013 / revised July
  2016, SHA-256 `e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be`.
* Vishay, **BAV23C**, document 86374, Rev. 1.1, 21-Feb-2024, SHA-256
  `b05e055b9bddac73647119b108d61535c80f89b2ad12087d4cee28bb18106d96`.

The page numbers below are the printed datasheet pages, not PDF zero-based
indices.

## What TI actually requires

UCC28180 page 5 gives the ISENSE absolute maximum voltage range as -24 V to
7 V and the ISENSE input-current absolute maximum as -1 mA to +1 mA. These
are damage limits, not an allowable sensing-error budget. Page 6 gives the
PCL threshold as -0.345 V minimum, -0.400 V typical and -0.438 V maximum;
the same page states the electrical-characteristic temperature range as
-40 to +125 °C. Page 18, section 8.3.14, says ISENSE should be limited to
0 V through -1.1 V and that the external diode's forward voltage must be
greater than the maximum PCL threshold (0.438 V in magnitude) and less than
1.1 V over temperature and component variation. Page 27, section 9.2.2.9,
specifies the 220-ohm series resistor and shows the design example's 1000-pF
ISENSE filter capacitor.

Thus the component-level qualification condition is a window on diode
forward voltage at the actual current and temperature, not merely “the diode
can carry 5 mA” and not the ISENSE absolute-maximum current.

## What the BAV23C datasheet establishes

Vishay page 1 specifies the BAV23C absolute maximums at 25 °C: 250 V
repetitive peak reverse voltage, 200 mA average forward rectified current,
400 mA forward continuous current, 625 mA repetitive peak forward current,
and 300 mW power on the recommended FR-4 footprint. Page 2 specifies a
maximum forward voltage of 1.0 V at 100 mA and 1.25 V at 200 mA, both at
25 °C, and gives an operating-temperature range of -55 to +150 °C. Those
facts support the high-current and reverse-voltage stress direction, but do
not establish TI's forward-voltage window.

The relevant low-current evidence is page 3, Figure 1, “Typical Forward
Current vs. Forward Voltage.” Reading the logarithmic plot only as a coarse
order-of-magnitude check (the graph is not a guaranteed specification) gives
the following ranges near VF ≈ 0.438 V:

| junction temperature (typical curve) | forward current near 0.438 V |
| ---: | ---: |
| 25 °C | tens of µA (order 10⁻⁵–10⁻⁴ A) |
| 100 °C | a few hundred µA to roughly 1 mA |
| 150 °C | roughly 1–several mA |

These are **typical graph readings**, not guaranteed limits. They are enough
to show that real forward conduction at the PCL threshold is permitted by
the published typical behavior. The current is not guaranteed to be zero,
and there is no guaranteed minimum forward voltage at 1 µA, 10 µA, or any
other low clamp current in the electrical-characteristics table. Figure 2
on the same page gives admissible power dissipation versus ambient
temperature, while Figure 4 gives typical reverse leakage; neither supplies
a worst-case forward-voltage tolerance curve.

The current assumed by the existing `bav23c-assumed-v2.inc` at the nominal
PCL point is 70.2 nA at 25 °C. That is at least hundreds-fold below the
coarse 25 °C typical-current range suggested by Vishay's Figure 1 at the
same voltage. The assumed model therefore cannot be treated as a
vendor-anchored prediction of PCL loading. This is not a proof that a part
will fail; it is proof that the current model does not establish
qualification.

## Audit of the existing 1 µA / 2 mV screen

The Rust checker itself labels the 1 µA diode-current and 2 mV ISENSE-shift
limits as a “deliberately chosen loading screen,” and neither limit appears
in the TI or Vishay documents. They are engineering screening criteria, not
datasheet requirements.

They can be translated through the actual 220-ohm resistor:

* 1 µA through the clamp corresponds to 0.22 mV across 220 ohms.
* 2 mV of controller-side shift corresponds to 2 mV / 220 ohms = 9.1 µA
  of resistor current.
* The UCC28180 ±1 mA ISENSE current number is an absolute maximum, so it
  cannot be used as a functional-error allowance. At 1 mA the same resistor
  would imply 220 mV, which is plainly incompatible with a 2 mV sensing
  screen.

The 2 mV criterion is 0.46% of the 0.438 V PCL threshold and is a small-error
screening choice. The 1 µA criterion is stricter than the resistor-equivalent
2 mV criterion. Neither criterion is derived from a published UCC28180
accuracy specification, and neither can be used to turn the assumed SPICE
current into a qualified result.

Using the typical Figure 1 reading above, even a few tens of µA would produce
several mV across the 220-ohm resistor before the diode/resistor operating
point is solved self-consistently. That can already exceed the chosen 2 mV
screen; at higher temperature the plotted typical current is much larger.
This is a reason to revisit BAV23C for this specific low-disturbance
placement, not a claim that the typical graph alone rejects every lot.

## What remains missing before the clamp can be accepted

The datasheets do not provide the required guaranteed, low-current
`VF(min)` and `VF(max)` over the product tolerance and the full -40 to
+125 °C controller range. A valid qualification needs one of:

1. a vendor production model or guaranteed min/max `VF` curves covering the
   actual clamp-current range, temperature and lot tolerance; or
2. a bench characterization plan that measures assembled parts at the
   controller-side node, including the PCL crossing, the -1.1 V clamp event,
   temperature, resistor tolerance, pulse duration and board thermal
   conditions.

The next simulation should use a vendor-anchored bounds model, or explicitly
carry a swept unknown forward characteristic. It should not report the
current `bav23c-assumed-v2` nominal PCL result as proof of non-interference.

## TI reference implementation check

TI's official **UCC28180EVM-573 User's Guide**, SLUUAT3B, is the useful
standard implementation to compare against. Its Figure 1 schematic (printed
page 6) shows `R2 = 221 ohm` in series with ISENSE and `C8 = 1000 pF` at the
controller-side node. It does **not** populate an ISENSE clamp diode. TI's
E2E answer to the EVM question explicitly says that the Rev-D datasheet added
the diode while the EVM did not have one; the EVM therefore supports the
resistor/filter placement, not a qualified diode part.

The same TI E2E answer says that a diode with reverse rating above 1.1 V and
at least three times the illustrative 5 mA resistor current is a reasonable
stress starting point, and says many customers use BAV23C. It also says a
candidate without a VF-versus-temperature curve cannot be judged suitable.
That response is useful application guidance, not a datasheet guarantee. It
does not turn the BAV23C typical Figure 1 curves into production limits.

Sources: [UCC28180EVM-573 User's Guide, SLUUAT3B](https://www.ti.com/lit/ug/sluuat3b/sluuat3b.pdf)
and [TI E2E ISENSE-pin diode discussion](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/877587/ucc28180-isense-pin-diode-requirement).
