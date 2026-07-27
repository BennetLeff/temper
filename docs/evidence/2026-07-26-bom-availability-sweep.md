# BOM Availability Sweep — Procurement Risk

**Date:** 2026-07-26. **Scope:** `docs/hardware/BOM.md` rev 1.5 (155 `elec/src` components + 6 chassis lines, ~182 distinct MPNs). **Method:** live web search + direct distributor/manufacturer page fetches (DigiKey, Mouser, TI, Murata, Littelfuse, TME), cross-checked against `elec/src/*.ato` and `elec/build/default.net`/`default.csv` for what MPN is actually specified. No BOM, `elec/`, or `pcb/` file was modified.

**Distributor figures are a snapshot taken 2026-07-26** — treat stock counts as indicative, not precise; they move daily.

---

## Headline

| | Count |
|---|---|
| Distinct MPNs in BOM (approx., per task brief) | ~182 |
| Distinct MPNs checked against a distributor/manufacturer source | **~38** (~21%) |
| Of those, real distributor/manufacturer evidence obtained | 33 |
| Of those, UNVERIFIED (no usable source found) | 5 |
| **Confirmed blockers** (cannot order the part as specified) | **3** |
| **Confirmed/likely risks** (EOL, thin stock, long lead, unresolved MPN) | **6** |
| Discrepancies resolved | 4 (2 requested + 2 found) |

Coverage is deliberately not proportional to line count: every Tier-1 active/module named in the task brief was checked (12/12), all but one Tier-2 safety-mains part (8/9, IEC inlet excluded as N/A — see Coverage), 2 of 3 Tier-3 long-lead items, and one commodity spot-check that turned out to be the single largest finding in this sweep (see Blocker #1).

---

## Blockers

Parts that cannot be ordered today as specified in the BOM.

| # | Ref(s) | MPN | Problem | Evidence |
|---|---|---|---|---|
| 1 | **16 refs** — `C_VCCI1`, `C_VDDA`, `C_VDDB` (§1.1), `C_OUT_HF`+`C_BOOT` (§2.1), `C_OUT_HF` (§2.3), `C_VCC1` (§3.1), `C_DEC_RTD` ×7 (§4.1), `C_WDT` (§5.3), `C_OVP_ADC` (§5.6) | `GRM188R71E104KA01D` | **Murata 100nF/0603/X7R decoupling cap — OBSOLETE, 0 stock.** DigiKey's own product page: Lifecycle Status "Obsolete," 0 units, no restock. This is the single most-instantiated part in the whole design (16 of 155 components share this one MPN, per BOM §10.1's own count). Every section that uses standard 100nF decoupling is affected. | Direct DigiKey product-page fetch, 2026-07-26 (`digikey.com/.../GRM188R71E104KA01D/587154`) |
| 2 | `C_X2` (§1.2) | `DE2E3KH221MA3B` | **MPN not found at any distributor searched, and the value looks wrong even if it exists.** Murata's DE2-series "221" suffix decodes to 220 pF by the same convention confirmed on a sibling part (`DE2B3SA221KA3BT02F` = 220 pF, Farnell). The BOM describes this ref as "0.22µF 20% X2 310V" = 220 nF — a 1000× mismatch. Murata's DE2 leaded safety-disc line tops out around 10 nF per its own product-line page; a 220 nF part in this family is not plausible on its face. Same failure signature as the already-known fictional `EKZE251ELL332MM40S` bus cap. | WebSearch (DigiKey/Mouser/Murata, no hit on exact string) + Murata PIM lookup (redirect resolved, page required JS, content not confirmable) + cross-check against `DE2B3SA221KA3BT02F` (220 pF, Farnell) and DE2-series range (Murata lineup page) |
| 3 | `F1` (§1.2) | `0034.3129` (Schurter) | **The fuse itself is real and stocked (DigiKey, $1.19, in stock), but it is a bare 16A/250V time-lag glass fuse *link*, not a "holder+fuse" assembly** as the BOM describes it ("AC Mains Fuse (holder+fuse) \| 5x20mm holder"). Schurter's `0034.xxxx` numbering is its FST fuse-link family; fuseholders are a separate part family/number. If a holder is genuinely needed and not separately specified anywhere in the 155-part count, the design is missing a mounting part for mains fusing. **Not fully confirmed** — Schurter's own FST-5x20 datasheet PDF could not be parsed for this exact line. | WebSearch (DigiKey/Future Electronics listings describe it as a fuse cartridge); WebFetch of Schurter FST_5x20 datasheet PDF returned no text match for this line item — **UNVERIFIED at the primary source**, treat as a flag to confirm, not a certainty |

