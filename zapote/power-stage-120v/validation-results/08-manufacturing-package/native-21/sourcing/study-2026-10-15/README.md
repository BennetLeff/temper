> **Committed 2026-10-15 by the integration session (DECISIONS 45).** Moved here from the study's scratch folder.

> **Board note (2026-10-15):** this study was run on the s32 BOM; its §4 pre-order table still names 74650074 and UCC21550. The long-lead logic stands. For the current list use `../../PROTOTYPE-LOT.md` (s43) and `../SNAPSHOT-2026-10-15.csv`.

> Not committed: `downloads/` (vendor PDFs, Octopart pages; untrusted) and `c34-copy/` (its `bank_margin.json` is
> byte-identical to `11-candidates/c34-bank-margin/results/`, which `run_all.sh` now reads). `run_all.sh` is
> repo-relative; its offline steps reproduce every committed result byte for byte. The scorecard reads
> `../SNAPSHOT-2026-10-15.csv` = `snapshot/s35/SNAPSHOT-s35.csv` (s35 BOM, J2/J5 7466004R) plus the s32 74650074 row.

# Native-21 power board (s32 BOM): sourcing and buildability study, 2026-10-15

This was a read-only study of `zapote/power-stage-120v` on `codex/power-stage-integration`. Nothing in the worktree was edited. No accounts, carts or forms were used, and no supplier was contacted. Vendor PDFs are in `downloads/` and are not for the repo. Run `run_all.sh` to reproduce every number; the online steps are marked in it.

## 1. Snapshot (`snapshot/SNAPSHOT-2026-10-15.csv` / `.json`)

The snapshot has one row per BOM line (94 lines, `fab/bom-jlcpcb.csv` at 38e856ef3). Every count and price is a number. The column list is in the docstring of `scripts/build_snapshot.py`.

**Sources**

| Source | Coverage | Read time | Method |
|---|---|---|---|
| JLC parts API | All 94 lines, plus 40 alternates | 2026-10-15 ≈06:40Z | `jlc_fetch.py`, cached in `scripts/jlc-raw/` |
| DigiKey | 6 product pages, plus 3 early in-page reads | 06:47–06:49Z | Normal browser tab, `scripts/dk_extract_page.js`. DigiKey then rate-limited the reads (HTTP 429) and showed a bot challenge ("Just a moment…"). The challenge was **not bypassed** and the reads stopped. |
| Octopart public search pages | 52 MPNs: every problem line and most alternates. Gives authorised stock and price ladders for DigiKey, Mouser, Newark, Arrow, TME, TTI, Future, Sager, Master, RS… | 06:51–06:56Z | `octopart_fetch.sh`. The site returned HTTP 403 after page 52 and the fetcher stopped. |

**Gaps**
- Mouser, TME, Newark and Farnell direct, Verical and oemsecrets all returned bot blocks or "Access Denied". They are recorded as not readable.
- 50 commodity lines (0603/0402 passives, logic) were checked at JLC only. JLC holds 500 boards' worth of each.
- Where no distributor was readable today, the row falls back to the 2026-10-13 DigiKey count. Those rows are flagged `dist_stock_is_2026_10_13_survey=True`; for example, 74650074 shows 32,606 from that survey.
- Lead times come from DigiKey's standard lead (today's read), or else from the 2026-10-13 survey column (`lead_source`).
- Parts cost from the snapshot: **$250.04 per board at 5 boards and $186.54 at 500.** Each line takes the cheapest source that holds the quantity; where no source holds it, the authorised list price at that quantity.

**Problem lines today.** "Authorised" excludes brokers. Brokers are listed for information only.

