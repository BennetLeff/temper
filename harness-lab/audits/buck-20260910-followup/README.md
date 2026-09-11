# Buck blocker follow-up — 2026-09-10

Three Luna agents followed up the proposed requirements, component/model
evidence, and L2 layout resolutions. The host reviewed their findings, corrected
the measurement definitions and calculation limits, and retained this package.
Base commit: `a75ca538d87d6578917d0cb3a50da7f14ebdc210`.

The [closure wave](closure-wave/README.md) adopts the design targets and adds
requirements-bound load-profile checks. Component evidence remains unresolved;
the BOM and evidence registry remain unchanged. Scored experiments and physical
validation have not run.

**Component retrieval:** [Live Murata retrieval](murata-live/README.md) recovered the exact
C11/C12 curves after authorized terms acceptance. C9 instead has an unverified
MPN with no exact live catalog match. This supersedes the earlier statement
that both Murata curve sets were simply unavailable.

[C9 DigiKey shortlist](c9-digikey-shortlist.md) records live stock for TDK,
KEMET and Würth 10 µF / 50 V / X7R / 1210 candidates, with the exact bias and
assembly checks still needed before a BOM replacement.

| Workstream | Concrete result | Remaining dependency |
|---|---|---|
| Requirements | [Targets and procedures](requirements-proposal.md) adopted; explicit profiles and named thermal limits supported. | Capacitor effective values and L2 hot-current evidence remain unresolved. Full waveform procedures require further implementation and model qualification. |
| Components | [Exact-part evidence and bounded calculations](components.md), including KEMET and Bourns evidence, plus [live C11/C12 curves](murata-live/README.md). | Resolve C9's exact identity; establish qualified effective minima for all five capacitor placements and L2 hot-current evidence. |
| Layout | [Corrected L2 footprint and scratch candidate](layout.md), based on the lead-frame land-pattern drawing and verified through native KiCad. | Assembly review and full frozen-contract/reference/variant qualification with negative controls. |
| Model | [Vendor-model completion path](model-path.md), exact-device EVM guide, and a live WEBENCH form prepared for the proposed envelope. | User choice on TI terms, then exact-device/mode and usable simulation/export verification; independent waveform qualification remains necessary. |

The current nine-component BOM remains U3 LMR51430XDDCR; L2 SRP1265A-5R6M;
C9 GRM32ER71E106KA12L; C10/C13 C0603C104K5RACTU; C11/C12
GRM32ER71E226KE15L; R16 RC0603FR-07100KL; R17 RC0603FR-0722K1L.

New source PDFs and their hashes are listed in [sources/README.md](sources/README.md).
The production board, frozen fixtures and approved-evidence registries were not
changed. Active requirements were revised in the closure wave. Earlier unrelated
working-tree edits were preserved.
No physical tests, scored model trials, vendor messages or remote publication
were performed.

Host verification confirmed that the production board, approved-evidence
registry and three pre-existing dirty documents retain their pre-follow-up
SHA-256 hashes. The candidate board hash matches the native collector's input
identity. The two newly retained PDF hashes match their source inventory.
