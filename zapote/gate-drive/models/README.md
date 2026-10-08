# Gate-drive low-fidelity model

`UCC21550_DWK14.wrl` is a mechanical visualization for the TI UCC21550 DWK
14-pin package. It uses a 7.5 x 10.3 mm body, 2.5 mm body height, and the
candidate footprint's 1.27 mm pin row positions. It contains exactly pins
1–11 and 14–16; the DWK package has no pins 12 or 13. The model is authored in
millimetre coordinates; when referenced by KiCad, use a `0.3937008` scale for
standard VRML inch conversion. The body and rectangular leads are deliberately
low fidelity and are not a substitute for TI's qualified STEP model or a
mechanical/clearance qualification.
