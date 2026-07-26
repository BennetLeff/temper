# BOM-vs-Source Audit — `docs/hardware/BOM.md` against `elec/src/*.ato`

Scope: every BOM line item compared against `elec/src/{components,modules,main}.ato`.
`elec/build/default.net` was checked for independent presence confirmation but is
**stale** — it has only 40 `libpart` entries and is missing `TLV3201`, `TPS3823`,
`SN74HC00`, `ES1J`, and the entire `SafetyInterlock`/`RTDSensing` subtree that
exist in current source. It was used only where it corroborated a source
finding, never as a contradiction of source. Source (`elec/src/*.ato`) is
ground truth per instructions.

## Headline counts

| Class | Count (BOM line items / source components) | Meaning |
|---|---|---|
| **A — in BOM, not in source** | **35 BOM lines** across 8 functional groups | costed, never wired |
| **B — in source, not in BOM** | **~75 source components** across 16 functional groups | wired, won't be ordered |
| **C — value/MPN disagree** | **16 items** | different part; materiality assessed per row |
| **D — consistent** | **6 spot-verified** (not exhaustive — see Limits) | — |

Class A alone is **35 of ~100 BOM line items (~35%)** — an order of magnitude
larger than the single `U_COMP2` case that triggered this audit.

---

## Safety-relevant subset (protection, isolation, HV stage, gate-drive) — read this first

