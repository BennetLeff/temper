# Integration-06 ISENSE clamp diagnosis (read-only)

## Finding

The retained source has the clamp polarity reversed for the actual
UCC28180 current-sense polarity.  In
`/private/tmp/temper-pkgs-1-4/elec/src/power_entry_passive_reva.ato`,
`PfcIsenseClamp` declares `A ~ pin 2` and `K ~ pin 1`; the module then wires
`isense_clamp.A ~ shunt.p2` and `isense_clamp.K ~ control_gnd` (source lines
122-128 and 430-431).  The bridge-return shunt node is negative relative to
`control_gnd` during sensed current, so this A-at-shunt/K-at-ground diode is
reverse-biased on the excursion that matters.  It only provides the opposite
(positive) clamp.

TI's Rev-D UCC28180 datasheet, §8.3.14 (local retained copy:
`zapote/power-entry/shunt-repair/sources/TI-UCC28180.pdf`, printed p. 18),
requires ISENSE to remain between 0 and −1.1 V.  The external diode's forward
voltage must be greater than the maximum PCL threshold (0.438 V magnitude) and
less than 1.1 V across temperature and component variation.  TI Figure 26
(printed p. 17) shows the diode from the filtered/controller-side ISENSE node
to GND, after the series ISENSE resistor; it is not drawn directly across the
shunt.  The same primary datasheet is published at
https://www.ti.com/lit/ds/symlink/ucc28180.pdf.

## Concrete correction candidate

Use one diode element of Vishay **BAV23C** (orderable example
`BAV23C-E3-08`, dual silicon switching diode, common cathode) as the named
ISENSE clamp.  Wire the selected die as:

```text
                       220 ohm R_ISENSE
bridge-minus/shunt.p2 ────────────────┬── UCC28180 ISENSE (pin 3)
                                     │
                                  K ─┤  BAV23C (one die)
                                  A ─┘
                                     │
                                  control_gnd
```

In source terms this means `isense_clamp.A ~ control_gnd` and
`isense_clamp.K ~ pfc.ISENSE` (or an explicit post-`r_isense` net), with the
other BAV23C anode handled explicitly according to the selected footprint
(do not leave an unreviewed floating lead in a production symbol).  The
220-ohm resistor remains between `shunt.p2` and `pfc.ISENSE`; the clamp must
be on the **controller side of that resistor**, at the same node as
`c_isense.p1`, not across `shunt.p2`.

This is the strongest available part recommendation rather than a claim that
the source is now qualified.  TI's own UCC28180 E2E answer says the diode
reverse-voltage rating should exceed 1.1 V, the 220-ohm resistor limits a
1.1-V clamp event to about 5 mA, and the diode should be rated for at least
three times that current; the same answer says many customers use BAV23C and
links its Vishay datasheet:
https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/877587/ucc28180-isense-pin-diode-requirement

Vishay's current BAV23C datasheet (`https://www.vishay.com/docs/86374/bav23c.pdf`)
specifies 250 V minimum breakdown, 100 mA maximum forward voltage of 1.0 V
(25 °C) and 200 mA/1.25 V, plus −55…150 °C operation.  The 250-V reverse
rating and ≥100-mA forward-current capability comfortably exceed TI's
minimum 1.1-V reverse and 15-mA current recommendations.  However, the
datasheet table is at 25 °C; its headline electrical table alone does **not**
prove the required 0.438…1.1-V forward-voltage window at every temperature,
current, and tolerance.  TI's E2E response explicitly says the attached
BAV23C data was the choice used by many customers; the final part release
still needs the vendor VF-vs-temperature curve/guarantee or bench
qualification at the actual clamp current.

## What this does and does not establish

* It establishes the polarity and placement correction: ground anode,
  controller-side cathode, after the 220-ohm resistor.
* It provides a concrete, TI-supported silicon candidate (BAV23C), rather
  than blindly reversing the present BAT54H Schottky.  BAT54H's low VF is
  exactly why it is unsafe to assume it meets TI's “VF > 0.438 V” condition.
* It does not establish inrush/short transient peak current, the diode's
  thermal pulse margin, exact VF over the product temperature/current range,
  or the complete UCC28180 pin transient.  The existing nominal coupled trace
  reaching about −0.3555 V is not evidence for the −1.1-V inrush bound.
* The EVM/reference schematic's 220-ohm resistor and controller-side filter
  topology support this placement, but the EVM discussion notes the added
  ISENSE diode was not present on the older EVM; EVM omission is not a reason
  to omit the clamp from this design.

## Host qualification of the current argument

TI's 5 mA calculation is an illustrative resistor drop, not an unconditional
inrush-current bound. At steady conduction the actual resistor current is
approximately `(abs(V_shunt) - VF) / 220 ohm`, with capacitor current added during
transitions. A bound on `V_shunt(t)` is still needed before accepting diode pulse
current, resistor stress, or pin voltage. The 400 mA headline continuous diode
rating has an infinite-heatsink condition; use the board thermal/pulse limits.
The vendor's forward-voltage plots are typical curves, not worst-case guarantees.

The adjacent `isense-clamp-candidate.patch` is a reviewable source proposal. It
selects one BAV23C die, explicitly leaves its unused anode unconnected, and moves
the active cathode to the filtered controller pin. It is not applied to the
frozen source, not compiler-validated, and not part of the accepted switching
trace. Do not count that trace as evidence for this proposed change.