| Line | qty/bd | JLC stock | Best authorised (total authorised) | Brokers | Lead | Status for 5 / 500 boards |
|---|---|---|---|---|---|---|
| C5/C6 B32676G1905K000 | 2 | 0 (listed) | DigiKey 547 (547) | 19,730 | 27 wk | Global Sourcing / consign-only |
| L1 B82726S2203A020 | 1 | 0 | **0 anywhere authorised** (TME 0, Newark 0, DigiKey 0) | Fmall 35,580, TIST 3,510 | 29 wk | **short / short** |
| T1 CST3015-200ED | 1 | 64 | No distributor listing; DigiKey: no match | 64 | unknown (Coilcraft direct) | JLC / short |
| D3/D17 30KPA150CA | 2 | 0 | **DigiKey 1,750, Good-Ark, MOQ 250** (1,914) | 1,851 | 12 wk | Global Sourcing / Global Sourcing |
| F1 KLDR025.TXP | 1 | 0 | Future 300 (692: Standard 246, Master 81, Sager 50) | 0 | 5 wk | Global Sourcing / consign (split buy) |
| R5 CSS2H-2512R-1L00F | 1 | 1,380 | Newark 25,967 (152k) | – | 19 wk | JLC / JLC: **no longer a problem** |
| PS1 IRM-20-15 | 1 | 1,497 | Master 2,008 | – | 17 wk | JLC / JLC |
| PS2 IRM-20-24 | 1 | 7,095 | Sager 17,212 | – | 17 wk | JLC / JLC |
| U26 TPS7A4700RGWR | 1 | 998 | No authorised offer listed (DigiKey 0 on 10-13) | 8,120 | 20 wk | JLC / JLC (holds 998 ≥ 500) |
| U3/U37–U39 TPS70950DBVR | 4 | 5,921 | DigiKey 8,164 | – | 20 wk | JLC / JLC |
| J2/J5 74650074 | 2 | 0 | DigiKey 32,606 (2026-10-13 survey; today not readable) | 208 | 26 wk | Global Sourcing (stale) |
| J6 1704004 | 1 | 0 | Amar Radio 48 (153 total) | – | 7 wk | Global Sourcing / short |
| Bank B32654A1104J000 | 5 | 104 | DigiKey 881 (1,114, with Newark 233) | 46,030 | 23 wk | JLC / consign-only (needs 2,500) |

**Corrections to the 2026-10-13 survey**
- 30KPA150CA is **not** zero-stock. The BOM's own manufacturer, Good-Ark, has 1,750 on DigiKey (reel, MOQ 250). At the 500-board break that is $4.08 per part, or $8.17 per board against the survey's $19.64.
- R5 is stocked: JLC 1,380 and Newark 25,967.
- PS1, PS2 and U26 are covered by JLC's own stock for 500 boards.

## 2. Buildability metric (`scripts/buildability.py`, `scorecard-buildability.patch`)

**Tiers.** Each line is placed in a tier for N boards, where need = qty × N:
- **jlc:** a JLC library part with JLC stock ≥ need;
- **global:** one authorised, non-broker distributor holds the need, so JLC Global Sourcing can buy it;
- **consign:** the stock exists only split across sources or at brokers;
- **short:** no source holds it.

**Metrics.** Lower is better except the shares.

| Metric | Definition |
|---|---|
| `lines_short_for_N` | Tier is short or consign: no single source holds the need |
| `jlc_assemblable_share_N` | (jlc + global) / lines |
| `consign_lines_N` | Lines in the consign tier |
| `build_lead_wk_N` | Largest factory lead among the short lines |
| `short_lead_unknown_N` | Short lines with no known lead. They are listed, never counted as 0. |

**Checks**
- **Control:** a synthetic 5-line case, `--control`, passes.
- **Patch:** it applies cleanly (`git apply --check` from the unit directory).
- **Equivalence:** the patched `scorecard.buildability()` returns exactly the standalone values on this snapshot.
- **What the patch adds:**
  - a `--snapshot` argument, defaulting to the latest `sourcing/SNAPSHOT-*.csv`;
  - the metrics in `cost`;
  - the short-line, lead and share metrics in `compare()`'s cheaper and dearer lists.

**s32 values** (snapshot 2026-10-15; `results/buildability-s32.json`):

