# c58: pad check of the 26 s56 BOM lines without JLC geometry (2026-11-25)

Prompted by the U30 defect on the controller (land of the wrong package through every gate) and the external review's list.
`compare_lands.py RAW_DIR` distils the public EasyEDA/LCEDA records, and reruns from `jlc-pads.json` without it.

**`drawing_lands.py` (2026-11-25):** the remaining lines against maker drawings on disk, and the hand-fitted parts the BOM
gives no JLC code (F1, RV1, BR1, Q2/Q3/Q5/Q6, the bank caps, D3/D17), which no pad check had covered.
Not checked: J2/J5 and RV1 (no sheet on disk), and three standard chip sizes. Negative control: moving one T1 pad 0.3 mm in a
copy of the script makes T1 FAIL.

**One FAIL: the FET holes.** Infineon's outline allows a lead up to 1.40 x 0.89 mm (1.66 mm diagonal); the TO-247 holes are 1.5 mm.
The drawing does not bound the typical lead, so leads may or may not fit; whether they do is known only from a fitted part or a larger hole.
1.8 mm in the 2.5 mm wide pad would leave 0.35 mm of copper each side. Nothing was changed: s56 is the board of record and the change needs
its own stage (copper, B3 and scorecard). The FETs are DNP at JLC and fitted later, so it is a bench item unless a stage is opened.

**Measure:** pad centres only (RMS at the best 90 degree rotation, limit 0.30 mm), as `check_land_patterns.py`. Not pad size, height or pin 1.

**Number differences resolved by hand** (REMAP in the script): C5 (pads 3/4 both `hv_ret`), PS2 (AC and DC pins agree with JLC's symbol),
U1 (2EDR8259X on the DWK land), J3 (two-position VH).
