# TEA2209T/1 construction decision

Date: 2026-09-19  
Status: **CONSTRUCTION GATE — current footprint not released**

This is a package/construction disposition for the 120 V-only active-bridge
candidate. It does not claim appliance compliance, and it does not promote the
existing board past its three TEA spacing findings. The assessed board remains
the byte-identified candidate in the review packet (`e274d8ad…`); no CAD,
schematic, BOM, or spacing rule was changed by this decision.

## Decision

The present SO16 land pattern is not supportable for production release from
the evidence retained. Its 0.60 mm pad width on a 1.27 mm pitch gives 0.67 mm
between adjacent copper pads. For each reviewed pair (3–5, 10–12, and 14–16),
the two adjacent gaps total 1.34 mm. The 1.94 mm endpoint span does not settle
the assembled path because the intervening unused lead is a conductor. The NXP
package drawing lists a 0.36–0.49 mm `bp` range; an idealized nominal-pitch
calculation using the widest listed lead gives 0.78 mm per lead-to-lead gap and
1.56 mm across the two gaps. That is an estimate, not a minimum or a finding
that this is the limiting path: the retained drawing does
not provide the lead-width, lead-position, solder, or assembly tolerances
needed to establish a guaranteed assembled clearance.

The package datasheet does not provide an appliance insulation approval for
these external pin pairs, a recommended high-voltage land treatment, or a
guarantee that the SO16 demonstration layout in UM11493 establishes clearance
or creepage. Therefore the generic 2 mm screen cannot be waived, and the
existing board cannot be called released merely because the ideal 120 V
waveform is half-wave (93.34 V RMS at the 132 V RMS design maximum).

## A construction hypothesis, not an authorized ECO

The lowest-cost hypothesis to ask the package and assembly owners about is a
**no-land construction for pins 4, 11, and 15**, which the candidate schematic
marks NC:

1. Ask NXP for a recommended land pattern and explicit confirmation that the
   three NC leads may be left unsoldered in this package. No retained NXP
   document currently grants that permission.
2. Ask the assembly owner to state the solder-joint, lead-position, and
   contamination assumptions for that construction. Do not infer them from the
   nominal package drawing.
3. Only after those answers, create a marked prototype variant with copper,
   paste, and mask removed for the NC pins and a keepout around them. Keep the
   three leads physically present; do not clip or bend them.
4. Re-measure the assembled path and obtain the product-safety disposition.
   This remains a proposal, not a waiver or an authorized footprint change.

This route is worth asking about because it removes the largest avoidable part
of the present geometry—the three floating PCB lands—without pretending that
the package lead spacing disappears. It is not yet a lab/prototype build
instruction: the no-land soldering and package-path questions are external
inputs.

## Fallback if the route is rejected

Select a controller/package whose manufacturer land pattern and package
geometry provide the required pair-to-pair spacing under the declared product
standard, or use a physically separated controller construction whose package
paths are independently accepted. A daughterboard carrying the same unmodified
SO16 is not a fix by itself: the package lead geometry follows the part onto
the daughterboard.

Do not narrow pads, clip leads, count solder mask as insulation, credit coating
or FR-4 CTI without a retained material/standard basis, or silently add the
230 V product scope. The current 120 V ±10% / ≤2000 m design scope remains the
only scope considered here.

## Exact release gate

Release requires one of these two records:

* a clause-specific product-safety disposition that identifies the required
  working/impulse voltage, pollution degree/material group, floating-conductor
  treatment, tolerances, and the limiting assembled path, and accepts the
  no-land candidate; or
* a selected alternate package/footprint with a manufacturer-backed spacing
  basis that meets those same inputs.

The prepared [TEA insulation request](../review/TEA-INSULATION-REQUEST.md)
contains the questions for NXP and the product-safety reviewer. It is a draft
and has not been sent. Until a response or an independently qualified
alternative exists, the correct disposition is **prototype candidate only;
production construction unresolved**.

The external questions are deliberately finite:

1. **NXP package:** For the exact TEA2209T/1 SOT109-1, are pins 4, 11, and 15
   electrically floating/unbonded, and does NXP permit them to be left
   unsoldered? Provide the recommended land pattern, lead-position tolerances,
   and any package path or material data relevant to these pin pairs.
2. **Product route:** Which appliance standard and edition governs the intended
   portable or stationary product, and what insulation class, pollution degree,
   material group, working voltage, impulse voltage, and altitude inputs apply?
3. **Assembled path:** Does the selected standard apply the floating-conductor
   treatment illustrated by IEC 60664 Example 11 here, including its individual
   gap condition? Identify the limiting copper, solder, lead, and molded-body
   paths with tolerances.
4. **Disposition:** For each pair 3–5, 10–12, and 14–16, provide the required
   versus available clearance/creepage (or the exact accepted functional-fault
   test route), and state whether the existing or no-land construction can be
   released.

The governing product standard is also a release input, not something that can
be inferred from the 120 V target. A portable countertop hotplate and a
stationary cooking appliance may enter different product-standard routes (for
example, the IEC 60335-2-9 versus IEC 60335-2-6 families, with corresponding
North-American routes such as UL 1026 versus UL 858). These are candidate
routes to confirm with the safety reviewer, not compliance claims. The present
PD2 compartment is a design requirement, not evidence that the built assembly
has achieved PD2. No IEC or UL certification conclusion is made here.

This leaves a concrete next investigation while the release gate is open: get
the package/assembly answers for the no-land hypothesis, then—only if they
support it—make a marked prototype variant and inspect its assembled lead and
solder geometry. Run the selected product-standard review against that measured
construction. If the standard or the package owner requires more separation
than the measured path provides, stop the TEA route and switch
package/controller rather than tuning copper to pass a numeric screen.

## Evidence and limits

The package dimensions are from NXP TEA2209T Rev. 1.1 (14 April 2021),
SOT109-1: 1.27 mm pitch and 0.36–0.49 mm `bp` entry in the package outline.
It is not a tolerance-controlled clearance bound. NXP's UM11493 Figure
26 is a layout precedent, not an insulation certificate. The Bourns floating-
conductor paper illustrates the IEC 60664 Example 11 treatment, but it does
not establish that the example or its X-condition governs this appliance.
The half-wave voltage calculation checks only the ideal circuit algebra; gate
offsets, device drops, commutation, startup states, and surge coupling remain
inputs to the safety disposition.
