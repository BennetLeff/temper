# Files for the s53 review (exact paths)

PS = `zapote/power-stage-120v` (in the repository). VR = `PS/validation-results`. N21 = `VR/08-manufacturing-package/native-21`.
`runs-native21/` is the build directory beside the repository worktree; it is **not in git**, so we send those files.
Hashes checked 2026-10-18.

## Board of record (stage 53)
| File | Path | SHA-256 / note |
|---|---|---|
| Routed board | `runs-native21/s53/c53int/section.kicad_pcb` | `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27` |
| Board project / rules / schematic copy | `runs-native21/s53/c53int/section.kicad_pro`, `section.kicad_dru`, `section.kicad_prl`, `section.kicad_sch`, `native21.kicad_sym`, `sym-lib-table`, `fp-lib-table` | same build |
| 3D model | `runs-native21/s53/c53int/board.step` | same build |
| Gate outputs | `runs-native21/s53/c53int/drc.json`, `barrier-gate-rust.json`, `barrier.txt`, `jlc-dfm.json`, `return-path.json`, `bypass-check.json`, `pi-distances.json`, `res-a-creepage.json`, `pin-absmax.json`, `cu-temp-basis.json`, `copper-dump.json`, `copper.png` | same build |
| Chain log | `runs-native21/s53/chain-int.out` | CHAIN_DONE |
| Gerbers | `N21/fab/native-21-gerbers.zip` (unpacked: `N21/fab/gerbers/`) | `a6afd37a4f4e0039de8de7fd86755ff65328f21e43501a23d0904e78ffbd4ddc` |
| Drill report | `N21/fab/drill-report.txt` | |
| JLC BOM / CPL | `N21/fab/bom-jlcpcb.csv`, `N21/fab/cpl-jlcpcb-order.csv` (upload this one), `N21/fab/cpl-jlcpcb.csv` (uncorrected source), `N21/fab/hand-assembly-extras.csv`, `N21/fab/positions-kicad.csv` | |
| Assembly drawing | `N21/fab/assembly-drawing.pdf` | |
| Fab note | `N21/fab/FAB-NOTE.md` | some counts stale (README section 9) |
| DFM result | `N21/jlc-dfm.json` | PASS, 777 vias |

## Parts and netlist
| File | Path | Note |
|---|---|---|
| Resolved BOM | `PS/native-21/frozen/resolved-components.json`, `PS/native-21/frozen/default.csv` | true parts; use these |
| Netlist | `PS/native-21/frozen/default.net` | connectivity only; part fields stale (OPEN-ITEMS B14) |
| Build manifest | `PS/native-21/frozen/manifest.json`, `PS/native-21/frozen/default.layouts.json` | |
| Circuit source | `PS/elec/src/` (atopile 0.2.69); build steps in `PS/README.md` | |
| Datasheet ledger | `PS/native-21/verification/datasheet-ledger/ledger.json`, `ledger-report.json`, `README.md`, `gate.py` | 3 VERIFIED / 92 PARTIAL / 0 VIOLATION at HEAD |

## Layout sources and scripts
| File | Path |
|---|---|
| Copper (tracks, vias, zones) | `PS/native-21/layout/copper.json` |
| Placement | `PS/native-21/placement.json`, `PS/native-21/layout/place.py` |
| Board-only parts (test pads, fiducials, holes) | `PS/native-21/layout/board_only21.json`, `board_only21.py`, `plan_board_only21.py` |
| Layer stack | `PS/native-21/stackup.json` |
| Board build | `PS/native-21/layout/incr_iter.sh`, `PS/prototype-closure/pcb/build_native21.py`, `PS/prototype-closure/pcb/apply_copper21.py` |
| Design rules | `PS/native-21/layout/rules21.py`, `write_rules21.py`, `PS/native-21/section.kicad_dru` |
| Full chain | `PS/native-21/layout/gates/chain.sh` |
| Scorecard | `PS/native-21/layout/gates/scorecard.py`; card `VR/10-benchmark/scorecard-native21s53.json` |
| Stage-53 record and reproduce steps | `VR/11-candidates/c53-cert-provisions/stage53/README.md` |
| Generated schematic | `PS/native-21/section.kicad_sch` (last committed at s52) |

## Gate inputs inside the repo
| Gate | Path |
|---|---|
| D5 audit | `PS/native-21/verification/d5-audit.json` |
| Enclosure fit | `PS/validation-plan/enclosure-fit/native21-in-r43.json`, `native21-body-collisions.json`, `r43-expected-hits.json` |
| Jet strip | `PS/validation-plan/enclosure-fit/native21-jet-strip.json` |
| Kelvin band | `VR/02-protection-timing/kelvin/budget-native21s53.json` |
| B3 ratings | `VR/04-board-current-thermal/round5-native21/b3-ratings/margins.json` |
| Temperature ratings per BOM line | `VR/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15/results.md` |
| Touch current | `VR/07-conducted-emi/leakage/result.json` |
| EMI (prototype L1) | `VR/11-candidates/b15-proto-alternates/results/emi-B82726S2243A020_moduleDM100u/results.json` |
| F1 copper | `VR/02-protection-timing/shoot-through-f1/s53_necks.json` |
| CMTI | `VR/06-controller-interface/cmti/cmti.csv` |
| Bank | `VR/11-candidates/bank28-air/results/bank_air_metric.json` |
| Copper baseline | `VR/10-benchmark/copper-baseline.json` |
| Netlist audit | `PS/audit.rs` |

## Design basis and records
| What | Path |
|---|---|
| Insulation basis | `PS/D5-BASIS.md` |
| Return-current rules | `PS/RETURN-PATHS.md` |
| Fault interface | `PS/FAULT-INTERFACE.md` |
| DC-link clamp | `PS/DC-LINK-CLAMP.md` |
| Decisions (items 50–80 = s38–s53 and after) | `PS/DECISIONS.md` |
| Open items | `PS/OPEN-ITEMS.md` |
| Switching parasitics (s51 matrices) | `VR/01-switching-parasitics/round17/results/matrices-s51/README.md`; `VR/01-switching-parasitics/gate-network-2026-10-15/results/s51-matrices/` |
| Airflow requirement (above 17.5 A) | `VR/11-candidates/airflow28-2026-10-16/README.md` |
| Bank sourcing / prototype BOM | `VR/11-candidates/c51-bank-source/README.md`; `VR/11-candidates/s52-proto-bom/README.md` |
| Monitor FMEA | `VR/11-candidates/c24-monitor-fmea/FMEA.md`; `VR/11-candidates/fmea-s47-2026-10-15/README.md` |
| Commissioning analysis (CT band) | `VR/11-candidates/commission-s53/README.md` |
| Independent review 2026-10-18 | `N21/INDEPENDENT-REVIEW-2026-10-18.md` |
| External review 2026-10-13 | `VR/13-external-review-2026-10-13/FINDINGS.md` |
| Bring-up overview / procedure | `N21/BRING-UP.md`; `firmware/components/power/COMMISSIONING.md` |
| Heatsink stack (M11) | `N21/owner-items/m11/` |

## Certification
| What | Path |
|---|---|
| Question index (s53) | `N21/owner-items/CERTIFIER-PACKET.md` |
| Ranked checklist | `N21/owner-items/CERTIFIER-CHECKLIST.md` |
| F1 inquiry | `N21/sourcing/inquiries/F1-CERTIFIER.md` |
| JLC laminate question | `N21/owner-items/JLC-LAMINATE-QUESTION.md` |
| Laminate CTI research | `N21/sourcing/inquiries/CTI-RESEARCH-2026-10-14.md` |
