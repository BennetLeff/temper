# Audit pass 3: the 50 DONE rows (2026-10-19)

Method: listed every row whose status starts with DONE and grouped by the first evidence tag in the row. I did not re-open the cited files in this pass, so every verdict rests on what the row itself says; where I flag a row it is because the row's own text shows a gap, or because pass 1 or 2 found a conflict.

## What DONE means here
| First evidence tag | Rows | What it shows |
|---|---|---|
| [DEC] a decision recorded in DECISIONS/README | 36 | That a choice was made. Not that it works |
| [CODE] code or a tool | 9 | That it builds or runs on the host |
| [CAD] | 2 | That the model fits |
| [VEN] vendor read | 1 | A price on one date |
| [PLAN] | 1 | A written plan |
| (no tag) | 1 | DOC-04, an inventory list |

Result: none of the 50 rests on a bench measurement (consistent with the checklist author's note that the project has none). 36 of 50 are decisions. A DONE on a decision should be read "decided", and the checklist would be clearer with a separate verified column.

## Downgrade or flag
| Row | Row says | Problem | Proposed status |
|---|---|---|---|
| FW-28 host tests | DONE (committed evidence, not re-run); 29/29 on 2026-10-12 | Not re-run, and older than the J13 pin edits (2026-10-18) and the MAX31865 divergence. Its own text says "not re-run" | IN PROGRESS |
| FW-26 ESP-IDF build | DONE (committed log); strict v5.3.6 build, "built outside the repo" | The log predates the J13 ESP-IDF edits, which no CI job builds (audit 2, C15) | IN PROGRESS |
| CTL-08 CPL rotation, ICs | DONE (vendor viewer) | Pin 1 confirmed on 16 parts and polarity on C9, D7, D9, U7. Connectors J1/J2/J3/J4/J7, D1–D6 and C1 were not checked, and the J4 position was not rechecked after the revert | IN PROGRESS for the unchecked parts |
| ENC-18 PS3 clearances | DONE (CAD) | PS3's part is MPM-65-15ST per DECISIONS, but the R43 BOM says IRM-60-15ST (audit 1, C12). The clearances were measured on one body; the other is "same case" per DECISIONS but that is unverified here | Keep DONE only if the CAD uses the MPM-65 body; check |
| ENC-35 R4 flush front | DONE (superseded concept) | A superseded concept is not an achievement | Remove from the DONE count (status SUPERSEDED) |
| PWR-01 board of record | DONE (candidate, not released) | The row itself says it is not released | OPEN until released, or label "candidate selected" |
| PWR-80 design review | DONE (desk) | Desk review found 2 MAJOR and further findings open; no BLOCKER | IN PROGRESS until the MAJORs close |
| CTL-04 design verification | DONE (desk); 248 checks, 0 failed | A script over the design data. Passing it did not catch the CPL rotation error that the viewer caught | Stands as desk; do not let it stand in for CTL-08 |
| PWR-09 bare-board price | DONE (quote read) | One dated vendor read; JLC prices move | Stands as a dated read, not a locked price |
| SNS-07 bench kit on alumina | DONE (bench decision) | The +20.2 % capacitance is "model-corrected"; the h_c contact assumption is unmeasured | Stands as a decision; the dependent claims are model-only |
| COIL-24 coil stud | DONE (by evidence); doc fix OPEN | Correct (M4); the R43 BOM text still misleads | Stands; the doc fix remains |
| COIL-31 first-power rules | DONE (decision) | The aluminium-pan figure (28–36 A rms) is a simulation; the rule is safe either way | Stands |
| CMP-24 patent-driven design rules | DONE | A design rule from reading patents. No attorney review (the checklist says not legal advice) | Stands as a rule; certification-grade clearance remains open |

## Stands as stated (decisions or tools, nothing found against them in this pass)
G-05 (decision; basis still IN PROGRESS), PWR-03, PWR-04 (vendor DFM pass), PWR-14, PWR-21, PWR-56, CTL-01, CTL-02, CTL-06, CTL-07, CTL-18, CTL-21, CTL-23, COIL-08, COIL-10, COIL-15, COIL-17, COIL-21, COIL-25, COIL-28, SNS-03, SNS-40, UI-07, UI-19, ENC-09, ENC-15, ENC-16, ENC-27, FW-02, FW-03, FW-14, FW-17, FW-25, TST-03, CMP-02, CMP-07, DOC-04.

Caveat on "stands": a DONE decision in this list may still have an open consequence in another row. Example: PWR-21 (bridge devices) is a selection, and its thermal and clamp behaviour is open under the PWR-28 to PWR-44 rows.

## Proposed edits to CHECKLIST.md (not applied)
Eight rows change status: FW-28, FW-26, CTL-08, PWR-01 and PWR-80 to IN PROGRESS/OPEN, ENC-35 to SUPERSEDED, ENC-18 on a check, and the status wording for the verified-versus-decided split. After that the DONE count would be about 43 rather than 50. I have not applied them because the checklist is the subagent's deliverable and the owner is auditing it; apply them if you want the file to match.
