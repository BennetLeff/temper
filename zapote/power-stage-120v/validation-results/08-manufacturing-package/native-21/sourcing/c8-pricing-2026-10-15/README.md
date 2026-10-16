# C8: pricing the native-21 BOM from real reads

Work product for OPEN-ITEMS C8. Nothing here is applied to the repo. PS = `zapote/power-stage-120v` on
`codex/power-stage-integration` at eec1c2083. All numbers were produced offline from committed files; no web page was
fetched (see Limits).

## Result

| | legacy card (today) | new basis (`_v2`) |
|---|---:|---:|
| s45 parts @ 500 boards | $201.60 | **$171.71** |
| s45 parts @ 5 boards | $304.99 | **$262.77** |
| s44 parts @ 500 / 5 | $202.38 / $306.90 | $171.53 / $262.58 |
| **s44 -> s45 @ 500** | **-$0.78** | **+$0.1807** (cost45.py JLC basis +$0.1807, difference $0.0000) |
| s44 -> s45 @ 5 | -$1.91 | +$0.1959 |
| lines priced from an estimate (s45) | 54 class-default + 2 proxies = 56 of 94 | 0 |

The delta needed no explaining: every changed line of s44 and s45 is a P1 line (JLC in stock, ladder at the true lot), so
the new module reproduces `cost45.py`'s per-line JLC deltas exactly (worst difference 0.00000). The legacy card reads -$0.78
because TL431A was $0.40 against a $0.0486 read and the five new resistors carried reads while the five removed ones
carried the $0.008 default.

Both legacy totals were re-derived here from the STOCK files with `scorecard.py`'s rule and equal the committed cards
(304.99 / 201.6 for s45; 306.9 / 202.38 for s44), so the "before" column is exact.

The new total is lower mainly because estimates were too high on cheap parts and because a handful of parts had old DK
list prices where JLC stocks the part: 30KPA150CA -$11.47 per board (survey $9.82 flat; DigiKey Good-Ark 2026-10-15 ladder
$4.08 at 1,000 pcs), CST3015-200ED -$4.13, GBJ2510-F -$3.36, MPM-20-24 -$2.82, KLDR025.TXP -$2.64, B32654A1104J000 -$2.53,
TPS70950DBVR -$2.02. It is higher on the lines the default under-priced: LM4040A25IDBZR +$0.86 ($0.40 -> $1.2636),
TLV3201AIDBVR +$0.82, TPS3700DDCR +$0.43.

## Files

| File | What |
|---|---|
| `work/native-21/layout/gates/bom_pricing.py` | the pricing module (proposed new file; its docstring is the spec) |
| `work/native-21/layout/gates/scorecard.py` | patched scorecard (proposed) |
| `work/native-21/layout/gates/test_bom_pricing.py` | controls (proposed new file) |
| `c8-bom-pricing.patch` | the three files above as one patch, repo-root relative (`zapote/power-stage-120v/...`) |
| `inventory-s45.csv` / `.md` / `.json` | per-line inventory, 94 lines; `.json` carries every candidate read for every line |
| `rescore-s44.json`, `rescore-s45.json` | re-scored cost fields (`new_basis` is what the card will carry) |
| `delta-s44-s45.json` | per-line delta against cost45.py |
| `cost-fields-s44.json`, `cost-fields-s45.json` | the full `cost` dict the patched `scorecard.cost()` returns, run in a scratch copy |
| `make_inventory.py` | regenerates the inventory, re-scores and the delta (`python3 -I make_inventory.py`) |
| `test-results.txt` | test output |

## Inventory summary (s45, 94 lines; `inventory-s45.csv`)

Columns: what the card uses today (class, source text, date, unit at 5 / 500, per-board line), then for 5 and 500 boards
the lot size in parts (qty per board x boards), tier, unit price from the ladder at that lot, per-board line, source, read
date, flags; then the line delta at 500, artefacts, and every other read at 500.

Price source the card uses today: 38 lines carry a read (DK, LCSC, JLC ladder, dated 2026-10-09 to 10-15), 54 carry the
2026-10-13 class-default estimate, 2 carry a proxy that is not a read (CST3015-200ED "SET EQUAL" to the -100ED;
B32654A1104J000 DK K-grade price x a JLC J/K ratio).

Best read used by the new module:

| Tier | Meaning | lines @5 | lines @500 |
|---|---|---:|---:|
| P1 | JLC library part, JLC stock covers the lot, JLC ladder price | 83 | 71 |
| P2 | authorised distributor holds the lot (2026-10-15 read), its ladder price | 4 | 4 |
| P3 | no 2026-10-15 read shows a holder; best-covering read | 7 | 19 |
| P4 | JLC listed_no_stock ladder, nothing else | 0 | 0 |
| P5 | estimate (no read at all) | 0 | 0 |

