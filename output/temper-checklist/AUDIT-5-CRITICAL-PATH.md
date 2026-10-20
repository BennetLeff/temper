# Audit pass 5: critical path and open rows (2026-10-20)

Method: parsed the 379 table rows of `CHECKLIST.md` (the status counts match the subagent's report: OPEN 196, IN PROGRESS 82, DONE 50, OWNER-ONLY 41, BLOCKED 10) and checked the "Critical path" section against them. Counts below come from that parse. I did not re-open the cited evidence files in this pass.

## Critical path structure
- The path names 83 row IDs; every one exists in the table.
- Of 206 OPEN or BLOCKED rows, 0 lack an owner. 139 have nothing in "Blocked by". That is not a fault for work that is simply not started, but it means the dependency graph is thin: only the 10 BLOCKED rows and some OPEN rows record what they wait for.
- 65 OPEN or BLOCKED rows record no decision ("none"). Those are the rows an auditor must decide before the item can be closed.
- Six rows carry no evidence at all: UI-03, TST-17, TST-20, TST-21, CMP-25, CMP-27. They are plans or placeholders and should be labelled so.

## The 10 BLOCKED rows and what they wait on
| Row | Waits on |
|---|---|
| PWR-79 power order gates | PWR-06 (laminate answer), PWR-72 (inlet module), PWR-13 (CPL check) |
| PWR-72 conducted EMI | inlet-module part; the request is unanswered |
| PWR-24 | availability "from 30 December 2026" (Conro); no alternative recorded |
| CTL-12 R39 | supply |
| COIL-23 ring lug | supply (see HOT-LIMITS.md: 50840 obsolete at Digi-Key, 1577639-1 at 24 weeks) |
| SNS-10 bond adhesive | vendor statement (≥ 260 °C continuous) |
| SNS-11 hot-zone insulation | supplier confirmation |
| UI-20 enclosure items | ENC-03, which waits on the owner declaring R43 final |
| ENC-03 | the owner's declaration |
| ENC-31 inlet EMI module | module selection |

Three of the ten (PWR-72, ENC-31 and, through it, PWR-79) are one problem seen from three rows: the inlet EMI module has not been chosen. That single decision gates the power order.

## Items the critical path should carry and does not
| Item | Row | Why it belongs |
|---|---|---|
| J4 mating side | CTL-20 (OPEN) | Contradiction C19 (audit 4). The plug has to be reachable; this decides the enclosure cutout and checks the CPL rotation. It is not on the controller order step |
| ESP-IDF build in CI | FW-30 (OPEN) | Contradiction C15. J13 firmware files have never been compiled since 2026-10-18; step 2 fixes firmware but nothing proves it builds |
| RCA 12A3 coil | COIL-33 (OPEN) | No decision to use, measure or retire it; the 3D FEM and tank sweep wait on its dimensions. Step 5 only covers the new coil |
| Display and fascia temperature | UI-02, UI-21 (OPEN) | Fascia 116–176 °C against the OLED's 85 °C and the VHB's 93 °C. Step 9 lists UI work only for an enclosed prototype, but any enclosed first-power run meets it |
| Stand-in sensor for first heating | none | The checklist itself says this is not stated in the repo (step 8). It needs a decision before bring-up |
| Controller and firmware branch choice | DOC-02 (OPEN) | Step 1 says merge; there are three firmware lines (audit 1, C4/C5). Which one wins is the owner's call, and every firmware row depends on it |

## Ordering problems
- Step 2 (firmware fixes) needs the step 1 baseline, and step 1 needs the owner to commit and choose the branch. Both are listed as "Claude can do these now", but step 1's merge decision is the owner's.
- Step 5 puts the lug decision (COIL-22, COIL-23, PWR-70) inside the coil build, but PWR-70 is a power-board decision (insulated M4 lugs required) and COIL-23 is BLOCKED on supply. The lug is a critical-path item in its own right and should come before winding is finished, since the leads are terminated at the end.
- Steps 3 and 4 run in parallel but both gate on the owner's JLC actions; nothing in the path sequences them against each other or against spend approval.
- Step 10 (certifier) is in the production half, but its answers (stuck-on cut, reinforced insulation at the sink, IEC-only supply modules) can force a re-layout of the board that step 3 orders. The checklist says the certifier precedes the production layout freeze; it does not say whether to ask before the prototype order. Asking earlier costs nothing, since a prototype can be re-spun.

## Proposed edits to CHECKLIST.md (not applied)
Add the six items above to the critical path, split step 5 so the lug decision comes first, and label the six evidence-free rows as placeholders.