| # | Finding | Class | Evidence | Severity |
|---|---|---|---|---|
| 1 | **Secondary OCP entirely absent**: `U_COMP2`/LM393DR (BOM:111), plus `R_SHUNT` (BOM:109) and `U_DIFF`/INA240 (BOM:110) — the whole OCP-02 signal chain | A | Zero hits for `LM393\|INA240\|SHUNT` in `elec/src/*.ato` | **Critical** — OCP-02 is a named gate (STRATEGY.md:57) |
| 2 | **IGBT desaturation protection entirely absent** — 19 BOM line items (D_DESAT_HS/LS, R_DESAT1, C_BLANK, R_DIV1/2, D_TVS, C_FILT, U_DESAT/LM393DR, R_REF1/2, R_PULL) BOM:145-163 | A | Zero hits for `DESAT` in `elec/src/*.ato` | **Critical** — DESAT is the primary IGBT short-circuit protection for the HV power stage; nothing replaces it |
| 3 | **Precision rectifier absent**: `U_RECT`/LM358DR + `D_RECT1-4`/1N4148WS (BOM:185-186), labelled "Precision Rectifier (OCP)" | A | Zero hits for `LM358\|1N4148` | High — feeds the (also-missing) redundant OCP path |
| 4 | **I2C isolator absent**: `U_ISO`/ADUM1250ARZ (BOM:95) | A | `components.ato:51-54` — comment: "ADUM1250 I2C isolator no longer needed... isolation barrier is between HV/SELV domains" (plan 003 superseded it) | Medium — isolation strategy moved elsewhere, but a part explicitly named for the isolation barrier is still costed |
| 5 | **Fault-indicator LEDs absent**: LED_OCP/OVP/THERMAL/WDT/MASTER + R_LED (BOM:196-201), 6 lines | A | `modules.ato:1783-1786` declares `ocp_led`/`ovp_led`/etc. signals; `modules.ato:1863` — *"LED indicators remain unassigned until their current-limiting circuits are specified"*. No `LED` component type exists in `components.ato` at all | High — operator-visible fault indication for a mains-connected appliance does not exist |
| 6 | **Fault-combining/reset logic ICs absent**: `U_AND`/74HC08D, `U_INV`/74HC04D (BOM:131-132) | A | Zero hits for `74HC08\|74HC04` anywhere in `elec/src/*.ato`; the actual latch (`modules.ato:1792-1856`) is built entirely from two `SN74HC4075` OR packages + one `SN74HC00` NAND package | High — named "Reset logic" / "Signal inversion" in BOM but the built latch uses none of it |
| 7 | **CT + burden resistor: different device, different ratio** | C | BOM:102-103 `CST-1005` (1:1000) + `R_BURDEN` 66.5Ω vs `modules.ato:1185-1194` `CST2010-100L` (1:100) + `r_burden` 6.65Ω — source comment explicitly frames 6.65Ω as "identical to the old 1:1000×66.5R design point," i.e. BOM was never updated after the CT swap | **Critical, material** — this is the OCP-01 sense path; STRATEGY.md's 37.6A trip calc used the *source* value, not the BOM's stale one. Ordering from the BOM gives a CT with 10× the wrong ratio |
| 8 | **OVP divider: different resistor network** | C | BOM:169-170 `R_OVP1-3`=1MΩ ×3 + `R_OVP4`=30kΩ (ratio ≈1/101) vs `modules.ato:1540-1562` `r_div_top1-3`=430kΩ ×3 + `r_div_bot`=10kΩ (ratio ≈1/130) | **Critical, material** — different trip voltage entirely; directly bears on the already-flagged OVP-01 ambiguity (STRATEGY.md:322-328), which never checked whether the BOM matched |
| 9 | **NTC thermistor: different R25 and beta** (already known) | C | BOM:176 `NCU18XH103F6SRB` (10kΩ, B=3950) vs `modules.ato:1655` `NTCALUG01A104GA` (100kΩ, B=4190K) | **Critical, material** — THM-01 |
| 10 | **Bootstrap diode: different device class entirely** | C | BOM:18 `UJ3D1210TS` (SiC Schottky, TO-220, 1200V/10A) vs `modules.ato:95` `ES1J` (600V/1A, SMA) | High, material — gate-drive/bootstrap path; wrong footprint, wrong current rating for the boot-cap recharge pulse |
| 11 | **Bleeder resistors: 4.5× value mismatch** | C | BOM:31 `100kΩ 2W` vs `modules.ato:549-561` `r_bleed1`/`r_bleed2` = 22kΩ 2W (`CRGP2512F22K`) | High, material — this is the passive backstop for HV bus discharge; source's own τ=79s safety comment (`modules.ato:701`) assumes 22kΩ. Building to the BOM's 100kΩ nearly quintuples the passive discharge time |
| 12 | **Bus capacitors: BOM part doesn't exist; quantity differs** | C | BOM:30 `EKZE251ELL332MM40S` 3300µF/250V ×2 vs `modules.ato:520-547` `EKMQ251VSN182MA50S` 1800µF/250V ×4 — source comment: *"replace the fictional 3300uF/250V EKZE part"* | High, material — bulk HV energy storage; also feeds the BusDischarge τ calculation |
| 13 | **Bus discharge (fail-safe active discharge) entirely unlisted** | B | `modules.ato:691-937` — `BusDischarge` module: 2×`Relay_SPDT` (G5LE-1 DC12), 4×4.7kΩ/5W, 2×coil droppers, MOSFET driver, 2× flyback diodes, 2× RC snubbers — 16 parts, zero BOM lines | Critical — this is the sole fail-safe mechanism for discharging lethal stored bus energy on power loss; none of it is costed |
| 14 | **Bypass relay MPN mismatch, and it collides with the (unlisted) discharge relays** | C | BOM:33 `K_BYPASS`=`G5LE-1-E` (Omron) vs `modules.ato:479-483` `bypass_relay.mpn = "G4A-1A-E DC12"`. The BOM's `G5LE-1-E` actually MPN-matches `k_dis1`/`k_dis2` (`modules.ato:743,749`, "G5LE-1 DC12") — the *discharge* relays from finding #13, not the bypass relay | High — BOM appears to describe the wrong relay under the bypass designator while the real bypass-relay part is absent |
| 15 | **Isolated auxiliary 15V supply entirely unlisted** | B | `modules.ato:1074-1138` — `AuxSupply` module: Mean Well `IRM-10-15` + 3 caps. This module provides the galvanic isolation between HV and SELV domains (`components.ato:66-68`, `RTDSensing` docstring `modules.ato:1238-1244`) | High — the part that *is* the isolation barrier has zero BOM entry |
| 16 | **RTD hardware-window fault chain (UVL-02 candidate) entirely unlisted** | B | `modules.ato:1268-1482`: `REF2025` reference, 2× additional `TLV3201` (window comparators), `TPS3700` rail monitor, `SN74LVC1G08` AND, `SN74LVC1G38` NAND, ~15 resistors/caps — ~25 parts | High — this is the exact circuit STRATEGY.md:330-333 identifies as the UVL-02 candidate; it does not appear in the BOM at all |
| 17 | **TLV3201 quantity: BOM costs 3, source uses 5** | C/B | BOM 5.1 lists 3× TLV3201 (U_OCP/U_OVP/U_THERMAL); source instantiates 5 (`grep -c "new TLV3201" modules.ato` = 5) — the 2 extra are the RTD window comparators in #16 | High — same root cause as #16 |
| 18 | **Fault-OR gate quantity: BOM costs 1, source uses 2** | C | BOM:129 `U_OR` qty 1; source has `fault_or` **and** `fault_any_or`, both `SN74HC4075` (`modules.ato:1792-1793`) | High — second OR package (RTD-fault-any aggregation) not accounted for |

