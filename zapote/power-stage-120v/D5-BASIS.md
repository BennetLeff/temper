# Conditional insulation placement basis

Owner decision on 2026-09-25: “Approve conditional placement basis.” This
responded to an explicit proposal for one controller-ground–PE functional
bond and an 8.0 mm minimum placement target, with Coilcraft evidence and the
voltage/standards review still open. It does not approve fabrication or routing.
D4 still requires review of the actual placement.

Use one removable 0 Ω functional connection near the separate J6 PE branch. It
must not carry protective-earthing responsibility: maintain the full HOT-to-
controller reinforced insulation requirement with PE open. Because the link
connects PE to controller return, HOT-to-PE copper, Y-capacitor paths and
heatsink insulators must also be checked for bypassing that barrier. Do not
carry the old basic-only HOT-to-PE rule forward without a justified system
insulation analysis; use the 8.0 mm provisional PCB floor there too. Keep other local
controller returns away from PE; external USB/probe earth paths need a system
review. The historical net name SELV_GND remains an identifier, not a final
SELV classification claim after earthing. Record the domain as earthed ELV,
with its final classification to be confirmed by the certification lab.

Cord PE bonds directly to the chassis/heatsink stud; its separate PCB branch
lands at J6 (Phoenix 1704004). J1 carries only mains L/N. J6, its PCB trace
and R38 are never in series with the primary PE bond. Maintain ≥8.0 mm
provisional clearance from every HOT conductor to the PE branch, its
hardware and the chassis connection. The C3/C4 local 10 mm-pitch footprint
uses 1.5 mm pads for an 8.5 mm nominal copper edge gap; check finished
board tolerances and the component surface path. This footprint change does
not settle the package or system insulation qualification.

The 8.0 mm floor applies to provisional PCB barrier geometry. It does not
prove that every working-voltage or switching-frequency case needs only
8.0 mm. Specify laminate with verified CTI ≥175 (group IIIa or better).
The reproduced IEC 60335-1:2020 Table 17 footnote restricts group IIIb to
working voltages ≤50 V; the repo's combined IIIa/IIIb numeric lookup must not
be used to waive that condition. Section 29.2.1 also requires checking the
IEC 60664-4 high-frequency distances above 30 kHz when larger. The lab must
confirm the governing edition, applicable appliance part and voltage convention.
[Table/footnote excerpt](https://www.equipmentnorm.com/NewSamples/IEC/178131394/IEC-60335-1-2020-2.pdf)
(printed p113, sample PDF p8); [IEC publication](https://webstore.iec.ch/en/publication/105687).

The TI UCC21550, AMC1311 and ISO7710 insulation tables state material group I
and pollution degree 2. Their package distances are evidence about those
packages, not blanket PD3 appliance approval. Board slots do not extend
package surface creepage. The Coilcraft CST3015 datasheet's ≥8 mm spacing
and 5 kVrms test do not supply its CTI/PD certificate. The IRM-20's input/output
pin span is not evidence of internal encapsulation or PD3 certification scope.

Sources: [UCC21550](https://www.ti.com/lit/ds/symlink/ucc21550.pdf),
[AMC1311](https://www.ti.com/lit/ds/symlink/amc1311.pdf),
[ISO7710](https://www.ti.com/lit/ds/symlink/iso7710.pdf),
[CST3015](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf),
[IRM-20](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF).

No physical insulation or certification testing has been performed.
