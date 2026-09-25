# Model fixture provenance

No complete official STW65N65DM2AG SPICE model was available in this bounded
run. The diode, comparator, logic, latch, gate load and switch are authored
behavioral surrogates in `../f2_shutdown_template.cir`, with each timing and
component value labelled at the point of use. The prior official PDFs and the
UCC27624 vendor fixture are listed in the adjacent audit inputs and remain
outside this worker-owned simulation directory. A typical surrogate never
closes a hardware qualification bound.