| Metric | 5 boards | 500 boards |
|---|---|---|
| lines_short_for | **3** | **14** |
| jlc_assemblable_share | **0.968** | **0.851** |
| consign_lines | 0 | 3 (KLDR025, B32676G1905, B32654A1104J) |
| build_lead_wk | **29** (L1) | **29** (L1) |
| short_lead_unknown | 2 | 6 |

**Short lines**
- **At 5 boards:** L1, plus two read gaps: DE1E3RA222MA4BP01F (JLC 6) and PMEG6030EP (JLC 7). No distributor was readable for those two.
- **At 500 boards:**
  - L1, CST3015-200ED, 1704004, IPW65R018CFD7, VOL628A-2X001T and R463N410050N1K (DigiKey 945 against 1,000);
  - read gaps: 6SVPC220MV, C0603C102J5GACTU, AC05000001507JAC00, PMEG6030EP and DE1E3RA222MA4BP01F.

The read gaps are short "as far as readable", not proven short. Re-take the snapshot when the distributor sites read again.

## 3. Alternates per problem line (ranked)

### C5/C6: DC-link film

**Repo stresses**
- Vbus worst no-clamp 451 V; static OVP 286 V (ledger).
- Worst C5 ripple 12.4 A at I_tank 22 A (ALT-C5C6 §4A), scaled linearly with I_tank.
- Bulk-path inductance basis ≈ 20 nH; die VDS rises ≈ 5 V/nH.

**Datasheet basis:** TDK B3267*D/G/J/T, 6/26, sha256 `9af4b662…`, https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32674_678.pdf.
- p.10: 37.5 mm ordering table (IRMS at 70 °C/10 kHz, ESR_typ, ESL). The ledger's "p.9" is the 300/450 V table.
- p.25: IRMS vs f, digitised.
- p.28: G per box.
- p.29: ΔT = ESR·I²/G against Factor²·20 K, with Factor 0.7 at 85 °C.

