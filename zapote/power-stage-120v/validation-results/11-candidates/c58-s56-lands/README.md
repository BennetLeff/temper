# c58: pad check of the 26 s56 BOM lines without JLC geometry (2026-11-25)

Prompted by the U30 defect on the controller (land of the wrong package through every gate) and the external review's list.
`compare_lands.py RAW_DIR` distils the public EasyEDA/LCEDA records, and reruns from `jlc-pads.json` without it.

**Not checked:** the lines the library has no record for, or whose request was refused, are printed as NOT CHECKED and are not passed.
They include the review's U41/U42 (RECOM), T1 (CT), L1, J2/J5, F2, J6 and R130, all with custom lands. They need the maker's drawing.
**F1 and BR1 have no JLC code in the BOM (owner-supplied / hand-fitted), so nothing here checks them.** J4 (C491447) had JLC geometry in
the first screen. Result: 15 of 26 PASS, 11 not checked: three standard chip resistors (R51, R71, R132) and the custom or
through-hole lands C1/C2, L1, T1, J2/J5, F2, R130, J6, U41/U42, which with F1 and BR1 need a maker-drawing check before the s56 order.

**Measure:** pad centres only (RMS at the best 90 degree rotation, limit 0.30 mm), as `check_land_patterns.py`. Not pad size, height or pin 1.

**Number differences resolved by hand** (REMAP in the script): C5 (pads 3/4 both `hv_ret`), PS2 (AC and DC pins agree with JLC's symbol),
U1 (2EDR8259X on the DWK land), J3 (two-position VH).
