# Wider power-entry gates after the AUX interface work

Date: 2026-09-22. This is a review of existing evidence and the minimum next
receipts for the PFC current-sense and fault-interruption paths. It changes no
circuit, part selection, simulation result or qualification status.

## Current-sense clamp

The [Revision 09 clamp evidence](../reference-revision-09/clamp-evidence.md)
establishes the negative-clamp topology: diode anode to control ground,
cathode to the controller-side ISENSE node **after** the 220 Ω resistor, with
the 1 nF filter at that node. The retained canonical BAT54H wiring is on the
wrong side/polarity for that job. BAV23C-E3-08 is an isolated candidate with
checked pin mapping, not an accepted part. The [TI UCC28180 Rev D ISENSE
guidance](https://www.ti.com/lit/ds/symlink/ucc28180.pdf) requires the
negative clamp's forward drop to preserve the −0.438 V maximum PCL threshold
and keep ISENSE within −1.1 V across temperature and part variation.

The [Vishay BAV23C data sheet](https://www.vishay.com/docs/86374/bav23c.pdf)
does not give the needed guaranteed low-current forward-voltage interval over
temperature and production variation. The chosen model also fails earlier
hot PCL-loading screens, which is a model-screen failure rather than a
measured part failure. Promotion needs either an applicable manufacturer
guarantee or assembly characterization with a bounded shunt waveform,
clamp current, ISENSE voltage and controller response at relevant thermal and
lot corners. The existing [TI/Vishay question draft](../reference-revision-09/manufacturer-questions.md)
requests the missing data; it has not been sent.

## F1, F2 and energy paths

The [Revision 09 fuse-coordination record](../reference-revision-09/fuse-coordination.md)
separates three paths that must remain distinct:

| Path | Present evidence | Closure input |
| --- | --- | --- |
| AC source → F1 → bridge/inductor → failed U9 | F1 and holder identities selected; authored source has 0.25 Ω, not a physical prospective-current bound. Schurter pre-arcing data is not total clearing. | Bound line prospective impedance/current at the installed location, then obtain applicable F1/holder breaking and total-clearing behavior and compare device/copper withstand. |
| Charged bank → F2 → failed U10/U9 | Candidate Mersen fuse/holder selected; retained model has ideal scripted F2 opening, no fuse/arc law. | Bound bank voltage, C, ESR/ESL, loop impedance and resulting waveform; obtain Mersen's applicability of its capacitor-discharge rating, MBC, peak/arc and total-clearing let-through before coordination analysis. |
| Local VD capacitor upstream of F2; residual VB after F2 opens | Neither F1 nor F2 is credited for local VD discharge; opening F2 leaves a charged bank. | Select and verify local-energy withstand or treatment plus a separately rated bank discharge and residual-voltage interlock. |

The exact manufacturer questions for Schurter and Mersen are already drafted
in [Revision 09](../reference-revision-09/manufacturer-questions.md). No
simulation can turn the published AC clearing I²t into a DC capacitor-discharge
guarantee, or turn an ideal open switch into a fuse-clearing waveform. Supplier
answers have not been received and no fuse clearing has been hardware tested.

## After those bounds arrive

1. Bind the applicable source, bank and local-reservoir fault envelopes to
   the **same** revised schematic, including line, U9/U10 and F2 states.
2. Rerun the [Revision 19 dynamic matrix](../interface-dynamics-19/transient-matrix.md)
   with the physical AUX source/load and hot FET SOA inputs. Keep modeled
   clamp peaks separate from installed driver-pin measurements.
3. Rerun the complete PFC startup, operating and fault campaign for the
   integrated candidate; the [2026-09-21 campaign closeout](../../../../../docs/evidence/2026-09-21-pfc-campaign-closeout-and-next-revision.md)
   records why prior normal/fault results do not transfer automatically.
4. Verify the exact PCB/holder/interconnect and assembly thermals, fuse
   clearing/withstand and residual-voltage behavior before calling the
   hardware qualified.

These are acceptance gates, not a request to send manufacturer messages or
run energized fault tests without the missing application data and fixture.
