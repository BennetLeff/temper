# jlc-max-r1 (UI board): 100 % JLC assembly, and the sensor tab on the same panel

Scope study, 2026-11-25 (US Central); reads 2026-11-26 04:40–04:44Z. Unit: `zapote/ui-board` revision 2
(schematic, frozen netlist and BOM; **no layout**, so nothing here moves copper that exists). Lots 5 / 10 / 20 boards;
project rule: stock ≥ 2 × the need. **Nothing was ordered, carted, logged into, contacted or pushed; no build was run.**
Octopart pages were read through its public search (no bot check met; method copied from the power stage's
`11-candidates/jlc-max-r1/scripts/octopart_fetch.sh`).

## Bottom line

1. **SW1–SW3: keep the C&K KSC223G LFG and have JLC buy it through Global Sourcing.** JLC holds 0 (C2798957), but
   authorised distributors do: Mouser 7,910 (MOQ 1) and Newark 4,293 (MOQ 1) on Octopart at 04:41:09Z, against 120
   for 20 boards at 2 ×. No part, land or circuit change. Cost of the route: the $20 commodity-inspection fee per
   switch kind and 9–20 business days (JLC's Global Sourcing terms as read for the power board on 2026-10-18,
   `ps-unified: .../11-candidates/consign-r1/README.md`, not re-read here); JLC's review can refuse a part, and its
   supplier list is only visible when logged in.
2. **JLC-stocked fallback: C&K KSC323J LFG, C2798494, 135 in stock** (covers 2 × 20 boards = 120, just). Same KSC
   family (IP67, gold, 2 ± 0.4 N, 300,000 operations, 3.5 mm, −40…125 °C), but a **J-bend land instead of the
   gullwing land**, a hard actuator and a shorter travel (0.2 +0.3/−0 mm against 0.35 +0.3/−0.1). The land is free
   to change now because the board has no layout; the feel and travel go to the cap-stack force trace the owner's
   SPEC already requires. Its gullwing twin KSC323G LFG keeps today's land but is not at JLC (distributors: Onlinecomponents
   79,013, MOQ 500; Newark 7,470, MOQ 1). No other JLC-stocked part meets the gold-contact requirement.
3. **Everything else on the UI BOM is a JLC line;** TMP122AIDBVR is thin (17 at JLC: covers 5 boards, not 10).
   Pre-order the 17 for a 5-board lot; Global Sourcing for 10 or 20 (DigiKey 7,939 MOQ 1, Mouser 2,384). J3 (OLED
   socket) and J7 (XH) are THT that JLC hand-solders. With item 1 the UI board is 100 % JLC-assembled.