---

## Class A table (in BOM, not in source) — 35 lines total

| BOM lines | Part(s) | Claimed function | Evidence of absence | Severity |
|---|---|---|---|---|
| 109-111 | R_SHUNT, U_DIFF, U_COMP2 | Redundant DC-bus-shunt OCP | no `SHUNT\|INA240\|LM393` in source | Critical |
| 145-163 (19 lines) | DESAT diodes/dividers/comparator/pull-ups | IGBT desaturation protection | no `DESAT` in source | Critical |
| 185-186 | U_RECT, D_RECT1-4 | Precision rectifier for OCP | no `LM358\|1N4148` in source | High |
| 95 | U_ISO (ADUM1250ARZ) | I2C isolation | `components.ato:51-54`, explicitly superseded | Medium |
| 196-201 (6 lines) | LED_OCP/OVP/THERMAL/WDT/MASTER, R_LED | Fault indication | `modules.ato:1863` "remain unassigned"; no LED component type exists | High |
| 129/131-132 (2 of 4 logic-IC lines) | U_AND (74HC08D), U_INV (74HC04D) | Reset logic / signal inversion | zero hits in source; latch built from OR+NAND only | High |
| 224-225 | R_AA, C_AA | ADC anti-aliasing filter | no `1.6nF` / no dedicated AA filter on any of the 3 ADC lines in `MCU` module | Low-Medium |

---

## Class B table (in source, not in BOM) — grouped, ~75 components