---

## Risks

Orderable today, but not clean.

| Ref | MPN | Status | Evidence |
|---|---|---|---|
| `K_BYPASS` (§1.2) | `G4A-1A-E DC12` (Omron) | **Obsolete/EOL** — DigiKey: "no longer manufactured and will no longer be stocked once stock is depleted." 21,232 units still in stock now (last-time-buy inventory); DigiKey's own page names a manufacturer-suggested substitute, `G5PZ-1A-E DC12` (2,950 units). This is the mains bypass relay around the NTC inrush limiter — safety-adjacent, single-sourced, and its supply is finite. | Direct DigiKey product-page fetch, 2026-07-26 |
| `RV1` (§1.2) | `V150LA10AP` (Littelfuse) | **Conflicting signals, unresolved.** One aggregator snippet states "no longer manufactured / end-of-life," but DigiKey still lists 3,756 units in stock; the manufacturer's own product page returned HTTP 403 and could not be checked directly. **Marking UNVERIFIED rather than asserting EOL** — this is exactly the kind of claim the brief says not to guess on. Needs a direct Littelfuse or DigiKey lifecycle-field check before ordering. | WebSearch (conflicting); Littelfuse.com direct fetch blocked (403) |
| `C_BUS1/1B/2/2B` (§1.2) | `EKMQ251VSN182MA50S` (×4) | Active, DigiKey confirms exact MPN, but only **200 units in stock** with a **28-week manufacturer lead time**. Physically large snap-in electrolytics — BOM's own "Critical Long-Lead Items" table already flags this. Confirms rather than resolves that flag. | Direct DigiKey product-page fetch, 2026-07-26 |
| `U_RTD` (§4.1) | `MAX31865AAP+` | Active, in stock (DigiKey ships today; Mouser ~2,420 units) — but one aggregator reports a **19-week factory lead time** for restock. Not urgent while in-stock units last. | WebSearch (Mouser/DigiKey/Octopart) |
| `CT1` (§4.3) | `CST3015-100ED` (Coilcraft) | Part is real and matches the BOM's spec (1:100, 5000 Vrms, 88 A) per Coilcraft's own catalog page. **Distributor stock at DigiKey/Mouser not confirmed** — searches surfaced Coilcraft's datasheet and third-party brokers (Sourcengine, GlobalSpec) but no direct DigiKey/Mouser listing. This matches the BOM's own "Verify stock" flag in §Critical Long-Lead Items — this sweep did not resolve it. | WebSearch, no direct distributor hit |
| `U_OR1/U_OR2` (§5.2) | `SN74HC4075DR` (TI) | Exists in TI's datasheet family (D/DR/N package variants all documented), and the D-package (`SN74HC00DR`, same logic family, common NAND) is trivially in stock everywhere — but no search surfaced a live DigiKey/Mouser product page specifically for `SN74HC4075DR`, unlike every other TI part checked in this sweep. Triple 3-input OR is a much lower-volume part than quad-NAND. **UNVERIFIED stock/lead time** — 2 required per board. | WebSearch, repeated queries, no direct distributor product page surfaced |
| `C_TANK1/2` (§1.4) | `FKP1U021507E00JSSD` (WIMA) | 150 nF/1600 V is at the documented top edge of WIMA's FKP1 series range (0.1 nF–150 nF per WIMA's own datasheet). Exact 12-character order code not found at DigiKey/Mouser/WIMA in this sweep (nearest hits were adjacent codes at different values, e.g. a 47 nF sibling). Being at the extreme of a series' range is itself a lead-time risk even where the family is real. **UNVERIFIED at distributor level.** | WebSearch, no exact-string hit |
| `R_DIS1A/1B/2A/2B` (§1.3) | `AC05000004701JAC00` (Vishay, 4.7kΩ 5W wirewound) | Confirmed to exist with matching specs at TME (EU distributor); DigiKey/Mouser presence not independently confirmed in this sweep. | WebSearch (TME listing exact string; no DigiKey/Mouser hit) |

---

## Discrepancies

### 1. `MAX31865AAP+` vs `MAX31865ATP+` — resolved

Only `MAX31865AAP+` (SSOP-20) is live. Confirmed by grep of `elec/src/components.ato:358-361` (`mpn = "MAX31865AAP+"`) and `elec/build/default.net`/`default.csv` (both resolve to `MAX31865AAP` / SSOP-20 footprint). `MAX31865ATP+` (TQFN-20) does not appear as a line item anywhere in the current BOM — it exists only inside BOM.md's own prose note explaining the historical TQFN→SSOP footprint fix. Both strings are real, distinct, orderable Analog Devices/Maxim parts (confirmed `AAP+` Active, in stock at DigiKey and Mouser); the design needs `AAP+` only. No ambiguity remains.

