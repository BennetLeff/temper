# native-21 open items (register, 2026-10-15)

One row per open item on the power board, so nothing falls between lanes. Board of record: **s32** (board 2fb346dc,
4 layers, DECISIONS 35, 40). Keep this current: when an item closes, give the DECISIONS number and move it to "Closed"
at the end. Agents named "running" write to scratch; the integration session reviews and commits their results.

Lanes:
- **Layout lanes** are one-writer worktrees, one per isolation island (13-coupling), merged one at a time through the
  scorecard. At most 2–3 run at once.
- **Analysis lanes** build nothing and run in parallel.

## 1. Correctness and safety (ranked first)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| S1 | Touch leakage FAILS: 0.974 mA design case vs 0.5 mA UL 1026 portable limit and the 0.25 mA (50 %) rule. Candidate 23 + D-22 rev B gives 0.419 mA, still failing | `07-conducted-emi/leakage/result.json` | Analysis: leakage × EMI co-design (EMI has 10.5 dB slack) | Running | Change set that passes both; then candidate 23 folds it in |
| S2 | Board temperatures never compared with ratings: B3 162 °C under U42 (nominal, h10), 135 °C c28_h25, against laminate MOT ~130 °C; RECOM U41/U42 derating valid only to 85.6 °C local air | `b3/outputs/summary.json`; ledger R24C2T25 | Analysis: thermal vs ratings audit and gate | Running | Ratings table, verdicts, a scorecard gate, ranked fixes |
| S3 | F6's 252/252 result rests on round-17 loop matrices from board 76ec8cca, not s32 | `c33-six-layer/adoption/README.md` | FEM (remote box) | Blocked: box offline | Owner restarts the box; run `adoption/fem/chain_c33.sh` for s32 (campaign ready) |
| S4 | Laminate CTI ≥ 175 V | DECISIONS 41 | Order | Closed by naming KB-6164 | Certifier accepts PLC 3 as group IIIa (packet A3) |
| S5 | Board thickness vs REDCUBE 1.6–2.0 mm; JLC ±10 % | DECISIONS 42 | Layout lane: candidate 35 | Running | Verdict; interim order remark in FAB-NOTE |
| S6 | CMTI 1.5× rule not met on FILTERED / OPEN rows (1.05×) | `c31-bom/README.md` | Parts / certifier | Open | Covered by the isolator review; NSi822xW rejected (no open-input state) |
| S7 | Datasheet ledger: 3 VERIFIED / 32 PARTIAL / 59 UNAUDITED of 94 lines | `datasheet-ledger/` | Parts verification lane | Deferred until the BOM settles (after the sourcing and device studies) | Then PARTIAL SAFETY / POWER lines to VERIFIED, in parallel |
| S8 | C5 / C6 ripple at the 28 A ceiling (~130 % of TDK's permitted ΔT at 85 °C ambient) | QUEUE "C5/C6 ripple" | Analysis: sourcing study | Running | Alternate that fixes ripple and lead time, or an ambient limit |
| S9 | Resonant bank 1.045× TDK's curve at 28 A | DECISIONS 37 | Candidate 34; sourcing study (other vendors) | Waits on stock | In-stock part ≤ 0.85× |
| S10 | Return-path open changes 18; six layers took them to 8 | DECISIONS 39–40 | Layout (LS / HS-B) | Open | Targeted four-layer fixes after the lanes merge |
| S11 | Certifier questions (CERTIFIER-PACKET A1–A4: F1, insulation, PEC / FMEA, supply approvals, RES_A, coil-lane voltage) | `owner-items/CERTIFIER-PACKET.md` | Owner | Draft, not sent | Owner sends the packet |

## 2. Buildability (JLC fab and assembly)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| B1 | 8 zero-stock and 19 single-source lines; L1 (CM choke) at zero everywhere; lead times of 17–29 weeks on C5/C6, L1, J2/J5, U26, TPS70950, IRM | STOCK-2026-10-13 | Analysis: sourcing study | Running | Fresh snapshot, alternates, pre-order plan |
| B2 | Buildability metric (stock for 5 / 500 builds, JLC-assemblable share, build lead) | DECISIONS 43 follow-up | Sourcing study, scorecard patch | Running | Review the patch and restate the cards |
| B3 | REDCUBE THR reflow (pin-in-paste) not confirmed at JLC | r2-dfm | Candidate 35 | Running | SMT part removes it |
| B4 | Order remarks: KB-6164 with KB-6064 prepreg, thickness 1.60–1.76 mm, stack JLC041622-7628 named, Confirm production file | FAB-NOTE | Order (owner) | Ready | Answered at JLC's file review |
| B5 | Track-geometry hygiene: 104 right angles, 206 acute corners (44 fold-backs), 704 mm any-angle | DECISIONS 43 | Cleanup pass, after the lanes merge | Metric in place (ratchet) | Build the cleanup tool, prove it on s32 with the chain |

## 3. Cost (parts $208.08 + bare board $17.28 per board at 500)

| # | Item | $ per board | Lane / owner | Status |
|---|---|---|---|---|
| C1 | Bridge MOSFETs 4 × IPW65R018CFD7 | 40.70 | Analysis: device frontier (loss, ZVS, thermal) | Running |
| C2 | Bus TVS D3 / D17 (B1 / B2) and F1 (A2 #5) | 19.64 + 18.52 | Owner / certifier | Packet |
| C3 | U41 / U42 RECOM bias modules (also S2's hottest spot) | 14.74 | Analysis: discrete isolated supply (bootstrap rejected, DECISIONS:91) | Running |
| C4 | C5 / C6 | 12.34 | Sourcing study | Running |
| C5 | PS1 deletion (candidate 23) | ~8.40 | Layout lane: SELV side | Waits for the S1 result and the controller's J13 |
| C6 | Bank, T1, L1, PS2, J2 / J5 and the rest of the top 15 | ~60 | Sourcing study | Running |
| C7 | Bare board: six layers $19.11 vs four $17.28 pinned; area compaction ~$1.5 per 10 % | DECISIONS 40 | After candidate 23 (compaction) | Open |

## 4. Layout lanes

| Lane (island) | Candidate | Status | Blocked on |
|---|---|---|---|
| Tank (WS3) | 35: SMT coil terminals | Running (ps-layers) | — |
| SELV side (WS5, spine owner) | 23: delete PS1, logic from PS3 over J13; F2 / filter | Ready to start | S1's change set (supplies and Y caps). The controller's J13 gates the merge, not the board work: the request fixes the pinout |
| HS-B / LS (WS4) | 30a (HS-B → LS ISO6721FB), 30b (C161), return-path fixes | Blocked on four layers (no via-legal cell in the y 47–60 band) | Needs a targeted re-placement of the LS pocket / U42 to open the band |
| Tank / bank | 34: resonant bank | Waits on stock | Sourcing study |
| Whole board (last) | Geometry cleanup pass; compaction | After the lanes merge | — |

## 5. Owner actions

- Restart the remote FEM box (S3).
- Send the certifier packet (S11, C2).
- Relay `c23-supply-topology/CONTROLLER-REQUEST.md` to the controller session (J13).
- Pre-order the long-lead parts once the sourcing study gives the plan (B1).
- Bench: coil L / R with real pans; bank hot spot; terminal and module temperatures (S2).

## Closed

- Six layers: phase A accepted on the data, not adopted on price (DECISIONS 39–40).
- CTI (DECISIONS 41).
- SELV-spine lock in the chain (27e946580).
