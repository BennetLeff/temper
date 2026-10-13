# Stage19b review verification receipt

Reviewed PCB SHA-256: `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662`. Tool: **KiCad 10.0.4** at `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`. The authoritative selected snapshot and frozen review copy both pass the 61-input identity guard. All **76 files** in the review-copy artifact inventory retained their original hashes after native operations. This inventory includes supplementary files; it is not a different 76-pin baseline guard.

## Native DRC

All four completed runs used the selected project's existing `.kicad_pro`, `.kicad_dru`, schematic and pinned vendored libraries. The runs included warnings and errors and used `--all-track-errors`, `--schematic-parity`, `--refill-zones` and JSON output. Zone refill occurred in memory; **no `--save-board`** was used. The legacy board's generated rules and ceiling were not involved.

| Completed run | Errors | Warnings | Unconnected | Parity issues | Configuration |
|---|---:|---:|---:|---:|---|
| [1](evidence/drc-1.json) | 0 | 1 | 0 | 0 | Original pinned project table; U26 library unregistered |
| [2](evidence/drc-2.json) | 0 | 1 | 0 | 0 | Added global table at unversioned private config root, not read by KiCad |
| [3](evidence/drc-3.json) | 0 | 1 | 0 | 0 | Separate private config; same unversioned-table issue |
| [4](evidence/drc-4.json) | **0** | **0** | **0** | **0** | Existing pinned QFN library registered in actual private `10.0/` config |

The warning in runs 1–3 was `lib_footprint_issues`: configuration did not include `Package_DFN_QFN` for U26 at `(115.4,81.05)` mm. The snapshot already contains the exact hash-pinned `candidate-libs/Package_DFN_QFN.pretty/Texas_RGW0020A_VQFN-20-1EP_5x5mm_P0.65mm_EP3.15x3.15mm.kicad_mod`, but its project `fp-lib-table` omits that library registration. The private global table for run 4 points to that existing directory. No footprint, candidate table, project or baseline pin changed. This exposes a portability gap in the snapshot's library registration; a future snapshot-maintenance change should include the entry and recheck its identity deliberately.

The environment override is rooted at `KICAD_CONFIG_HOME`; this KiCad version reads global library tables under its **`10.0/` subdirectory**, not directly from the root. The final command was:

```sh
KICAD_CONFIG_HOME=/private/tmp/temper-stage19b-rubric-review-2026-10-13/fresh/kicad-config-4 \
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc \
  --all-track-errors --schematic-parity --refill-zones --format json \
  --output /private/tmp/temper-stage19b-rubric-review-2026-10-13/fresh/drc-4.json \
  /private/tmp/temper-stage19b-rubric-review-2026-10-13/input/hardware/native21-stage19b/section.kicad_pcb
```

The private versioned `fp-lib-table` adds only:

```scheme
(lib (name "Package_DFN_QFN") (type "KiCad")
 (uri "/private/tmp/temper-stage19b-rubric-review-2026-10-13/input/hardware/native21-stage19b/candidate-libs/Package_DFN_QFN.pretty")
 (options "") (descr "Review environment registration of already pinned vendored library"))
```

The JSON reports also record five ignored checks inherited from the project: missing courtyard, track endpoint centering on via, tuning-profile geometry, symbol footprint-filter mismatch and footprint-type mismatch. Those checks were not independently passed. DRC has not tested actual material, assembly, EMC, temperature, protection or whether the supplied rules meet the product requirements.

An earlier sandboxed attempt produced no valid JSON report and was not counted as a completed check. Native execution produced fontconfig warnings; the completed reports contain structured results and the last run lists zero violations. Command exit status alone was not used as the verdict.

## Layer and native geometry inspection

Native SVG export used `F.Cu,In1.Cu,In2.Cu,B.Cu`, common `Edge.Cuts,F.Fab`, cropped page mode and one file per layer. A native multipage PDF using those four layers was rasterized at 100 dpi with `pdftoppm` and all four pages were visually inspected. The four PNGs are retained in `evidence/`. The figures are qualitative; native pad/track/via queries and selected source-bound geometry gates supply numerical checks.

The independent [native R5 pad query](evidence/r5-native-pads.json) used KiCad's own `pcbnew.LoadBoard` and `GetPosition`, rather than a copied rotation formula. The headless library printed a wx application assertion but returned normally; the pad/net results agree with the embedded board objects and the other native reviewer queries. [Position CSV](evidence/positions.csv) retains the practical reviewer's native front-side placement export. KiCad position Y sign and the manufacturing CPL convention still need assembler preview; this verification does not decide the vendor convention.

There was no new 3D-model coverage or interference pass. Prior producer enclosure-body checks were reviewed as modeled evidence. No board/CAD mutation, fabrication export release, component order, physical board measurement or solver-chain rerun occurred.

## Document and provenance validation

The six assessment tables contain **179 unique IDs**, exactly equal to the original criterion index: BP28, OTT35, SI29, AOE37, MAG29 and AN13921. Every row has a valid score, evidence/rationale and next check. Markdown table columns and local artifact links were checked. All six original rubric-file hashes still match their source manifest. Six GPT-6 Sol reviewers worked independently; parent reconciliation corrected R5 coordinate definitions, credited the supplied stage19b return audit, updated thermal-model precedence and distinguished floating/earthed-pan EMI margins.

[Machine-readable verification](evidence/verification.json), [criterion decisions](criterion-index.json), [input identity](evidence/identity.json) and [key source ledger](evidence/source-ledger.json) retain the results. The ledger includes 45 source/rubric entries and no unresolved requested path. The assessment does not average criteria or infer readiness from counts.

The publication checkout is based on the current main line, which retired the legacy placer gates. Both `make regen` and `make regen-check` were attempted and returned “No rule to make target”; `scripts/import_linter_gate.py` is absent. These are unavailable checks, not passes. This change adds review documents and evidence only; no firmware, placer, Python/Rust module, hardware pin or generated design artifact changed. Whitespace, criterion coverage, original rubric/input hashes, JSON validity and local links were checked directly.
