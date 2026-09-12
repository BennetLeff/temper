# U1 DWK CAD audit

The official TI UCC21550 product page identifies the selected DWK package as
14 pins and 10.3 mm square, but the accessible product and datasheet pages do
not provide a downloadable exact DWK STEP/WRL model. The native board therefore
retains KiCad's `SOIC-16W_7.5x10.3mm_P1.27mm.step` only as a visual
approximation. The copper footprint remains the verified DWK land pattern and
has physical pads 1-11 and 14-16; pins 12 and 13 are absent.

Evidence: [TI UCC21550ADWKR product page](https://www.ti.com/product/UCC21550/part-details/UCC21550ADWKR),
[TI UCC21550 datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf).

No CAD mutation was made during this audit. A fabrication or mechanical
qualification claim must continue to exclude the approximate 3D model.