Read dates: JLC part pages 2026-10-15 ~06:40 Z (the s45 resistors and TL431B from `jlc-raw/detail_*.json`, same day);
DigiKey page reads 2026-10-15 06:4x Z; Octopart authorised offers 2026-10-13 to 10-15 (date per offer in the JSON);
survey reads 2026-10-13 / 10-14.

Flagged lines (all on `inventory-s45.csv`):
- **Artefacts rejected by rule:** R24C2T25/R-R (U41 / U42 RECOM), JLC $0.0397 @5 and $0.0204 @500 (listed_no_stock) against
  DigiKey $7.954 / $7.37148. The card already used DigiKey; the 2026-10-15 snapshot did not (its $185.21 @500 includes the
  $0.0204, a $14.7 per-board understatement).
- **JLC listed_no_stock, not a purchasable price (8 lines):** KLDR025.TXP, B82726S2203A020, B32676G1905K000, 7466004R,
  3403.0279.23, 30KPA150CA, 1704004, R24C2T25/R-R. None is used as a price; every one has another read.
- **P3 lines at 500 (19 lines, $121.68 of the $171.71):** no 2026-10-15 read shows a holder of the full lot. Seven of them
  are priced from a 2026-10-13/14 survey read (flagged, and the flag says whether its stock count covers the lot):
  DE1E3RA222MA4BP01F, 2EDR8259XXUMA1, IPW65R018CFD7, B2P3-VH(LF)(SN), 3403.0279.23, B32652A0104K000, R24C2T25/R-R.
- **Reel-only / MOQ:** 30KPA150CA is priced at 5 boards from DigiKey's 164-piece cut-tape offer (MOQ 1, $6.727) and at
  500 boards from the 1,750-piece Good-Ark reel offer (MOQ 250 <= the 1,000 pieces needed, $4.08447). The only line whose
  MOQ exceeds the lot is 1704004 at 5 boards (best offer MOQ 50 against 5 pieces; the excess is bought, not priced; flagged
  `moq 50 above need` and `below_first_break`).

## Source preference order (also in the module docstring)

Per line and per board count N, need = qty_per_board x N parts. The first tier with a price wins; inside a tier the lowest
non-artefact price wins (P3: see below), ties broken by source name.

1. **P1 JLC stock.** JLC library part (basic or extended) with JLC stock >= need: the JLC ladder price at need.
2. **P2 authorised stock.** An authorised, non-broker offer (DigiKey page read, else the Octopart authorised offers) with
   stock >= need and MOQ <= need: its ladder price at need. Brokers and unauthorised sellers are never priced.
3. **P3 nobody holds the lot.** Over the authorised ladders (stock ignored), survey reads and the ladder of a JLC library
   part with short stock: the read whose stock covers the largest share of the lot, then the lowest price. Reason: the
   bulk of a short lot will be bought where the stock is. A survey read with no stock count covers 0.
4. **P4 JLC listed_no_stock.** Used only if P1-P3 are empty, and only if it passes the artefact rules.
5. **P5 estimate.** The class-default estimate or proxy from the survey row. Listed in `price_estimated_lines`.
   No survey row: the line is `price_unpriced_lines`.

This is a fixed order, not "cheapest source": JLC stock first because the board is a JLC assembly and JLC's own stock is
the route with no extra buy. The cheapest stock-holding read is kept per line as a sensitivity (`totals` key
`..._cheapest_stock_holding`): $262.55 @5 and $171.71 @500 on s45, so the order costs $0.22 @5 and nothing @500.

Survey rows (STOCK-2026-10-13*.csv) are classified from `price_source`: DK / DigiKey -> distributor read; JLC / LCSC -> JLC
read; `price_is_estimate` yes or `ESTIMATE...` -> estimate; `SET EQUAL...` or a ratio-derived price -> derived proxy;
anything else -> not a read. Estimates, proxies and unclassified rows never act as reads. Of two survey rows for one MPN the
later `check_date` wins (e.g. the KLDR price fix).

## Artefact rules

A read failing any rule is dropped from P1-P4 and listed in the card's `price_artefact_lines`.

- **A1** zero or negative price. A source with no price at all is not a candidate (not an artefact).
- **A2** a JLC listed_no_stock row with no ladder.
- **A3** price below 10 % of the median of the other reads for the same line and lot. Needs one other read. Estimates and
  proxies do not count as reads. (RECOM: 0.0204 < 10 % of 7.37148.)
- **A4** a JLC listed_no_stock ladder is never a P1 price; at most P4.

## Patch

`c8-bom-pricing.patch` (apply from the repo root or from PS: `git apply --check` passes from both, verified read-only):

- `scorecard.py` loads `bom_pricing.py` with `importlib` (like `track_geometry`) so it works under `python3 -I`; `cost()`
  adds the v2 keys; `main()` records the source in `card["sources"]["bom_pricing"]`.
