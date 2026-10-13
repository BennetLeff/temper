# DFMA review verification receipt

Date: 13 October 2026. Scope: the 72 DFMA criteria, rather than a new complete electrical operating/qualification review.

## Input identities

- Selected stage21b PCB SHA-256: `c015804959add81e948055279cb78946e3a762ac9077c0b21bfbde3c89d0cb56`.
- Selected source copper: `c608c724953cbdab4fb304ae1b30c08c48196aab91fe8eac4b87b052d6dd5835`; schematic: `e25b32a9585e2e42a2cc1b3f5378e03aa9aaea97d1d8e118444357172a3be0ad`; netlist: `5be3b9f5042793951e01cd47778f2586a65b5b3987ae2116d6938c8d58ead208`.
- The source copper copy and schematic matched the live producer when the completed routing build froze; its Rust geometry receipt named exactly this PCB hash. A private review-only manifest pinned 139 source/supporting inputs. The existing standalone Rust guard passed against that manifest and selected board. All 139 hashes were checked again after native review operations and remained unchanged. These pins do not modify the repository hardware baseline.
- Root `make hardware-baseline-check` passed its published stage15b identity. The other published stage19b snapshot and the first producer stage21 manifest did not select the requested stage21b. No older board was substituted. The user confirmed the C30/C31 update was in progress; review selection followed its completed routed output, then the final producer manifest accepted the same stage21b hash.
- R43 assembly SHA-256: `0a6fcd0fe8dfa03477ffc170df59d2ab32faee8e67ea38e94059fa7066be86ce`. All entries of R43's supplied manifest matched the frozen copy; 941 files were inventoried. Its stage12 input snapshot and stage13 pose/BOM remain explicit older dependencies.
- Final producer Gerber ZIP SHA-256: `bb7a54787dc08d06562da1c790109ab763707eede3a3a95bb03e862ccbfd3a39`. Initial transitional and final package captures were retained separately. The producer corrected C30/C31 corrected-CPL/audit rows and advanced its manifest during this review; those earlier findings are resolved history, not active failures or reviewer fixes.

## Fresh native checks

KiCad 10.0.4 at `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` checked the frozen board with `--all-track-errors --schematic-parity --refill-zones --format json`; no `--save-board` was used. Private versioned `KICAD_CONFIG_HOME/10.0/fp-lib-table` entries reference the frozen vendored libraries, including the omitted project registration for QFN.

| Completed run | Severity requested | Electrical errors | Unconnected | Parity | Warning scope |
|---|---|---:|---:|---:|---|
| [1](evidence/pcb/drc.json) | Errors and warnings | 0 | 0 | 0 | silk overlap 199 cap; silk over copper 199 cap; silk edge 22 |
| [2](evidence/pcb/drc-2.json) | Errors only | 0 | 0 | 0 | Not requested |
| [3](evidence/pcb/drc-3.json) | Errors only | 0 | 0 | 0 | Not requested |

The electrical violation sets intersect to the empty set. Warning categories were not re-censused or treated as stable counts. The sandboxed first attempt aborted with exit 134 and produced no valid JSON; it is not a completed pass. The successful runs used the same frozen input and library registration. The original producer report had library-resolution warnings; the private configuration resolved those without changing board/library bytes.

Five inherited project ignores remain explicit: missing courtyard, via-centering, tuning-profile geometry, symbol footprint filter mismatch and footprint type mismatch. No pass is claimed for these suppressed categories.

Fresh reviewer-only Gerber, drill and position outputs were generated in the private review workspace. Native placements matched final producer positions, and all 353 populated designators/MPNs matched the 92-line BOM. The final raw/corrected CPL variants matched every position, with the 10 intended rotation overrides; the alternative variant negates Y intentionally. Actual assembler preview of the final selected convention and flagged parts remains open. Gerber export subtracts soldermask; its ink-on-land screen cannot prove label readability.

Native `pcbnew` queries checked component/pad geometry, drill/paste classes, C30/C31 positions and the C31/C24 nominal gaps. The node returned normal objects despite a headless wx assertion. Native F.Fab/courtyard/paste visuals and the four-layer copper plot were inspected. Source-bound producer geometry/fabrication checks were read with their identities; they are separate from these fresh reviewer operations.

## Coverage and limits

Five Sol reviewers produced 72 unique criterion decisions: 32 score 1, 27 score 2, 13 U, no 0/3/NA. JSON/ID coverage, evidence references, authored-report local links and immutable input hashes were checked. Verbatim producer documents retain their original links; their original source directories are recorded in the identity ledgers. Authored-report whitespace is checked on the explicit staged file set. Source CSVs retain their original CRLF bytes; the evidence check permits CR-at-EOL rather than normalizing hash-bound data. Source finding IDs overlap by mechanism; they are not summed as independent defects.

R43 whole/interior/rear/underside views and CAD source were inspected. No new R43 STEP interference kernel, physical tool reach, snap deformation, harness trial, thermal correlation, wet/cleaning test, service-cycle test or production yield/capability test was run. Matched inherited sequence/cover results and mismatched door/final reports are distinguished individually.

The generic schematic/PCB/cross-domain/EMC/SPICE/thermal/lifecycle analyzer suite and an every-part electrical usage/datasheet review were not rerun. This task applies the specified DFMA rubric, uses native geometry/manufacturing-file checks, and leaves circuit operating margin, field EMC, insulation qualification, material acceptance and lifecycle/availability verification as explicit separate evidence needs. It is not a new comprehensive electrical review. Existing modeled switching/thermal/EMI/benchmark results are not recast as fresh physical measurements. Exact-part drawings used for consequential assembly questions are cited in the PCB report.

No board, schematic, source BOM, CAD, manufacturing packet, baseline pin, supplier account or order was changed by these reviewers. Saved design files are exact review evidence copies; reference exports are private review outputs. No corrected benchmark was created and no improvement was implemented. Source contexts and artifact hashes are retained for reproducing the review, not for manufacturing authorization.

## Retained source archives

[Selected stage21b source archive](evidence/pcb/selected-stage21b-source.zip) retains the 139 pinned inputs and review-only manifest byte-for-byte, including vendored libraries/models. Its `producer-context` records preserve the context at initial board selection, including the older manifest. [Final manufacturer-package archive](evidence/manufacturing-stage21b-final.zip) separately retains the later accepted stage21b manifest and corrected placements byte-for-byte. They are review evidence, not a combined supplier upload package. Archive member bytes and ZIP integrity were checked against the frozen source directories.
