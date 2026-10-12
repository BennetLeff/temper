# Controller fab loose ends (2026-10-12)

Branch `fab/controller`, unit `zapote/controller`. Nothing here modifies the board, schematic or `fab/` outputs, and nothing was ordered, uploaded, logged into or sent. Three tasks, each with its own folder.

| Task | Folder | Verdict |
|---|---|---|
| 1. CPL rotation audit | [cpl-rotation/](cpl-rotation/) | 248 lines: **196 OK, 15 CORRECTED, 37 NEEDS-PREVIEW**. One 20-line SOT-23 family conflict needs JLC's preview before release. |
| 2. Consignment / sourcing sheet | [consignment/](consignment/) | 5 named parts plus 2 more found short today (R31 now 3 in stock, J13 BOM code mismatch). Datasheet-backed alternates exist for 4 of them; AD8436 and R39 need an owner decision. |
| 3. J4 drawing | [j4/](j4/) | The open item is the **Molex 43045-1600 sales drawing, still unread**. An interface drawing was produced; the Molex envelope remains [UNVERIFIED]. |

Rerun everything (from the worktree root; `python3 -I` needs the script's own folder, so run the scripts by path):

```sh
D=$(mktemp -d)                                   # fresh, empty download dir
curl -sL -o $D/cpl_rotations_db.csv https://raw.githubusercontent.com/matthewlai/JLCKicadTools/master/jlc_kicad_tools/cpl_rotations_db.csv
E=zapote/controller/evidence/fab-loose-ends
python3 -I $E/cpl-rotation/easyeda_pads.py --raw-dir $D/ee --fetch        # optional, network, slow (rate limited); easyeda_pads.json is committed
python3 -I $E/cpl-rotation/audit.py --db $D/cpl_rotations_db.csv          # audit.json audit.csv cpl-jlcpcb.proposed.csv
python3 -I $E/cpl-rotation/render_pngs.py                                 # png/ (needs matplotlib)
python3 -I $E/consignment/fetch_stock.py --extra C578725,C495329,C546857,C728584,C865488,C652841,C2861205,C4360543,C861587,C23112,C160315   # network
python3 -I $E/consignment/build_sheet.py                                  # consignment-sheet.csv/.md (offline)
python3 -I $E/j4/j4_drawing.py                                            # j4-interface.svg (offline)
```

---

## 1. CPL rotation audit

**Pass criterion.** Every one of the 248 placed lines in `fab/cpl-jlcpcb.csv` is classified OK, CORRECTED or NEEDS-PREVIEW with a stated basis; a proposed corrected CPL exists beside (never over) the fab file; every CORRECTED and NEEDS-PREVIEW line has a PNG with pin 1 marked; a 0603 no-op control and a known-offset SOT-23 control classify correctly.

**Method.** JLC places its library footprint at the CPL rotation, so the CPL must carry KiCad's rotation plus the offset between the two footprints. Two independent sources give that offset:

- **A, rotation-offset DB.** `cpl_rotations_db.csv` from matthewlai/JLCKicadTools (repo HEAD `500a9fff`, 2025-05-01; file sha256 `fce26b89...3542698`, 59 rules, downloaded 2026-10-12 into a scratch dir, not committed). Bouni's kicad-jlcpcb-tools keeps no static DB file in its repo any more (its `CORRECTIONS.md` only documents importing the same `Footprint pattern,Rotation,Offset X,Offset Y` format), so this is the DB that format comes from. First regex match on the KiCad footprint name; JLC rotation = KiCad rotation + offset.
- **B, geometry.** The public EasyEDA/LCSC footprint of each BOM LCSC part (pad number and position, `easyeda_pads.json`, 80 of 83 parts; C20571196, C2074586, C4260028 are not in EasyEDA) is rotated in 90 degree steps until its numbered pads land on the numbered pads of the KiCad footprint read from `pcb/controller.kicad_pcb`. That step is the offset JLC needs. The convention (offset added to the KiCad rotation, counter-clockwise) was validated by the 14 SOIC/TSSOP/SOT lines on which A and B independently agree on 270, which they could not do under the opposite sign.

Classification, in order:

1. Symmetric non-polar two-pad passive (R, C, L, no CP_/D_): **OK** when the pad axis is right (a 180 degree error is harmless). 192 lines.
2. A and B both available: agree gives OK (offset 0) or **CORRECTED** (offset applied); disagree gives **NEEDS-PREVIEW**.
3. One source only: offset 0 on a non-polar part is OK; anything else (non-zero offset, polarised part, THT line, no data) is **NEEDS-PREVIEW**. A non-zero single-source offset is never applied automatically.
4. Candidate rotations (rotation plus each source's offset) are listed for every NEEDS-PREVIEW line in `audit.csv`/`audit.json`, and the proposed CPL leaves those lines untouched.

**Sources.** KiCad board `zapote/controller/pcb/controller.kicad_pcb` (read-only); `fab/cpl-jlcpcb.csv` and `fab/bom-jlcpcb.csv`; JLCKicadTools DB above; EasyEDA product API `https://easyeda.com/api/products/<LCSC>/components`, fetched 2026-10-12 (footprint data (c) JLCEDA/EasyEDA Official Library, https://easyeda.com , https://lceda.cn ; only derived pad numbers and positions are committed, the raw JSON is not). The API rate-limits after about 20 requests, so the fetch backs off and resumes.

**Results.** Counts: OK 196, CORRECTED 15, NEEDS-PREVIEW 37 (`audit.json` `meta`). `cpl-jlcpcb.proposed.csv` differs from the fab CPL in exactly the 15 CORRECTED rotations (same CRLF format, checked by `diff`).

CORRECTED (A and B agree), proposed rotation replaces the CPL value:

| Ref | MPN | KiCad footprint | CPL rot | Offset | Proposed |
|---|---|---|---|---|---|
| U5 | OPA2388IDR | SOIC-8 | 0 | 270 | 270 |
| U6, U7 | TLV9062IDR | SOIC-8 | 0 | 270 | 270 |
| U15 | MCP3202-CI/SN | SOIC-8 | 0 | 270 | 270 |
| U8 | TCA9555PWR | TSSOP-24 | 0 | 270 | 270 |
| U9 | SN74LVC244APWR | TSSOP-20 | 0 | 270 | 270 |
| U20 | SN74LVC1G74DCUR | VSSOP-8 | 0 | 180 | 180 |
| U21 | TPS3823-33DBVR | SOT-23-5 | 0 | 270 | 270 |
| U36 | TLV9061IDBVR | SOT-23-5 | 0 | 270 | 270 |
| U22 | CD74HC30PWR | TSSOP-14 | 90 | 270 | 0 |
| U23, U24 | SN74LVC14ADR | SOIC-14 | 90 | 270 | 0 |
| U30 | MAX31865AAP+ | SSOP-20 | 90 | 270 | 0 |
| U38, U39 | SRV05-4 | SOT-23-6 | 0 | 270 | 270 |

NEEDS-PREVIEW (37 lines, PNG each in `cpl-rotation/png/`):

- **20 lines, SOT-23 / SOT-23-5 family conflict** (Q1, D4, U13, U16, U29, U10, U17, U18, U31, U32, U11, U25, U33, U37, U12, U19, U26, U27, U28 with geometry +180 against DB +270; U35 with geometry 0 against DB +270). The DB rule `^SOT-23` says +270; the EasyEDA footprint matches the KiCad pads at +180 exactly (see `png/U11_NEEDS-PREVIEW.png`: the geometry panel fits, the DB panel does not). They cannot both be what JLC's machine library does. This is the family to check first in JLC's placement preview, with candidates `rot+180` and `rot+270` listed per line.
- 11 lines single-source geometry non-zero (U1, U2 TPS62933 +180; U3 WSON-6 +270; U14 AD8436 QSOP-20 +270; THT connectors J1, J2, J3, J7, J12 +180, J4 +180, J11 +270).
- 5 polarised parts with geometry offset 0 only (C1, C9 electrolytic; D1, D2, D3 ESD5Z): pad-number polarity against JLC's marking needs one look in the preview.
- J13 (no EasyEDA footprint for C20571196, no DB rule).
- THT lines: JLC places THT by hand or wave, so the preview may not show them; use the silk pin-1 mark. J4's pad centroid is 10.5 mm from its footprint origin, so for THT the CPL Mid X/Y is the pin-1 origin, not the body centre.

Controls (`audit.json` `meta.controls`, both pass): C2 (CL10B103KB8NNNC, 0603) is OK with rotation unchanged and no DB rule; the four KiCad `SOT-23` lines (D4, Q1, U13, U16) all match `^SOT-23` with DB offset 270 and are not silently passed (NEEDS-PREVIEW because the geometry source disagrees).

**Verdict.** The 15 two-source corrections are the strongest findings: the current CPL carries raw KiCad rotations for these ICs and would very likely place them 90 or 180 degrees off. The proposed CPL is a proposal; verify in JLC's placement preview before use (JLC's preview is the final arbiter and `fab-notes.md` already says so). The 20-line SOT-23 conflict is unresolved here.

**Limitations.** Pad-number matching assumes EasyEDA and KiCad number pads like the datasheet; JLC's real machine library can differ from the public EasyEDA footprint (the SOT-23 conflict is exactly that, one of the two sources is wrong for JLC). 192 symmetric passives are OK on the rule, not individually checked (R39 and R53 have no EasyEDA footprint and rely on the rule alone). DB offsets X/Y were reported as zero; no position offsets were audited. No JLC preview was run (no account).

---

## 2. Consignment / sourcing sheet

**Pass criterion.** For a 2-board prototype lot plus spares, every BOM line has quantity, current JLC and LCSC stock with timestamp, the zero/low-stock parts have distributor stock/lead time (date and URL) where readable, JLC consignment steps are written out, and any alternate with JLC stock carries datasheet evidence of equivalence, proposed only.

**Method.** `fetch_stock.py` reads JLC's public parts-search endpoint (the one the parts page calls) and LCSC's public product-detail endpoint for all 83 BOM lines and the alternates, timestamp per read (`consignment/stock-snapshot.json`, 2026-10-12 16:36-16:39 UTC). Distributor stock was read with page fetches (curl, then an LLM page-extraction tool) and recorded by hand in `distributor_records.json`. Datasheets for the alternates were read in a scratch folder (sha256 in the sheet); none are committed. Quantity: per-board count x 2, plus 2 spares per line (10 % when the lot is 20 or more).

**Sources.** JLC and LCSC reads above; DigiKey search pages (2026-10-12); JLC help pages https://jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb (page dated 2026-09-09) and a search summary of https://jlcpcb.com/help/article/60-how-to-use-jlcpcb-global-sourcing-parts-service.

**Results** (full table in `consignment/consignment-sheet.md`/`.csv`):

| Part | Supply qty | JLC / LCSC stock now | Distributors (2026-10-12) | Alternate with JLC stock (proposed) |
|---|---|---|---|---|
| AD8436BRQZ (U14) | 4 | 0 / 0 (also 0 for BRQZ-R7) | DigiKey $28.28 qty 1 (stock not shown); an undated aggregator snapshot says about 75 DigiKey and 202 Mouser, stale-risk | **AD8436ARQZ-R7 C495329, JLC 106**: same QSOP-20 pinout and electrical table; accuracy 0.5 % vs 0.25 %, VOS +/-500 vs +/-250 uV (ADI Rev. E). Spec-degraded, owner decision, else consign B grade |
| TPS3703A4330DSERQ1 (U3) | 4 | 18 / 0 | DigiKey: 0 in stock, 26 weeks, 2,835 due 2026-11-30; non-Q1 A4330DSER 2,954 in stock | none needed (18 covers 4); contingency non-Q1 (JLC 0, consign) |
| ERA-3AEB1652V (R53) | 4 | 0 / 0 | DigiKey: 0, 49 weeks, 5,000 due 2026-11-05 | **RT0603BRD0716K5L C728584, JLC 18,103**: 0603, 0.1 %, +/-25 ppm, 0.1 W (ERA-3A and Yageo RT datasheets). Drop-in |
| RG2012V-431-W-T1 (R39) | 4 | 0 / 0 | DigiKey: 22 weeks, only a 3,000-piece reel at $3,712 shown | none equal: ten 0.05 % 430 Ohm 0805 parts all 0 at JLC. Degraded: RT0805BRD07430RL C865488 (0.1 %, 656). Owner decision |
| CD74HC30PWR (U22) | 4 | 2 / 2 (was 7 on 2026-10-08) | DigiKey $0.60 (stock not shown) | **74HC30PW,118 C546857, JLC 144**: identical TSSOP-14 pinout, 2-6 V (TI and Nexperia datasheets). Pin-compatible |
| RC0603FR-078K06L (R31) | 4 | **3** / 0 (was 163) | not looked up | RT0603BRD078K06L C861587 (2,718) or 0603WAF8061T5E C23112 (107,582); parametric text only |
| B2P-VH(LF)(SN) (J13) | 4 | BOM code C20571196 not found at JLC (LCSC 800) | n/a | same MPN is listed at JLC as C160315 (283,039): a BOM code fix, not an alternate |

JLC consignment steps (overseas shipper) are in the sheet: choose the shipping mode, ship to the Hong Kong warehouse address the system shows, enter courier and tracking, supply sales information and the HS code, JLC prices-reviews within 2 business days, pay duty/VAT deposits (VAT 13 %) plus a 2 % handling fee (minimum USD 10), ship, resolve any quantity discrepancy, download the contract. Alternative: JLC Global Sourcing (JLC buys from distributors, 9-15 days, payment final).

**Recommended route.** Order the lot on JLC stock after swapping R53 to C728584, U22 to C546857 and R31 to C861587; fix J13's LCSC code. TPS3703 Q1 (18) is enough for 4 pieces now. The two remaining blockers are U14 and R39: either accept the A-grade AD8436 and a 0.1 % R39 for the prototype, or consign (4 pieces each, about USD 113 for AD8436BRQZ at the DigiKey price). Consignment adds duty/VAT deposits, the 2 % fee, freight and a shipping delay; weigh that against the alternates.

**Verdict.** The DECISIONS item 7 list is confirmed and extended: R31 fell to 3 and CD74HC30PWR to 2 since 2026-10-08. Four parts have datasheet-backed JLC-stocked alternates; two need an owner decision.

**Limitations.** Distributor coverage is thin: Mouser (bot wall and timeouts), Farnell, Newark, RS, Arrow, Octopart and findchips refused or timed out; DigiKey search pages did not show stock for several parts. DigiKey figures come from an LLM page-extraction tool (secondary reading, re-check on the page before buying); the Mouser/DigiKey AD8436 stock is an undated aggregator figure and LCSC's own number contradicted that source. Lead times for JLC itself are not published per part. Whether JLC can globally source AD8436BRQZ needs an account. The accuracy effect of A-grade AD8436 and of 0.1 % R39 was not computed against the controller error budget.

---

## 3. J4 drawing

**Pass criterion.** Identify what is open about J4. If a specific item is defined, close or restate it with evidence; otherwise produce an interface drawing (connector MPN, pin map, mating housing and crimps, wire gauge, harness length, current and voltage, polarity marking) from a committed script.

**What is open.** A specific item is defined: `LAYOUT.md` open item 7 and `DECISIONS.md` C17 / `ENCLOSURE-HANDOFF.md`: *"J4 drawing: the 43045-1600 sales drawing could not be fetched (molex.com refuses this network). The mated height 10.29 mm is Molex's figure for the same series (43045-2001); the plug's -X overhang (R31: to X-50) is still unread"*. So "J4 drawing" means the Molex sales drawing, needed to check the header envelope and the plug overhang.

**What was done.** Re-tried on 2026-10-12: `molex.com` (both the `/pdm_docs/sd/430451600_sd.pdf` and the `content/dam/...` URL given by LCSC C277731) does not connect from curl and times out via a page-fetch tool; RS, Octopart and Heilind were 403 or empty. **The drawing is still unread; the item remains open.** A further finding: the repo's KiCad footprint cites `430450201_sd.pdf` (the 43045-0201 two-circuit drawing), not the 16-circuit sales drawing, so the footprint was not generated from the 1600 drawing either.

Because the drawing is unreachable, the interface drawing was produced: `j4/j4_drawing.py` writes `j4/j4-interface.svg`. It shows the 2x8 pad grid from the committed footprint (pin 1 square pad at the origin, rows 1-8 and 9-16, 3.00 mm pitch, two 3.0 mm peg holes), the full pin map with net, direction and level, the harness (Micro-Fit housing 43025-1600 at both ends, crimp 43030-0001 tin, 20-24 AWG, alternative 43030-0008 gold; AWG22 as in the README, at most 1 m; native-21 end is vertical 43045-1612), currents (15 V at about 0.32 A from 4.83 W; 0.85 A peak on three selv_gnd contacts; 49.4 mA of 3.3 V out; contact rating 8.5 A) and the pin 1 / keyed-shell polarity note.

**Sources.** `README.md` (pin obligations, power tree), `DECISIONS.md` C17, `ENCLOSURE-HANDOFF.md`, `pcb/libs/Connector_Molex.pretty/Molex_Micro-Fit_3.0_43045-1600_2x08_P3.00mm_Horizontal.kicad_mod`, LCSC C277731 product data (8.5 A, 600 V, tin, 16 pin), DigiKey search page for 43025-1600 read 2026-10-12 (housing 0430251600, 16 positions, 'Contacts Sold Separately'; related sockets 0430300001 and 0430300008 listed as 20-24 AWG).

**Verdict.** J4 interface drawing produced and reproducible; the Molex sales-drawing check is not closed.

**Limitations.** The enclosure harness list gives no harness length, only the README's 1 m / AWG22 allocation, so the drawing says so rather than a length. The crimp pairing 43030-0001 with 43025-1600 is from DigiKey's related-items listing, which itself says it does not state compatibility; confirm against Molex's application specification. Crimp tool, wire colours and the keyed-shell statement are general Micro-Fit facts, not read from the 1600 drawing. The body envelope, mated height 10.29 mm (series figure) and plug overhang stay [UNVERIFIED]. Someone with Molex access should download `430451600_sd.pdf` and fill the envelope into `layout/world.py` / the J4 courtyard check.
