# Shared placement-library evidence

Read-only public EasyEDA API responses, retrieved 2026-10-20. Geometry is source evidence only; it is not copied into CAD.
- C0603.json: owner `lcsc`; https://easyeda.com/api/components/f8151fdc728a41ebbc304e11d39e5437
- C0805.json: owner `lcsc`; https://easyeda.com/api/components/2ee8eb13a0124a108e622ce40c0c25a8
- C1206.json: owner `lcsc`; https://easyeda.com/api/components/7bdec8012728462a85919a4d0d033579
- C165948.json: owner `LCSC`; https://easyeda.com/api/components/d556fcebb18d4647a249a7d49ea0c41d
- C51118.json: owner `lcsc`; https://easyeda.com/api/components/7ec9305c6bfd40199d1dde43ba8e9df2
- C7519.json: owner `lcsc`; https://easyeda.com/api/components/9a066f903e65476fa74739d5e9b0ceb9
- R0603.json: owner `lcsc`; https://easyeda.com/api/components/398691f1f785460098bbe5ee6590333c

Revision-A-only IC and oscillator records are retained under `archive/rev-a/superseded/sources/placement-library/`, outside the revision B package. The current part-specific authority is `sources/placement-rev-b.json`.

Rev E keyed parts, retrieved 2026-10-21 by `cad/tools/placement_offsets.py` as `<LCSC>-product.json` from the lceda.cn mirror of the product API, `https://lceda.cn/api/products/<LCSC>/components?version=6.4.19.5`. easyeda.com answered 403 that day; the mirror's PAD records for C2684450 and C44853692 match the easyeda.com records fetched on 2026-10-20. C15127 (Q1) and C51118 (U3) were refetched to confirm that the tool reproduces their audited offsets (180° and 270°). Each file's SHA-256 is in `sources/placement-rev-c.json`.

Rev E USB-C power entry: C55266 (U16 TPS2553DBVR) fetched the same way on 2026-10-21; offset 180°, RMS 0.21 mm over 6 pads against native SOT-23-6 (next candidate 2.08 mm). C15127 (Q1) and the DC-005 jack left the board with this change; their records stay as audit history.

Rev F 3D models (2026-10-29): C41416668 (SAMZO BNC-KYWE-295-W4-N) fetched the same way for its outline3D record. `cad/tools/models_3d.py` reads the outline3D uuid, origin, z and rotation from the C2684450, C41416668, C165948 and C160472 records and fetches the STEP models from `https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/<uuid>` (not committed; hashes in `cad/3dmodels/models-3d.json`).
