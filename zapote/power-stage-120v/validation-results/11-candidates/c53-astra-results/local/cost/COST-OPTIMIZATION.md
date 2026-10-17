# Cost-down options for the seven most expensive BOM lines (Opus subagent report, 2026-10-17; condensed by the parent)

**Provenance:** a read-only Opus subagent wrote this from the repo and live distributor pages (it could not write its own file, so this is a
condensed copy of its text). **None of its numbers has been independently re-checked by the parent.** WEB = distributor page read 2026-10-17;
SNIPPET = search summary only. Its pricing script (not committed) imported `native-21/layout/gates/bom_pricing.py` read-only at N = 5 / 20 / 500
and reproduced the s53 card ($274.93 at 5, $175.04 at 500).

## Headline
None of the seven lines has a cheap swap that keeps footprint and ratings that the repo has not already taken (the 2026-10-14/15 price corrections
KLDR $29.41 -> $18.52 and TVS $19.64 -> $8.17 already captured the easy money). The seven lines plus the F1 clips are about **$97.39 per board at
500, 53 % of the $175.04 card** (which excludes the clips).

## Baseline per board
| Line | $ at 20 | $ at 500 | Stock against the 500-board need |
|---|---|---|---|
| Q2/3/5/6 IPW65R018CFD7 x4 | 75.87 (tool, JLC $18.97, JLC holds 4) / 45.68 at DigiKey 60-break $11.42 | 40.70 (DigiKey 510-break $10.176) | DigiKey 459 vs 2,000, 8 wk |
| L1 B82726S2243A020 | 11.70 (Mouser 10-break) | 9.21 | 62 + 29 in stock; production 2203: $9.885 DigiKey, 0 stock, 29 wk |
| C5/C6 B32676G1905K000 x2 | 16.03 | 12.01 | 547 vs 1,000; 27 wk |
| J2/J5 7466004R x2 | 5.00 | 3.66 | OK |
| F1 KLDR025.TXP | 16.35 | 15.88 on the card; about 18.1-18.5 realistic | Future 300; rest from Master ($19.90) or DigiKey ($18.52 at 500) |
| F1 clips 01250003H x2 (not in the BOM) | 6.50 | 3.80 | OK |
| D3/D17 30KPA150CA x2 | 13.45 | 8.17 | 1,750 |
| U26 TPS7A4700RGWR | 4.74 | 3.96 | JLC 998 |

## Ranked actions
| # | Action | $/bd at 20 | $/bd at 500 | Risk | Gate |
|---|---|---|---|---|---|
| 1 | **Prototype FETs: buy at DigiKey 60-break ($11.42), not JLC's $18.97** (optionally +40 spares and 4-8 CM8 samples for D-8) | -30.19 vs the tool | 0 | none | re-read stock |
| 2 | F1 -> Bel 0ADEC9250-BE + 01220088Z clips | not this lot | -15.98 card / -18.65 vs DigiKey | **high (certification)** | certifier acceptance (G6), layout stage, let-through test |
| 3 | CM8 (IPW65R018CM8) in place of CFD7: value-only (R_on 68 -> 39 ohm, Cgs 4.7 -> 1 nF) | -6.62 | -6.77 | medium | ledger entry, chain, S4/S6, D-8; DigiKey 482 vs 2,000 (24 wk); no 650 V vendor model |
| 4 | Quote round on zero-stock JLC/LCSC listings of the same MPNs | n/a | up to -19, unverified | low | owner approval only for a TVS maker change |
| 5 | Schurter CSO clips (only inside an F1 layout stage; excludes #2) | -3.48 | -2.04 | low-medium | footprint, rejection-end fit |
Runner-up: production L1 on the 2243 instead of the 2203: -$1.21 at 500, but halves CM inductance and needs the module DM part.

## Do not cut
D3/D17 (FMEA B13 backstop for the REF25 fail-high case, and the 2 J absorption), C5/C6 (bus peak and 2 J check), L1 (safety, 80 % rule, EMI), U26
(Tj 120.6 C at release, 4.4 K margin; 0.1 K at c28) and the J2/J5 terminals (pinned by DECISIONS 42/44).

## Defect found in the repo tooling
`bom_pricing.py` `price_at()` returns `points.get(boards)` for survey reads, which only carry prices at 5 and 500 boards. At any other N the DigiKey survey price is
missing, so at 20 boards the FET line falls back to JLC's unbuyable $18.97 and overstates the 20-board cost.

## Could not verify (the subagent's list)
CM8 TO-247 datasheet values and model; live Mouser and Octopart prices (timeout / 403); JLC Global Sourcing markup; all "listed_no_stock" prices; TDK, TTI and
Infineon volume quotes; Schurter clip fit with the Class CC rejection end; certifier acceptance of the Bel part and its CSA / NOM marks; the module DM inductor's
cost and heat; U26's exact load; tariffs, freight and consign handling.