4. **The sensor tab should ride on the UI board's panel in one Standard PCBA order.** The tab (64 × 32 mm) is below
   Standard PCBA's 70 × 70 mm minimum single board, it is two-sided (TMAG5170 on the fascia face, J9 behind), and
   Economic PCBA is single-sided only, so it needs a panel anyway. Both come from one netlist (one BOM, unique
   designators), both are 1.6 mm FR-4. Proposed panel: the UI board plus two tabs to its right, mouse-bites, 5 mm
   rails: about 236 × 91 mm (≤ 250 × 250 mm). Estimated PCBA fee saving against two orders: about $31
   (§2.4), before the PCB "different designs" fee, which only JLC's calculator gives. Condition: one stack-up for both
   (the tab takes the UI board's layer count).

## 1. Tact switch SW1–SW3 (DECISIONS U27)

Requirements (U27, the owner's `UI-BOARD-REQUIREMENTS.md` and `SPEC.md` button table): gold contacts (closed-contact
current 0.282–0.35 mA must be ≥ the minimum load), force ≈ 2.25 ± 0.55 N at the switch (2–5 N at the cap with the
seal), travel to electrical actuation 0.35–0.65 mm at the cap, ≥ 100,000 cycles, sealed body, 6.2 × 6.2 mm with the
actuator top 3.5 mm above the board, rated above the 80 °C board limit, SMT.

The C&K catalogue page for the KSC series was read this time (LCSC copy, sha256 `ffbad9d7…`, `reads/datasheets.json`;
U32 recorded the KSC2 drawing as not obtained). It gives for KSC22x 2 ± 0.5 N, 500,000 operations (KSC221),
0.35 +0.3/−0.1 mm; gold contacts 0.1 mA / 20 mV minimum, 10 mA maximum, −40…125 °C; bounce ≤ 1 ms. The owner's
2.25 ± 0.55 N and 0.35 +0.25/−0.15 mm are from another revision of the drawing; they overlap.

| Rank | Part | LCSC / route | Stock (read UTC) | Covers 2× at 5/10/20 (30/60/120) | Land | Ratings vs requirement | Margin / feel | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | **C&K KSC223G LFG** (= Y31B13136FPLFG) | C2798957 at 0; **JLC Global Sourcing** | JLC 0 (04:40:17Z); Mouser 7,910 MOQ 1, Newark 4,293 MOQ 1, TTI Europe 6,000 MOQ 2,000 (Octopart 04:41:09Z) | yes via distributors | today's G land | is the requirement | none | **Use** ($20 inspection fee) |
| 2 | C&K KSC323J LFG | **C2798494** | 135 (04:40:15Z) | yes, 135 ≥ 120 just | **J-bend** land (catalogue p. B-52: span 6.8 mm vs 10 mm) | gold 0.1 mA min ✓, 2 ± 0.4 N ✓, 300,000 ops ✓, IP67 ✓, 3.5 mm ✓, −40…125 °C ✓ | hard actuator; travel 0.2–0.5 mm vs 0.25–0.65: feel and snap to the force trace | **JLC-native fallback**; land change at layout |
| 3 | C&K KSC323G LFG | not at JLC; Global Sourcing | Onlinecomponents 79,013 MOQ 500, Newark 7,470 MOQ 1 (04:41:24Z) | via distributors | today's G land | as rank 2 | as rank 2 | only if rank 1 is refused and the hard actuator is acceptable |
| — | C&K KSC341GLFS | C221734 | 1,389 | yes | G land | **silver**: 1 mA minimum > 0.35 mA wetting; 3 ± 0.75 N; −40…85 °C | fails gold / wetting | reject |
| — | Hroparts K2-1839SP/SQ, SAMZO, LCKELEC, SOFNG 6.2 × 6.2 | several, 100–1,900 | — | — | similar body | contact plating and drawings not given; mostly 4.3–15 mm actuators, −25…85 °C, 100,000 cycles | unknown | reject (no traceable data) |
| — | C&K PTS645, E-Switch TL3301, Alps SKHH, Panasonic EVQP | stocked | — | — | 6 × 6 or THT | unsealed, −20…70/85 °C or THT | — | reject |

Searched (all cached in `reads/`): KSC223G, KSC223G LFG, Y31B13136FPLFG, KSC221G/222G/241G/223J/321G/322G/323G/323J,
KSC2/KSC3/KSC4/KSC6/KSC7/KSC, "SMD-4P,6.2x6.2mm", "6.2x6.2mm IP67 Tactile", SKHH, SKQG, SKTA, SKSC, EVQP, EVPAA,
EVQ-P7, B3FS, B3SN, B3S-1000, TL3301, TL3315, TL3305, PTS526, PTS645, PTS810. KSC323G LFG and the gold KSC2 variants
have no JLC listing.

**Consequences of rank 2 (only if chosen):** footprint `Temper_UI:CK_KSC2_G_gullwing_6.2x6.2mm` → a J-bend land,
the BOM entry and its `lcsc_exception` (`tools/make_bom.py:69-70`), `TACT_MPN` (`tools/verify_ui.py:93`) and the
calcs' part note (`tools/ui_calcs.py:771`). Rank 1 changes only the BOM entry: it should carry C2798957 instead of the
`lcsc_exception`, so JLC's BOM step matches it and offers Global Sourcing (`verify_ui.py:698` then stops taking the
exception path).

## 2. Sensor tab on the UI board's panel

### 2.1 What the two boards are (both from the `UiBoard` netlist; no layout yet)

