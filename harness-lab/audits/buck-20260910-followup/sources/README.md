# Source inventory

These are reference documents, not approved component/model receipts.

| Retained document | Primary source | SHA-256 |
|---|---|---|
| `C0603C104K5RACTU.pdf` | https://search.kemet.com/download/specsheet/C0603C104K5RACTU | `a74d666c69e2798691fea970c43141fb2d25fabff3710494d68dcd35fcef4040` |
| `ti-lmr51430evm-guide.pdf` | https://www.ti.com/lit/ug/sluuch0/sluuch0.pdf | `c62a648c00193324109ce20b590be9a7720c2995bd3b5d57d4b3101b4c6f78b1` |
| Existing `../../buck-20260909/sources/bourns-srp1265a.pdf` | https://www.bourns.com/docs/product-datasheets/srp1265a.pdf | `30b470999b737a6350ce5b09a917a5f12090c2e0895a78ddc15285e3d44ec649` |

The KEMET and EVM PDFs were downloaded during this follow-up. Bourns' retained
document was reused and its first-page drawing inspected visually. The host
also read current TI product and WEBENCH pages; their retrieval limitations are
recorded in `../model-path.md`.

Both exact Murata PDF endpoint attempts returned HTML rather than approval
sheets. Those responses remain in the temporary agent workspace as diagnostics
and are not registered as component evidence. No exact Murata DC-bias curve or
hot L2 saturation curve was established by this follow-up.