- **Key meanings.** The legacy keys `parts_usd_at_5`, `parts_usd_at_500` and `unpriced_lines` keep their 2026-10-13
  stock-survey meaning, byte for byte (304.99 / 201.6 on s45), so every old card stays comparable. New keys:
  `parts_usd_at_5_v2`, `parts_usd_at_500_v2`, `price_basis` (`bom_pricing-v1`), `price_estimated_lines`,
  `price_unpriced_lines`, `price_artefact_lines`, `price_short_lines_5` / `_500`, `price_tiers_5` / `_500`.
- **Compare.** `compare()` uses `parts_usd_at_500_v2` only when both cards carry it with the same `price_basis`. If one
  card has it and the other does not (new card against an old benchmark), it compares the legacy key and prints
  `NOTE: price basis differs ... the v2 totals are not compared`. With `--strict-basis` it REJECTs instead
  ("parts cost not comparable"). The `compare` signature gained optional `notes` and `strict_basis`; both callers pass them.
- Until a benchmark is re-scored it has no v2 keys, so every compare against today's benchmark prints the NOTE. To move the
  benchmark to the new basis, merge `rescore-s45.json["new_basis"]` into `scorecard-native21s45.json["cost"]` (and the same
  for s44 from `rescore-s44.json`); that is a benchmark-card edit and was not done here.

## Tests (`test_bom_pricing.py`; output in `test-results.txt`: 29 checks, PASS)

Run: `PS_ROOT=<PS> python3 -I test_bom_pricing.py` for the copy here; inside the repo, `python3 -I native-21/layout/gates/test_bom_pricing.py`.

- The artefact rule catches the RECOM row, on the synthetic case and on the real data at both 5 and 500 boards, and the
  line is priced $7.954 / $7.37148.
- A1, A2, A3 (including the exact-10 % boundary and the no-other-read case) are each tested.
- s44 -> s45 at 500 boards: +$0.1807 against cost45.py's committed +$0.1807 (limit $0.01); every changed line matches
  its per-line JLC delta (worst difference 0.00000).
- Estimates appear only where no read exists: synthetic (a JLC read beats an estimate row; a SET EQUAL proxy is not a
  read; no read gives P5; no row at all gives unpriced) and real (no s44 / s45 line is estimated or unpriced while a read
  exists).
- Ladder at the true lot: 25,500 parts takes the 24,000 break; below the first break is flagged.
- Tier rules P1 / P2 / P4 and the exclusion of unauthorised offers.
- Determinism: two in-process runs and two `python3 -I` CLI runs give byte-identical JSON.
- Compare: new-basis card against old-basis benchmark prints the NOTE and uses the legacy key; `--strict-basis` exits 1
  with REJECT; two v2 cards compare on `parts_usd_at_500_v2`.

## Limits

- **The $171.71 is not a quote.** 19 lines at 500 boards ($121.68) are P3: no read dated 2026-10-15 shows a source holding
  the whole lot, so they are priced from the best-covering list ladder or older survey read. The biggest are the four
  IPW65R018CFD7 ($10.18 each, DK survey 2026-10-13, 459 in stock against 2,000 needed), the bank capacitors
  B32654A1104J000 (5 per board, DigiKey 881 in stock against 2,500), 30KPA150CA and KLDR025.TXP. Buy lead and stock risk
  stay in the buildability keys, not in this price.
- **Not priced:** JLC extended-part fees, assembly and setup, Global Sourcing markup, shipping, duty, attrition, tax.
  Same as the legacy card.
- **A3 needs two reads.** Most passives have only a JLC read, so an artefact on a single-read line cannot be caught by rule.
  A1 catches zeros only.
- **Survey classification reads `price_source` text** (prefixes DK / DigiKey / JLC / LCSC / ESTIMATE / SET EQUAL). A new
  free-text source falls in "not a read" and is then ignored, which is the safe direction.
- **Reads are the committed 2026-10-15 snapshot.** The module never fetches. Octopart offers are dated per offer
  (10-13 to 10-15); the two-point DigiKey in-page reads (3 MPNs) price only 5 and 500 boards. When the snapshot is
  re-taken, the module picks up the new files if they keep the same names and schema; a stage that adds an MPN needs its
  JLC page cached in `jlc-raw/` (as stage 45 did) or the line falls to survey, then estimate.
- **No fresh web reads were made.** No line is estimated, so there was nothing the task required a fresh JLC / LCSC page
  for. `dl/` is empty.
- **Fixed preference order.** It is $0.22 above the cheapest stock-holding read at 5 boards (see above).
- **Not run:** the full scorecard (no build directory), `depmap_check.py` (adding `bom_pricing.py` to its `chain` script
  list at landing is advisable so the scoped chain sees a pricing change; its literal-path scan was not run on the new
  module), the repo's other tests. `scorecard.cost()` was run in a scratch copy with `validation-results` symlinked to PS
  and returned the legacy keys unchanged plus the v2 keys (`cost-fields-s4*.json`).
- `bom_pricing.py` resolves reads from its own location (`parents[3]`); the copy under `work/` is run with explicit
  `--sourcing` / `PS_ROOT`.