| | UI board | Sensor tab |
|---|---|---|
| Size | 170 × 81 mm (DECISIONS U17/U30) | 64 × 32 mm (U26) |
| Thickness / material | 1.6 mm FR-4 | 1.6 mm FR-4 (`tools/floorplan.py` TAB_T) |
| Layers, copper, finish, mask | not chosen (no layout) | not chosen |
| Placement sides | front (fascia) face: SW1–3, OLED socket J3, TMP122, buzzer; rear: J7, J8 and the rest (U17) | front face: U8 TMAG5170 and C16 (package top 0.68 mm from the fascia, so nothing taller); rear: J9 (SH, 2.9 mm+) and, by choice, U7, R24, R28 |
| THT | J3 (1 × 20 socket), J7 (XH 12) | none |
| Edge-critical parts | J8 SH side-entry at (56, 78), 8 mm in from u = 64 | J9 SH side-entry at (82, 53), 4 mm in from u = 78 |
| Holes | four Ø3.4 M3 (E1: 0.3 mm web at (−104, 60)), four Ø7 stud clearances | three M2.5 NPTH, no copper keep-out, insulating standoffs |

### 2.2 JLC rules that decide it (read 04:43–04:44Z, `reads/jlc-pages/`)

- Standard PCBA: single board 70 × 70 mm to 460 × 500 mm; panel 70 × 70 to 250 × 250 mm; single and double-sided;
  edge rails and fiducials necessary. Economic PCBA: 10 × 10 mm minimum but single-sided only.
- V-cut: copper ≥ 0.4 mm from the cut; zero spacing; straight cuts through the whole panel; minimum panel 70 × 70 mm;
  V-cut in one direction and routing in the other is allowed (1.6 or 2 mm spacing).
- Mouse-bites: copper ≥ 0.2 mm from non-bite edges; spacing 1.6 or 2 mm; serrated edges remain; for SMT at JLC:
  5 mm tooling edges, 2 mm tooling holes, 1 mm fiducials centred 3.85 mm from the panel edges; breakaway tab ≥ 5 mm
  wide with mouse-bites.
- Different designs: boards with different copper that can be separated (V-cut, milling, holes) count as different
  designs and incur a PCB fee from the online calculator; "if your order needs SMT, then the SMT panel will also be
  charged with different design fees".
- PCBA fees (page "Last updated on Oct 22, 2026"), Standard PCBA: setup $51.12 double-sided; panel $51.12 × (designs − 1)
  double-sided; stencil $16.42 double-sided; hand-soldering labour $3.58 per order; manual assembly $0.0164 per joint;
  SMT $0.0016 per joint; feeder loading $1.53 per part type; handling ≥ $14.93; large-size fee only above 650 cm².

### 2.3 Verdict and panel layout

**One panel, one Standard PCBA order: yes, cleanly, with conditions.**
- Layout: UI board at the left, two tabs stacked at the right (32 + 2 + 32 = 66 mm ≤ 81 mm), 2 mm routed gaps with
  mouse-bites, 5 mm rails top and bottom carrying three 1 mm fiducials per side (both sides are placed) and 2 mm
  tooling holes. Panel ≈ (170 + 2 + 64) × (81 + 2 × 5) = 236 × 91 mm, 215 cm². The second tab is a spare.
- Mouse-bites everywhere, not V-cut: a V-cut must run straight through the panel, and any horizontal cut between the
  tabs would cross the UI board. The tab and the UI board are located by their holes, not their edges, so the serrated
  edges do not matter; keep bites off the UI board's left edge near E1 (0.3 mm web).
- Conditions: (1) one stack-up for both: the tab takes whatever layer count, copper and finish the UI board's layout
  chooses; (2) J8 and J9 (side-entry SH) must not overhang a board edge or a bite: place each body ≥ 2 mm inside its
  outline; (3) same "top" side for both in the panel (choose the connector side as top, so the TMAG5170 face is the
  bottom pass for both boards).

### 2.4 Cost estimate (JLC published PCBA fees, §2.2; estimate, not a quote)

| | One panel (2 designs) | Two orders (UI single; tab as a 4-up panel, 1 design) |
|---|---|---|
| Setup (double-sided) | 51.12 | 51.12 + 51.12 |
| Different-design panel fee | 51.12 | — |
| Stencil | 16.42 | 16.42 + 16.42 |
| Hand-soldering labour (THT J3, J7) | 3.58 | 3.58 |
| Handling | ≥ 14.93 | ≥ 14.93 × 2 |
| **Sum of these** | **≈ 137** | **≈ 169** |

