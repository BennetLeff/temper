# Insulation partition and provisional rule basis

This board set is a prototype candidate. A KiCad clearance pass is a geometric result, not product dielectric certification.

| Boundary | Current implementation | Rule meaning |
|---|---|---|
| Central AUX24/5/3.3 and AUX0V | No mains copper;0.15mm native baseline;0.3mm plane clearance | Functional low-voltage manufacturing screen only |
| Central CTRL3.3/CTRL_GND to AUX | ISO7710 interface; no intended shared return | Functional domain separation; no claim that central geometry provides mains reinforced insulation |
| Six voltage-card HV nodes to AUX | AMC3330 DWE0016A HV land option,8.1mm opposing-row copper gap; native8mm cross-domain rule | Provisional geometric screen, unchanged by power ECO |
| CT primary to secondary | Insulated primary conductor through aperture, no PCB primary terminal | Actual wire insulation, aperture fit, restraint and installed CT rating must establish boundary |
|24V contact feedback receiver | AUX-derived field side and logic with common system source | Does not create a new protective system isolation boundary |
| Enclosure/chassis to all boards | Packaging interface and nonconductive sensor mounts | Housing/environment and fault path remain separate qualification inputs |

The AMC3330's component isolation approvals and land drawing do not establish the complete cooker's creepage, clearance or dielectric-test voltage. The design still needs a selected product-standard/category determination, working RMS/peak and recurring tank waveform, transient category, pollution/condensation environment, PCB material group/CTI, altitude, protective bonding and accessible conductive-part classification. These inputs must produce traceable numerical rules for every boundary before fabrication release. They are currently unresolved; choosing8mm alone does not select a standard.

No solder-mask or coating credit is taken. No clearance reduction is justified by the housing until the actual assembled guard and lead restraint are checked. The local tank ladder is extended to avoid folded high-voltage adjacency, but individual resistor voltage/pulse limits remain a separate check. Native DRC uses actual board copper and the local rules; harnesses, contamination and off-board terminals are outside that calculation.

Primary geometry and isolation basis: [TI AMC3330](https://www.ti.com/lit/ds/symlink/amc3330.pdf), [TI ISO7710](https://www.ti.com/lit/ds/symlink/iso7710.pdf), [Talema AC current transformers](https://talema.com/wp-content/uploads/datasheets/AC-1005.pdf). Product requirements must be selected by the responsible electrical/product review; this note makes no certification claim.