### 2. `UCC21550BDW` vs `UCC21550BDWK` — resolved

Same pattern. `elec/src/components.ato:27-30` defines an atopile component **class** still literally named `UCC21550BDWK` (left over from before the fix) whose `mpn` field is explicitly `"UCC21550BDW"` with an inline comment: *"Fixed: was UCC21550BDWK (14-pin), now correct 16-pin DW package."* `elec/build/default.net`/`default.csv` confirm the emitted part is `UCC21550BDW` in all cases (`modules.ato:93` instantiates the class, but the class's `mpn` override is what reaches the netlist). `UCC21550BDWK` never appears as an ordered MPN — only as the stale class identifier and in BOM.md's own correction note. Confirmed `UCC21550BDW` Active, in stock (DigiKey ships today, Mouser has it too). No ambiguity remains.

### 3. `G5LE-1 DC12` vs `G5LE-1-E DC12` (Omron relays) — found, resolved

Not asked for, but adjacent to the Tier-2 relay check. `modules.ato:744,750` specify `G5LE-1 DC12` for `K_DIS1`/`K_DIS2` (§1.3), verified in-source against Omron datasheet K100-E1-08. `G5LE-1-E DC12` is a **different, real** Omron part (16A contact rating vs. `G5LE-1`'s 10A) that appears in the current BOM only inside the §1.2 note explaining that an earlier revision wrongly used it as `K_BYPASS`'s designator. No current line item specifies `G5LE-1-E`. Both parts independently confirmed to exist and stock at DigiKey. No ambiguity in the current BOM — flagging only because the task brief named `G5LE-1-E` as a part to check, and it is correctly *absent* from the live BOM, not present under a wrong designator.

### 4. `FKP1T021506B00` vs `FKP1U021507E00JSSD` (WIMA tank caps) — resolved on paper, unresolved in stock

BOM §1.4 already documents the correction: source uses `FKP1U021507E00JSSD`; the old `FKP1T021506B00` "(alt)" second-source line was dropped, not cross-checked, and correctly removed. That resolves the MPN question. It does not resolve procurability of the corrected part — see Risks table above; this sweep could not confirm `FKP1U021507E00JSSD` at a distributor.

---

## Confirmed real and orderable (spot checks, no issue found)

For completeness — these were checked and came back clean (Active, in stock, standard lead time unless noted):

| MPN | Ref | Note |
|---|---|---|
| `IKW40N120H3FKSA1` (Infineon) | Q1, Q2 | The bare `IKW40N120H3` string in the BOM is not itself the orderable SKU — DigiKey/distributors sell the suffixed variant (`FKSA1`, tube pack). Base device Active, 2,346 in stock. Minor MPN-precision note, not a supply risk. |
| `UCC21550BDW` | U_GD | Active, in stock both DigiKey and Mouser |
| `IRM-10-15` (Mean Well) | PS1 | Active, in stock both distributors, ships same/next day |
| `ESP32-S3-WROOM-1-N8R8` | U_MCU | Active, DigiKey ships today. (Note: task brief referenced "N4" — the BOM's actual, deliberate choice is N8R8; see BOM §3.1 correction note. Not a BOM defect.) |
| `LMR51430XDDCR` | U_BUCK | Active, thousands in stock at both distributors |
| `TLV3201AIDBVR` | U_OCP/U_OVP/U_THERMAL/U_THERMAL2/U_RTD_LOW_WIN/U_RTD_HIGH_WIN (6 instances) | Active, tens of thousands in stock |
| `TPS3823-33DBVR` | U_WDT | **Active** — confirmed directly via TI.com and DigiKey (25,280 units, 16-wk mfr lead time). One search snippet suggested "EOL" but that referred to a different package/temp variant in the family; direct-source check overturned it. Worth recording as a methodology note: aggregator snippets can attribute a sibling variant's status to the wrong part. |
| `SN74HC00DR` | U_NAND | Active, high volume, in stock |
| `SN74LVC1G08DBVR` / `SN74LVC1G38DBVR` | U_RTD_WIN_AND / U_RTD_FAULT_NAND | Real TI parts; `...1G08DBVR` showed **out-of-stock/backorder** at DigiKey at check time — worth a follow-up stock check closer to order time, not flagged as a structural risk here |
| `TPS3700DDCR` | U_RTD_RAIL_MON | Active, ships today |
| `NTCALUG01A104GA` (Vishay) | NTC_HS, NTC_COIL | Confirmed exists with matching 100kΩ/B4190 spec via Vishay's own datasheet; distributor stock not independently pulled |
| `SF152E` (NEC/Schott) | FUSE1 | Confirmed to exist with matching 157°C/10A/250V spec via multiple secondary sources; DigiKey/Mouser stock not confirmed directly in this sweep |
| `392-120AB` (Wakefield-Vette) | HS1 | Active, ships today |
| `MF60251V1-1000U-A99` (Sunon) | FAN1 | Active, ships today |
| `SP400-0.009-00-58` (Bergquist) | TIM_HV | Confirmed exists at DigiKey |
| `61300211121` (Würth) | J_FAN | Active, ~117k units at Mouser |
| `EVQ-P7A01P` (Panasonic) | BTN_RESET, BTN_BOOT | Active, in stock (design-side placeholder-footprint caveat already flagged in BOM §7.2 — unrelated to procurement) |
| `RC0603FR-0710KL` (Yageo, 10kΩ) | used ~15+ times across the design | Active, in stock — spot-checked as the second-most-common passive value after the obsolete 100nF cap above |
| `INA240A1QPWRQ1` (TI) | *not currently a BOM line* | Checked per task brief; real, Active, in stock. Correctly absent from the live BOM — removed per §4.4 pending the shunt-topology decision. No action needed. |

---

## Coverage and limits

**What was checked (38 distinct MPNs, ~21% of ~182):**
- All 12 Tier-1 actives/modules named in the task brief (IGBT, gate driver, CT, aux-supply module, MCU module, RTD IC, buck IC, comparator, watchdog, and the two logic families), plus 3 adjacent RTD-fault-chain ICs.
- 8 of 9 Tier-2 safety-mains parts (fuse, MOV, X2 cap, Y1 cap, CMC, both relay MPNs in the K_BYPASS/K_DIS confusion). The IEC inlet was not checked because it is not a component — the BOM already documents (§1.2 note) that no such part exists anywhere in `elec/src/*.ato`; this is a design-scope fact, not a procurement question.
- 2 of 3 Tier-3 long-lead items (bus caps, WIMA film cap). The "Coilcraft transformer" named in the brief does not exist as a separate part from `CT1`/`CST3015-100ED` (already covered) — there is no other Coilcraft component in this BOM.
- The one Tier-4 item with a self-evident no-orderable-identity problem (`L_TANK`) was not independently re-verified — the BOM (§1.4) and `docs/hardware/TANK_COIL_SPECIFICATION.md` already document, with source citations, that no inductance value exists in `elec/src/*.ato`. Re-deriving that finding would add nothing; it is carried forward as-is.
- A small, explicitly-labeled sample of commodity passives: 3 spot-checks (`GRM188R71E104KA01D`, `RC0603FR-0710KL`, `EVQ-P7A01P`), chosen to include the highest-multiplicity part in the design (16 instances) rather than a random draw — this is why the sample size is small but the finding yield was high.
- 4 chassis-BOM parts (§11): heatsink, fan, one TIM pad, one connector.

**What was not checked, and why:**
- **~144 of ~182 distinct MPNs** — the large majority of commodity resistors and capacitors (most of the Yageo `RC0603`/`RC1206` series values, most Murata `GRM`/`GCM` MLCC values other than the two spot-checked, all 7 distinct Panasonic `ERA` precision resistors in the RTD window chain, the zener diodes `BZT52C5V1-7-F`/`BZT52C3V3-7-F`, `SS14`, `MUR1560G`, `AO3400A`, `NTC_INRUSH SL32 10015`, `R_SHUNT`-class parts that are correctly absent from the BOM, and the mechanical hardware line in §11). These were excluded on the brief's own instruction to sample rather than exhaustively check commodity passives, and because the highest-consequence categories (actives, safety-mains, long-lead) consumed the available effort.
- The second TIM pad (`SP400-0.007-00-54`) and the mounting-hardware bucket in §11 were not checked individually — same category as the confirmed TIM pad above, lower marginal value.
- No purchase-portal quotes were pulled (no distributor account access); all figures are from public product pages and search snippets, dated 2026-07-26, and explicitly marked UNVERIFIED wherever a page could not be reached (Littelfuse.com 403, Murata PIM JS-rendered page, Schurter FST PDF text-search miss, Octopart 403).
- Every claim above cites the specific source consulted (direct fetch vs. search-snippet) so the confidence level is legible; where no reachable source existed, the finding is labeled UNVERIFIED rather than asserted.
