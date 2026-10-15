# native-21 open items (register, updated 2026-10-15)

One row per open item on the power board, so nothing falls between lanes. Board of record: **s35** (board fba59ef3,
4 layers; DECISIONS 44, on s32 of DECISIONS 35 / 40). Keep this current: when an item closes, give the DECISIONS number
and move it to "Closed" at the end. Agents marked "running" write to scratch; the integration session reviews and
commits their results.

Lanes:
- **Layout lanes** are one-writer worktrees, one per isolation island (13-coupling), merged one at a time through the
  scorecard. At most 2–3 run at once.
- **Analysis lanes** build nothing and run in parallel.

Scorecard (DECISIONS 43, 45, 46): compare against `10-benchmark/scorecard-native21s35.json`. The release gates
(`RELEASE_GATES`: `b3_ratings`) and the leakage limit are absolute conditions for an order. A candidate is graded on
their ratchets.

## 1. Correctness and safety (ranked first)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| S2 | **Board copper over the laminate MOT in still air.** R5.4 copper ~12 K over 130 °C at 22 A with 55 °C bay air (~56 K at 28 A). HF film C38 / C40 over 110 °C at 22 A. At 28 A also R5's element (197 / 170 °C), the gate resistors and C21. Release gate FAIL: laminate −56.4 K, parts −38.9 K | DECISIONS 46; `b3-ratings/` | Analysis: model refinement (FET-lead path, c28 heat file, film-cap / 1206 limits, fix targets) | Running | Then: candidate 36 (tank copper at R5.4 / FET row), 0.5 mΩ shunt option, enclosure airflow reply. Until it passes: still-air ceiling ≤ 18 A (owner → controller) |
| S1 | Touch leakage FAILS: 0.974 mA design case vs 0.5 mA UL 1026 portable limit and the 0.25 mA (50 %) rule. Candidate 23 + D-22 rev B gives 0.419 mA, still failing | `07-conducted-emi/leakage/result.json` | Analysis: leakage × EMI co-design (now also checking temper-8d's split-R coil EMI model) | Running | Change set that passes both; then candidate 23 folds it in |
| S12 | Laminate UL scope: KB-616(X) multilayer recognition lists max inner copper 35 µm; the stack has 2 oz (61 µm) inner layers. KB-6164F / KB-6165F list 102 µm | DECISIONS 46 side finding | Analysis: model refinement (task 5, public sources) | Running | Pick the order material in scope; certifier packet A3 |
| S3 | F6's 252/252 result rests on round-17 loop matrices from board 76ec8cca, not s35 | `c33-six-layer/adoption/README.md` | FEM (remote box) | Blocked: box offline | Owner restarts the box; run `adoption/fem/chain_c33.sh` for s35 |
| S8 | C5 / C6 ripple at 28 A: on the vendor basis the fitted part carries 28 A only at cap ambient ≤ 80 °C; no stocked part fixes 28 A at 85 °C. 28 % of the HF ripple power is above TDK's 95 kHz chart edge | DECISIONS 45 | Parts | Verdict recorded | B32676G1106K once "Z 1" = catalogue part is confirmed (owner or distributor); bench C5 case temperature |
| S9 | Resonant bank 1.045× TDK's curve at 28 A; no ≤ 0.85 option in authorised stock | DECISIONS 37, 45 | Candidate 34 | Waits on stock | Moot below 28 A while S2 limits the ceiling |
| S6 | CMTI 1.5× rule not met on FILTERED / OPEN rows (1.05×) | `c31-bom/README.md` | Parts / certifier | Open | Covered by the isolator review; NSi822xW rejected (no open-input state) |
| S7 | Datasheet ledger: 3 VERIFIED / 32 PARTIAL / 59 UNAUDITED of 94 lines | `datasheet-ledger/` | Parts verification lane | Deferred until the BOM settles (device and bias studies) | Then PARTIAL SAFETY / POWER lines to VERIFIED, in parallel |
| S10 | Return-path open changes 18; six layers took them to 8 | DECISIONS 39–40 | Layout (LS / HS-B) | Open | Targeted four-layer fixes with the LS-pocket lane |
| S11 | Certifier questions (CERTIFIER-PACKET A1–A4: F1, insulation, PEC / FMEA, supply approvals, RES_A, coil-lane voltage); add S12 to A3 | `owner-items/CERTIFIER-PACKET.md` | Owner | Draft, not sent | Owner sends the packet |
| S13 | temper-8d requests: AMC1301 measured input current on R5 (HOT5 domain; J4 +2 pins; +7–9 % power at the 15 A plug); pan-detect re-validation on the full bridge (Al / Cu / small / warped pans); ±1 kHz dither at 120 Hz (check ZVS at fs − 1 kHz) | `git show sensor-c1-impulse-mining:output/temper-coil-driver-r1/RECOMMENDATIONS.md` | AMC1301 rides with candidate 23 (SELV side); firmware items to the controller | Logged | The power argument is capped by S2 until it passes |

## 2. Buildability (JLC fab and assembly)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| B1 | **L1 B82726S2203A020 sets the build date:** no authorised stock, 29-week lead, so a 500-board build lands ~2027-05 if ordered now. 14 lines short for 500 boards, 3 for 5; JLC-assemblable share 0.851 / 0.968 | DECISIONS 45; `sourcing/study-2026-10-15/` | Owner (ordering); EMI re-run for L1 alternate B82726S2243A020 | Plan ready | Owner pre-orders (README §4). L1 alternate: c29 / D-22 EMI re-run with 0.75 mH / 8 µH |
| B2 | Five "short" lines are read gaps (DigiKey bot check, Octopart 403), not proven shortages | DECISIONS 45 | Sourcing | Open | Re-take the snapshot when the sites read again |
| B4 | Order remarks: KB-6164 with KB-6064 prepreg (S12 may change this), stack JLC041622-7628 named, Confirm production file. Thickness remark dropped (DECISIONS 44) | FAB-NOTE | Order (owner) | Ready | Answered at JLC's file review |
| B5 | Track-geometry hygiene: 104 right angles, 206 acute corners (44 fold-backs), 704 mm any-angle (s35 = s32) | DECISIONS 43 | Cleanup pass, after the lanes merge | Metric in place (ratchet) | Build the cleanup tool, prove it on s35 with the chain |
| B6 | Stencil: J2 / J5 want 150 µm paste; fine-pitch parts' stencil not chosen; J2 / J5 CPL rows NEEDS-PREVIEW | DECISIONS 44 | Order (owner) | Open | Step stencil or aperture choice at order |
| B7 | `PROTOTYPE-LOT.md` lists superseded parts (UCC21550, ISO7710, 74650074R) | `08-manufacturing-package/native-21/` | Integration | Stale | Regenerate from the snapshot when the BOM settles |

## 3. Cost (scorecard parts $206.44 at 500 on the 2026-10-13 survey; $186.54 on the 2026-10-15 snapshot; bare board $17.28)

| # | Item | $ per board | Lane / owner | Status |
|---|---|---|---|---|
| C1 | Bridge MOSFETs 4 × IPW65R018CFD7 | 40.70 | Analysis: device frontier (loss, ZVS, thermal) | Running |
| C2 | Bus TVS D3 / D17 (snapshot: $8.17 from Good-Ark at DigiKey, not $19.64) and F1 (A2 #5) | 8.17 + 18.52 | Owner / certifier | Packet |
| C3 | U41 / U42 RECOM bias modules | 14.74 | Analysis: discrete isolated supply (bootstrap rejected, DECISIONS:91) | Running |
| C4 | C5 / C6 | 12.34 | Parts (S8) | Alternate chosen, pending suffix |
| C5 | PS1 deletion (candidate 23) | ~8.40 | Layout lane: SELV side | Waits for the S1 result and the controller's J13 |
| C7 | Bare board: six layers $19.11 vs four $17.28 pinned; area compaction ~$1.5 per 10 % | DECISIONS 40 | After candidate 23 (compaction) | Open |

## 4. Layout lanes (none building now)

| Lane (island) | Candidate | Status | Blocked on |
|---|---|---|---|
| Tank / FET row (WS3 / WS4 boundary) | 36: tank-copper heat at R5.4 / FET row (wider, more parallel layers, or 3 oz outer); option: 0.5 mΩ shunt | Next | The model-refinement targets (S2) |
| SELV side (WS5, spine owner) | 23: delete PS1, logic from PS3 over J13; F2 / filter; AMC1301 (S13) | Ready to start | S1's change set (supplies and Y caps). The controller's J13 gates the merge, not the board work |
| HS-B / LS (WS4) | 30a (HS-B → LS ISO6721FB), 30b (C161), return-path fixes (S10) | Needs an LS-pocket / U42 re-placement to open the y 47–60 band | The bias-supply study (C3): U42 may change |
| Tank / bank | 34: resonant bank | Waits on stock | S9 |
| Whole board (last) | Geometry cleanup pass (B5); compaction (C7) | After the lanes merge | — |

## 5. Owner actions

- Restart the remote FEM box (S3).
- Send the certifier packet (S11, with S12).
- Relay to the controller session: `c23-supply-topology/CONTROLLER-REQUEST.md` (J13); the still-air ceiling ≤ 18 A until
  S2 passes (DECISIONS 46); temper-8d's controller CR-1..CR-7
  (`git show sensor-c1-impulse-mining:output/temper-sensor-r3/pcb/CHANGE-REQUEST.md`; not this board, so not reviewed
  here).
- Relay `b3-ratings/ENCLOSURE-REQUEST.md` (board-face airflow) and `c35-smt-terminals/ENCLOSURE-REQUEST.md` (lug
  seat +2.5 mm) to the enclosure session.
- Pre-order the long-lead parts (`sourcing/study-2026-10-15/README.md` §4), L1 first.
- Confirm DigiKey's "B32676G1106K Z 1" is the catalogue B32676G1106K (S8).
- Bench: coil L / R with real pans; bank hot spot; terminal pull, torque and temperature; module temperatures; bay air
  and board copper at R5 in an enclosure soak (S2).

## Closed

- Six layers: phase A accepted on the data, not adopted on price (DECISIONS 39–40).
- CTI (DECISIONS 41).
- SELV-spine lock in the chain (27e946580).
- Board thickness vs the REDCUBE terminals, and JLC's THR reflow: SMT terminals adopted (DECISIONS 42, 44; was S5, B3).
- Buildability metric in the scorecard (DECISIONS 45; was B2's metric half).
- B3 temperatures compared with ratings: gate in place (DECISIONS 46; the violation itself is S2).