| Source module | `file:line` | Why it matters | Severity |
|---|---|---|---|
| `BusDischarge` (16 parts: 2 relays, resistors, snubbers, driver) | `modules.ato:691-937` | Sole fail-safe HV-bus discharge path | **Critical** |
| `AuxSupply` (IRM-10-15 + 3 caps) | `modules.ato:1074-1138` | The physical isolation barrier | **Critical** |
| RTD hardware-window chain (~25 parts: REF2025, 2×TLV3201, TPS3700, 2 logic gates, resistors) | `modules.ato:1268-1482` | UVL-02 candidate circuit | High |
| Second `SN74HC4075` (fault_any_or) | `modules.ato:1793` | RTD-fault aggregation, safety logic | High |
| AC mains fuse (F, "0034.3129", 16A/250V) | `modules.ato:442-447` | Primary AC overcurrent protection | High |
| MOV surge suppressor (V150LA10AP) | `modules.ato:452-455` | Mains surge protection | Medium |
| Y1 PE-bonding cap (`y_cap_pe`) | `modules.ato:637-642` | IEC 60335-1 Y1-rated safety cap | Medium |
| X2 EMI cap (`c_x2`) | `modules.ato:458-463` | Mains EMI filtering | Low |
| DC-bus HF film cap (`c_dc_hf`, 470nF/630V) | `modules.ato:323-328` | HV bus decoupling at the bridge | Medium |
| Dead-time resistor (`dt_res`, 34kΩ) | `modules.ato:267-272` | Sets gate-drive dead time | Medium |
| Gate-driver bypass caps ×4, EMI filter R/C ×4, neg-bias zener | `modules.ato:101-152, 284-320` | Gate-drive path decoupling/filtering | Medium |
| Bypass-relay driver (MOSFET, dropper, flyback diode, gate R's — 5 parts) | `modules.ato:486-514` | Relay drive circuit for K_BYPASS | Low |
| ZCD divider + clamp (4 parts) | `modules.ato:649-673` | Zero-crossing soft-start timing | Low |
| CT bias network (`r_bias_top/bot`) | `modules.ato:1218-1226` | CT output biasing | Low |
| OCP/Thermal internal divider resistors not itemized (~9 parts) | `modules.ato:1505-1513, 1661-1699, 1601-1619` | Sets actual trip thresholds for OCP-01/THM-01/OVP-01 ADC tap | High — these ARE the threshold-setting components |
| Fan header + dropper, MCU EN/BOOT RC + boot button (6 parts) | `modules.ato:1158-1174, 1922-1964` | Non-safety support passives | Low |

---

## Class C table (value/MPN disagree)

| Item | BOM value | Source value | Electrically material? | Severity |
|---|---|---|---|---|
| CT + burden (BOM:102-103 vs `modules.ato:1185-1194`) | CST-1005, 1:1000, R_BURDEN 66.5Ω | CST2010-100L, 1:100, r_burden 6.65Ω | **Yes** — different ratio decade | Critical |
| OVP divider (BOM:169-170 vs `modules.ato:1540-1562`) | 1MΩ×3 + 30kΩ | 430kΩ×3 + 10kΩ | **Yes** — different trip ratio | Critical |
| NTC thermistor (BOM:176 vs `modules.ato:1655`) | 10kΩ, B=3950 | 100kΩ, B=4190K | **Yes** | Critical |
| Bootstrap diode (BOM:18 vs `modules.ato:95`) | UJ3D1210TS, SiC, TO-220, 1200V/10A | ES1J, 600V/1A, SMA | **Yes** — different technology/package/rating | High |
| Bleeder resistors (BOM:31 vs `modules.ato:549-561`) | 100kΩ | 22kΩ | **Yes** — 4.5× discharge time-constant change | High |
| Bus capacitors (BOM:30 vs `modules.ato:520-547`) | EKZE251ELL332MM40S, 3300µF ×2 | EKMQ251VSN182MA50S, 1800µF ×4 (BOM part flagged "fictional" in source comment) | **Yes** — BOM part unbuildable | High |
| Bypass relay (BOM:33 vs `modules.ato:479-483`) | G5LE-1-E | G4A-1A-E DC12 | **Yes** — different relay series/current class | High |
| Common-mode choke (BOM:28 vs `components.ato:172-201`) | B82725S2183N040, 2×4.7mH, 18A | B82726S2163N030, 2.2mH/winding, 16A | **Yes** — ~2× inductance, different current rating | Medium |
| ESP32 module variant (BOM:75 vs `components.ato:489`) | ESP32-S3-WROOM-1-N4 (4MB flash, no PSRAM) | ESP32-S3-WROOM-1-N8R8 (8MB flash+8MB PSRAM) | Cost/lead-time material, not electrical | Medium |
| Gate driver MPN (BOM:17 vs `components.ato:30`) | UCC21550BDWK | UCC21550BDW — source comment says BDWK was a wrong 14-pin part, now fixed to 16-pin DW | **Yes**, per source's own annotation | Medium |
| Buck converter section header/values (BOM:47-57 vs `modules.ato:940-1051`) | Section titled "24V/12V→5V"; C_IN 2.2µF/100V; L_BUCK SRP1038A 6.8µH; R_FB2 32.4kΩ | Circuit is 15V→**3.3V** (`power_out.voltage = 3.3V`, `modules.ato:958`); c_in 10µF/25V; l_out SRP1265A 5.6µH; r_fb_bot 22.1kΩ | **Yes** — BOM describes a different converter (wrong output voltage) | Medium-High |
| RTD MPN/package (BOM:87 vs `components.ato:315`) | MAX31865ATP+ (TQFN-20) | MAX31865AAP+ (SSOP-20) — source comment: deliberate TQFN→SSOP fix | Package/footprint material, value/function same | Medium |
| RTD channel count (BOM:87-89 vs `main.ato:135`) | qty 2 (U_RTD1, U_RTD2) | 1 `RTDSensing` instance wired (`rtd_pan` only) | **Yes** — implies a second channel that doesn't exist | Medium |
| I2C pull-up quantity (BOM:96 vs `modules.ato:1967-1979`) | qty 4 (2 per side of isolator) | qty 2 (isolator removed, single side) | Consistent with #4/A finding above | Low |
| PWM filter cap (BOM:216 vs `modules.ato:114-124`) | 33pF | 220pF (resistor value 51Ω matches exactly) | **Yes** — 6.7× value change on gate-drive-adjacent EMI filter | Medium |
| Fan (BOM:255 vs `modules.ato:1143`) | Noctua NF-A8 PWM, 80mm | Sunon MF60251V1-1000U-A99, 60mm, non-PWM (series-dropper controlled) | Yes — different part, no PWM conductor in source | Low-Medium |

---

## Class D — count only

6 line items spot-verified as consistent by both value and MPN: IGBT base part
(Q1/Q2, `components.ato:12` vs BOM:16 — package suffix differs, base die
matches), `C_BOOT` (`modules.ato:147` vs BOM:19, exact MPN), `RG_ON`
(`modules.ato:160` vs BOM:20, exact MPN), `RGS` (`modules.ato:166` vs BOM:21,
exact MPN), rectifier diodes D1/D2 (`modules.ato:517-518`, MUR1560 base part vs
BOM:29 MUR1560, "G" suffix only), watchdog IC (`components.ato:417` vs BOM:138,
exact MPN match TPS3823-33DBVR). Not exhaustive — see Limits.

---

## Method and limits

- Ground truth was `elec/src/*.ato`, read in full (main.ato, modules.ato,
  components.ato — 2,020 + 450 + 613 lines). `elec/build/default.net` was
  cross-checked but found stale/incomplete (missing entire safety-interlock
  subtree) and was **not** used to assert absence, only to corroborate.
- Reference-designator matching was by function + MPN, not by name, per
  instructions (e.g. `K_BYPASS`↔two different physical relays in source).
  Matches flagged "inferring" above are explicitly marked.
- **UNRESOLVED**: BOM's 5 test points (TP1-5, BOM:242-246) vs source's 2
  `TestPoint` instances (`modules.ato:1858,1860`) — `TestPoint.bom_exclude =
  true` (`components.ato:611`) suggests test points aren't meant to be
  BOM-tracked the same way as parts, so I did not classify this as A/B/C.
- **UNRESOLVED**: General decoupling buckets (BOM 10.1, `C_DEC` qty 20 /
  `C_BULK` qty 5) were not reconciled item-by-item against the ~30+ scattered
  100nF/10µF instances in source; both plausibly cover the same population
  but I did not do the count.
- **Not reached**: Section 1.3 alt tank caps, Section 7.2 controls beyond
  S_RESET/btn_reset function match (inferred, not confirmed by net name), and
  a full line-by-line reconciliation of every 0603 resistor value against its
  BOM row (~40 individual resistor/cap lines were read in source but not all
  cross-referenced back to an exact BOM row match/mismatch verdict).
- Given the volume of findings, Class A/B tables aggregate related line items
  into functional groups rather than listing all ~110 individual rows;
  counts are stated where aggregated.