Joint and part costs are the same either way; shared part types (SRV05-4, SM10B, the 0603 passives) load feeders once
in the combined order ($1.53 per type). Not in the estimate: the PCB fabrication price and its "different designs"
fee (calculator only), Global Sourcing fees, shipping. The tab must be panelized (≥ 70 × 70 mm) in either case, so
it loses JLC's small-board special price in both.

### 2.5 Gates to rerun when the panel exists

KiCad DRC on the panel file (break-line copper clearance 0.2 mm for bites, 0.4 mm if any V-cut); JLC DFM on the
panel Gerbers; fiducials and tooling holes on both sides of the rails; the CPL in panel coordinates for both boards
(designators are already unique: one netlist) and JLC's 3D preview of both sides; `tools/floorplan.py` checks on the
unpanelized outlines (tab outline, holes, keep-outs unchanged); a fresh independent review of the panel, as for any
layout (project rule).

## 3. Other UI BOM lines (`ui_bom_scan.py` → `ui-bom-scan.json`)

22 lines; read 04:42Z; "was" = the BOM's 2026-10-12 figure.

| Line | Part / LCSC | Live (was) | Need 2× at 5/10/20 | Issue | Route |
|---|---|---|---|---|---|
| U2 | TMP122AIDBVR C2877606 | 17 (17) | 10 / 20 / 40 | short at 10 and 20 | **pre-order the 17** for 5 boards; Global Sourcing for 10/20 (DigiKey 7,939, Mouser 2,384, Arrow 2,416; Octopart 04:42:48Z). The JLC "TMP122AIDBVR-TUDI" (C55214282, 290) is another maker's copy: not counted |
| SW1–SW3 | KSC223G LFG (no LCSC on the BOM) | 0 | 30 / 60 / 120 | not a JLC line | §1 |
| U1 | MCP23S08-E/SO C152205 | 309 (1,048) | 10 / 20 / 40 | falling | fine; re-read at order |
| U8 | TMAG5170A1QDGKR C5220642 | 1,031 (4,342) | 10 / 20 / 40 | falling | fine; re-read at order |
| BZ1 | GSD9605YB-5V2800 C530415 | 752 (280) | 10 / 20 / 40 | — | fine |
| J3 | PM254V-11-20-H85 C46595982 | 2,328 | — | THT (manualWeld) | JLC hand-solders; height still open (E2) |
| J7 | B12B-XH-A C158027 | 5,734 | — | THT | JLC hand-solders |
| all others | basic passives, SRV05-4, gates, SH | ≥ 10,633 | — | — | JLC |

**Not on the BOM (no JLC PCBA route; none needs soldering):** the Newhaven NHD-3.12-25664UCW2 OLED (plugs into J3;
not listed at JLC) — if E2 ends with a soldered low-profile header instead of the socket, the OLED becomes an owner
solder job unless JLC can source it; the J8–J9 harness (SHR-10V-S housings, LCSC C398474 49,841, plus crimps;
a harness item); the XHP-12 jumper to the controller; the magnet; the tab's three non-magnetic standoffs.

## Change now vs defer (UI)

Change now: put C2798957 on the SW1–SW3 BOM line and mark it Global Sourcing (no copper exists, nothing else moves).
At the order: pre-order TMP122 (5 boards) or Global-Source it (10/20). At layout: one stack-up for UI and tab;
J8/J9 inside their outlines; build the 236 × 91 mm panel. Defer: KSC323J LFG (only if Global Sourcing is refused, and
after a force trace); E2 (OLED socket height) stays with the enclosure.

## Re-run

- `python3 -I jlc_fetch.py search "<kw>" | detail Cxxx` (cached in `reads/*.json.gz`; `--refresh` re-reads).
- `python3 -I ui_bom_scan.py` → `ui-bom-scan.json` (offline from the cache).
- `./octopart_fetch.sh octopart-mpns.txt` then `python3 -I octopart_parse.py reads/octopart octopart-offers.json`.
  The HTML pages (12 MB) are not committed; their sha256 are in `reads/octopart/_sha256.txt`, so the parse
  re-runs only after a re-fetch.
- JLC policy pages: tag-stripped text in `reads/jlc-pages/` with the HTML sha256 and fetch log.