| Rank | Part | Kind | Fit | Rating margins | Ripple ΔT use 22 / 26 / 28 A at 85 °C | 28 A OK up to | Stock |
|---|---|---|---|---|---|---|---|
| 1 | **B32676G1106K** (10 µF / 750 V; "Z 1" at DigiKey, K000 at TTI/Mouser) | Drop-in (same 30×45×42 body, P 37.5 / 20.3) | Same footprint | 451/750 = 0.60 (≤ 0.8). ESL 13 nH (+1 nH per site, ≈ +0.5 nH path, ≈ +2.5 V die VDS) | 0.77 / 1.08 / 1.25 | 80.8 °C | **DigiKey 18,789 (Z 1, 18 wk, $6.58 at 1,000)**; TTI 900 (MOQ 100) + Mouser 91 for K000 |
| 2 | B32676G1126K000 (12 µF / 750 V) | Near-drop-in: same pins, 33×48×42 body | Height 48 mm against the ≤ 48.4 mm envelope; C 24 µF | 0.60; ESL 14 nH | **0.57 / 0.80 / 0.92** | 85 °C | No listing at DigiKey or Octopart. MOQ 360 (p.10); lead about 27 wk |
| 3 | B32676G8106K000 (10 µF / 875 V) | Near-drop-in, 33×48×42 | As 2 | 451/875 = 0.52; ESL 14 nH | 0.61 / 0.86 / 0.99 | 85 °C | DigiKey 7, Mouser 6; 27 wk |
| – | B32676G1905K000 (fitted) | – | – | 0.60 | **0.80 / 1.12 / 1.30** (control reproduces the repo's 0.80) | 80.1 °C | DigiKey 547; 27 wk |
| – | B32676G8755K000 (7.5 µF / 875 V) | Drop-in | – | – | 0.89 / 1.24 / 1.44 | 78 °C | DigiKey 0; rejected |
| D | 4 × KEMET R75PR415050H3J / R75PR4150AA30K, two per site (ALT-C5C6 option E) | Design-level: new P27.5 pads and a mains re-route at C5 | ECO | 630 V; 451/630 = 0.72 | ≈ 0.65 at 28 A (KEMET 20 K basis; repo 8 K at 22 A × (28/22)²) | – | DigiKey 583 + Newark 306 (J); DigiKey 1,494 + Arrow 1,408 (K) |

**C5/C6 ripple verdict** (`scripts/c5c6_ripple.py` → `results/c5c6_ripple.json`)
- **Vendor curve is flat.** TDK's permissible current is flat from 10 to 95 kHz, within −2.3 / +4.3 % (digitised p.25, control at 10 kHz within 0.6 A of the table). So ESR_typ at about 91 kHz equals the 10 kHz value, and the repo's 80 % at 22 A stands.
- **The ledger's extrapolations are confirmed:** 1.12 at 26 A and 1.30 at 28 A with an 85 °C cap ambient.
- **The fitted part carries 28 A on the vendor basis only with a cap ambient ≤ 80.1 °C.** At the existing bench condition (≤ 75 °C) use is 0.78.
- **No stocked part fixes 28 A at 85 °C.**
  - The drop-in B32676G1106K is only 4 % better (0.77 / 1.08 / 1.25), but it fixes stock and lead time.
  - Only the 33×48 bodies (G1126 0.92, G8106 0.99) pass at 85 °C. They are not stocked, and their 48 mm height consumes the envelope.
- **Open sensitivity.** 28 % of the HF ripple power sits above TDK's 95 kHz chart edge. With an assumed √f ESR rise there, the factor is ×1.38: 28 A at 75 °C would be ≈ 1.07, and G1126 at 85 °C 1.27.
- **Recommendation:**
  - Fit B32676G1106K, once TDK or DigiKey confirm that the "Z 1" suffix is the catalogue part. Its body and ratings are identical to the p.10 row except C, ESR and ESL.
  - Keep the bench gate for running above 22 A: cap ambient ≤ 75 °C **and** a C5 case-temperature measurement.
  - Pre-order G1126K000 only if the owner wants 28 A without an ambient condition. That needs an enclosure-fit re-run and a C-band (24 µF) re-validation.

### L1: common-mode choke

**Repo stress:** 15 A inlet cap; the 80 % rule needs I_R ≥ 18.75 A.

**Datasheet:** TDK B82726S22*3A020, May 2026, https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf. Ordering table p.4, derating p.5.

| Rank | Part | Kind | Margins | Stock |
|---|---|---|---|---|
| 1 | B82726S2243A020 (24 A, 0.75 mH, Lstray 8 µH, 3.2 mΩ; same series, same drawing p.3) | Drop-in footprint; **electrical change** | 15/24 = 0.63 (passes). CM L −53 %, DM leakage 18 → 8 µH: the c29 / D-22 EMI must be re-run (s19b needs ≥ 100 µH DM including the leakage) | Mouser 62, DigiKey 29: enough for 5-board lots only |
| 2 | TDK B82726E6203B041 (20 A, 2.7 mH, 600 V) | Near-drop-in: different housing (footprint not verified) | 15/20 = 0.75 at TR | DigiKey 169 |
| 3 | KEMET SC-20-201 (c29's cheaper variant) | Design-level (footprint and EMI) | 20 A class; not verified | DigiKey 57 |
| ✗ | B82726S2183N020 (18 A) | – | 15/18 = 0.83 fails the 80 % rule | – |
| ✗ | Same MPN at brokers (Fmall, TIST) | – | Unauthorised source for a SAFETY part | – |

**Plan:** pre-order B82726S2203A020 now (29 wk). For the 5-board prototype, either fit rank 1 with an EMI re-run or wait.

### Resonant bank (C21–C23, C151, C152)

**Method.** c34 was re-run from a copy (`c34-copy/`, VR pointed at the repo read-only). All four controls passed (exit 0), and today's bank reproduced at 1.045. `scripts/bank_stock.py` then joined the banks with ratio ≤ 0.85 to today's stock.

**Banks ≤ 0.85:**
- B32643B8104J (0.831), 6 × B8823J (0.764), 4 × B8124J + B8683J (0.814), 7 × B8683J (0.724);
- B32654A2104J (0.771), 7 × A2683J (0.727), 10 × A2473J (0.637);
- KEMET 10 × R76UR2470 (0.691), 8 × R76TR2680 (0.806).

**None of them is in authorised stock:**
- JLC: 0 or not listed;
- Newark: 0 for B32654A2104J and R76TR2680;
- no authorised offer at all for any B32643B8xxx part;
- only brokers hold stock: B32643B8104J000 27,690, B32654A2104J000 25,820, R76TR2680SE30J 14,480.
- Octopart blocked the reads of A2683J, A2473J and R76UR2470.

**Other vendors.** The other vendors in c34's exclusion list stay excluded: their datasheets publish no current rating at 35 kHz, or they fail on voltage or size. The stocked commodity 2 kV 100 nF part at JLC (KYET MMKP104J3F2701, P27.5, 1,400 in stock) publishes no current rating, so it cannot be scored.

**Fitted part B32654A1104J000:** 1,218 authorised and JLC units against 2,500 needed for 500 boards; 23 wk lead. The K variant (DigiKey 2,669) is stocked but worse (ratio 1.13).

**Plan:** decide between c34's B32643B8104J000 (28 wk, MOQ 2,080) and B32654A1104J000 now, since both leads exceed five months.

### Other problem lines

| Line | Ranked options |
|---|---|
| **D3/D17 30KPA150CA** | 1. **The same MPN and manufacturer (Good-Ark) at DigiKey: 1,750.** No family change, so DC-LINK-CLAMP is satisfied. 2. Littelfuse or MDE 30KPA150CA, same JEDEC P600 30 kW part: the manufacturer changes, so it needs owner approval. ✗ 5KP150CA: family change, 5 kW, forbidden. AK3-380C-Y / PTVS3-380C-TH: ECO (ALTERNATES-2026-10-09 §4). |
| **F1 KLDR025.TXP** | Same MPN, split buy: Future 300 (MOQ 10) + Standard 246 + Master 81 + Sager 50 = 692 ≥ 500. Consign it. No alternate needed. |
| **R5 CSS2H-2512R-1L00F** | Not short (JLC 1,380, Newark 25,967). The Bourns CSS2H-2512 datasheet table offers 1 mΩ only in the R alloy (1.0 mΩ / 5 W; "CSS2H-2512K-1L00F" does not exist), so there is no same-series alternate. |
| **PS1/PS2 IRM-20-15 / -24** | Not short (JLC 1,497 / 7,095). No change. |
| **U26 TPS7A4700RGWR** | Not short at JLC (998). Reserve it now: no authorised distributor stock is listed and the TI lead is 20 wk. TPS7A4701RGWR is a different ANY-OUT variant with no authorised stock; not recommended. |
| **U3/U37–U39 TPS70950DBVR** | Not short. TPS70950DBVT is the same die in small-reel packaging (DigiKey 1,703): a true drop-in. |
| **J2/J5 74650074** | 1. Keep: DigiKey 32,606 on 10-13 (stale), lead 26 wk. 2. **Candidate 35, WP-SMBU 7466004R: DigiKey 9,006 and Mouser 2,920 in stock** (need 1,000; $1.91 at 500). SMT footprint ECO; 50 A at 20 °C and 1.2 N·m per DECISIONS 42 (datasheet rev 001.003). It also removes the 1.6 mm board-thickness constraint. |
| **J6 1704004** | Short at 500 (153 across small distributors); 7 wk lead. No alternate verified. Pre-order. |
| **T1 CST3015-200ED** | JLC 64 covers the 5-board lot. For 500, Coilcraft direct only, lead unknown: the owner should get a Coilcraft quote. |

## 4. Pre-order plan for a 500-board JLC build

Today is 2026-10-15. **L1 at 29 weeks sets the earliest build, about 2027-05-06**, unless rank-1 L1 passes EMI.

**Mechanisms**
- **JLC/LCSC stock:** JLC "Parts Manager / order parts" to the private library reserves JLC/LCSC stock now.
- **Global Sourcing:** JLC buys from DigiKey, Mouser and others in 9–15 days.
- **Consign:** the owner buys and ships the parts to JLC.

| When | Order (qty includes ~4 % spares) | Why |
|---|---|---|
| **Now** | L1 B82726S2203A020 × 520 (distributor backorder; 29 wk) | Gates the build |
| Now | VOL628A-2X001T: reserve JLC's 172, backorder 350 (28 wk) | Short |
| Now | Bank: B32654A1104J000 × 2,600 (23 wk), or B32643B8104J000 × 2,600 if c34 is staged (28 wk, MOQ 2,080) | Short, long lead |
| Now | C5/C6: B32676G1106K "Z 1" × 1,040 at DigiKey (in stock) after TDK confirms the suffix; else B32676G1905K000 × 1,040 (27 wk) | Short, long lead |
| Now | 2EDR8259XXUMA1 × 1,040 (DigiKey 1,043 on 10-13, plus JLC 97; 39 wk if missed) | Long lead |
| Now | R463N410050N1K: DigiKey 945 + JLC 46, backorder the balance (24 wk) | Short |
| Now | 30KPA150CA (Good-Ark) × 1,040 at DigiKey (1,750, MOQ 250) | Was "zero"; stock is finite |
| Now | J2/J5: 74650074 × 1,040 (26 wk) or, if candidate 35 lands, 7466004R × 1,040 (in stock) | Long lead |
| Now | Reserve at JLC: TPS7A4700RGWR × 520 (998 in stock, 20 wk), IRM-20-15 × 520 (17 wk) | Single-source, long lead |
| Now | T1: request a CST3015-200ED quote from Coilcraft for 520 | Only source |
| By ≈ 2027-02 (≥ 12 wk before the build) | IPW65R018CFD7 × 2,080 (8 wk; DigiKey 459 on 10-13), 1704004 × 520 (7 wk), KLDR025.TXP × 520 split buy (5 wk), 3403.0279.23 × 520 (18 wk; buy now if DigiKey still shows its 7,183) | Short or split |
| At order time | Re-read DE1E3RA222MA4BP01F, PMEG6030EP, 6SVPC220MV, C0603C102J5GACTU, AC05000001507JAC00 | Read gaps today |

## 5. Files (all under this folder)

| Path | Contents |
|---|---|
| `README.md` | This write-up |
| `run_all.sh` | Re-runs everything |
| `scorecard-buildability.patch` | Unified diff against `native-21/layout/gates/scorecard.py`. `patch/a`, `patch/b` hold the before / after copies. |
| `snapshot/SNAPSHOT-2026-10-15.csv` and `.json` | The snapshot. Suggested repo path: `validation-results/08-manufacturing-package/native-21/sourcing/SNAPSHOT-2026-10-15.csv`, which is the patch's default glob. |
| `snapshot/jlc-2026-10-15.json`, `octopart-2026-10-15.json`, `digikey-2026-10-15.json`, `bom-jlcpcb.s32.csv`, `mpn-list.json` | Raw per-source reads and inputs |
| `scripts/jlc_fetch.py`, `jlc_snapshot.py`, `octopart_fetch.sh`, `octopart_parse.py`, `dk_extract_page.js`, `dk_browser_fetch.js`, `build_snapshot.py` | Snapshot scripts |
| `scripts/buildability.py` | Metric and control |
| `scripts/digitize_b32676_irms.py`, `c5c6_ripple.py` | C5/C6 ripple |
| `scripts/bank_stock.py` | Bank stock join |
| `scripts/extra_mpns.txt`, `octopart_mpns*.txt` | Input lists |
| `results/buildability-s32.json`, `b32676_irms_curves.json`, `c5c6_ripple.json`, `bank_stock.json` | Results |
| `c34-copy/` | c34 scripts and results re-run (one-line VR change) |
| `downloads/` | Vendor PDFs and Octopart pages: untrusted, not for the repo |

`dk_browser_fetch.js` was the first in-page attempt and hit HTTP 429; it is kept for the record.
