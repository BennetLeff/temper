# s32: JLC-soldered Q2 / Q3 / Q5 / Q6 on the R45 M11 stack (OPEN-ITEMS S32)

Study, 2026-11-25, on `claude/native21-s55-unified` (s57 board of record). Nothing was ordered, built, contacted or pushed. The board, Gerbers,
BOM and the `hardware/native21-stage15b/` tree are untouched.

Run: `python3 -I s32_calc.py` from this folder. It writes `s32-calc.json` and prints every number below. It imports the committed models
read-only: `owner-items/m11/stack_calc.py`, `bench-sink-r1/scripts/bench_{params,mech,tolerance,thermal}.py`, `tools/write_rules.py`, and
`c60-seating-fixture/seat-tolerance.json`. Its controls reproduce the M11 baseline (0.399–0.634 °C/W conservative, `stack-calc.json`), the bench's
2.2 mm shim stack (0.953 °C/W, `thermal.json`) and the bench spreads (`tolerance.json`). EST marks an estimate. **Bound** is used only for a figure
whose dropped terms are all ≥ 0.

## The question and the budget

- **S32 (OPEN-ITEMS):** before a JLC-soldered board goes onto R45's M11 AlN tiles, evaluate (a) per-FET shims narrower than the 16 mm tab against
  `R_cs` and tab-to-tab creepage and clearance, (b) a compliant interface, and (c) fixture-soldered boards.
- **D-36** (DECISIONS 2026-10-06): "Fan ≈ 30 CFM at ≈ 140 Pa and **MOSFET interface ≤ 0.7 °C/W**". `R_cs` is the insulator plus both contacts
  (M11 RECOMMENDATION §3).
- **Grease bases** (from `stack_calc.py`; both are used for every row):

  | Basis | Value per interface | Source | Per TO-247 interface |
  |---|---|---|---|
  | Optimistic | 0.06 °C·cm²/W | DOWSIL TC-5622 TDS | — |
  | Conservative | 0.413 °C·cm²/W | TIC 1000A proxy | 0.172–0.273 °C/W |

  M11 claims its 0.066 °C/W margin on the conservative basis, so the conservative basis is the worst case here.
- **Spread to absorb** (`bench_tolerance.spreads()`, stage-57 1.8 mm holes, DECISIONS 87 / 89):

  | Case | Lot A1 | Datasheet A1 |
  |---|---|---|
  | U (remark not honoured) | 1.800 mm | 2.100 mm |
  | R (remark honoured) | 0.270 mm | 0.570 mm |

  The thickest design shim is 2.2 mm.

## Tab nets and insulation rules

| Device | Tab net | Neighbour, pitch | Tab-metal gap, centred (E1 max 14.15) | Worst, with x play (± 0.54 per device) |
|---|---|---|---|---|
| Q5 (HS, leg B) | `bus_p` | Q6, 18.0 mm | 3.850 mm | **2.770 mm** (corner-limited play 2.808) |
| Q6 (LS, leg B) | `sw_b` | Q3, 22.1 mm | 7.950 | 6.870 |
| Q3 (LS, leg A) | `sw_a` | Q2, 18.0 mm | 3.850 | **2.770** (2.808) |
| Q2 (HS, leg A) | `bus_p` | BR1 (plastic back) | — | — |

- **Tab to tab:** these are different HOT groups (`tools/write_rules.py` HOT_GROUPS). They are functional insulation, at **3.2 mm**:
  `FUNCTIONAL_CREEPAGE_MM`, IEC 60335-1 Table 18, PD3, > 125–250 V.
  - Clearance is no tighter. The bench's basic clearance is 1.3 mm.
  - Table 18 note 2 ("ceramics … need not be greater than the associated clearance") is **not** claimed. The path runs along the grease-filled
    joint between the package's mould compound and the tile, so one face is organic.
- **HOT to PE:** reinforced. Creepage 8.0 mm, clearance 2.0 mm, solid 2.0 mm AlN by cl. 29.3.1 (M11 RECOMMENDATION §2 and §4.1). The bench's
  `insulation.md` applied the basic floor instead (4.0 / 1.3 mm, 1250 Vac), which is the bench's own floor and not the enclosure's.

**Finding that predates S32 and applies to every option, including today's M11 baseline and the fixture route.** At Q5|Q6 and Q3|Q2 the tab-metal
gap on the shared tile is 3.850 mm with the parts centred. With the repo's x-play bound (`FET_POS_TOL` 0.465 + hole position 0.075 per device) it
falls to **2.770 mm, against 3.2 mm**.
- No gate measures this: the 3.2 mm DRC rule sees the lead pads, not tab metal above the board.
- It closes if the lot's **E1 ≤ 13.720 mm** (datasheet 12.38–14.15).
- Otherwise it needs cl. 29.2.4's clause-19 route, the certifier's view on note 2, or a barrier. On the cl. 29.2.4 route: a Q5–Q6 tab short is a
  Q5 drain–source short, and a Q3–Q2 tab short is a Q2 drain–source short.
- Shims do not change it, as long as they stay inside the tab metal (below).

## Verdicts

Margins are against 0.7 °C/W at the worst corner: smallest tab (151.2 mm²), 2.2 mm shim, conservative grease, unless stated.

| Option | `R_cs`, worst corner | Margin to 0.7 | Insulation | Verdict |
|---|---|---|---|---|
| **(a1)** HOT-side shim (Al or Cu) between tab and the **shared** tile, ≤ 11.38 × 12.08 mm, inside the tab metal | Al: 1.187 (1-D), bound 0.756. Cu: 1.127 (1-D), bound 0.696. Optimistic grease: Al 0.351, Cu 0.292 | **−0.487 / −0.427** conservative; **+0.349 / +0.408** optimistic | PASS: no tab-to-tab or HOT→PE distance shortens; the shared-tile finding above stays | **Needs measurement.** FAIL on the repo's conservative D-36 basis (a bound for Al 2.2 mm), PASS on the TDS basis. Comb and sink float need changes (below) |
| **(a2)** own tile per FET, PE-side shim behind it | 1.308 (1-D; 1.456 with x play). Optimistic 0.405 | −0.608 / +0.295 | Joint creepage needs pedestal reliefs. These cost 2.65 mm (3.73 mm with x play) of tab width at each 2 mm joint, and Q2 loses 3.75 mm (4.83 mm) | **FAIL (1-D, conservative)**, and dominated by (a1). It also needs five tiles instead of two. Not pursued |
| **(b)** compliant layer (gap pad, dispensed filler) replacing the tab-side grease | U spreads: gap alone ≥ 2.778 (k 5 W/mK; large tab ≥ 1.749), **bound** | −2.08 (−1.05 at the large tab) | AlN is still the reinforced insulator (29.3.1). The layer is not credited, must be non-conductive, and must stay off the tile overhang | **FAIL (bound)** for U spreads, unless k ≥ 19.8 W/mK at the small tab (12.5 at the large) with every other layer free. Best compliant k in the repo's sources: 5 W/mK. R spreads: **needs measurement** (k ≥ 3.1–11.1 W/mK small tab, per basis) |
| **(c)** c60 two-pass seating fixture (owner-soldered) | Baseline 0.634 | **+0.066** conservative | Baseline M11 | **Needs measurement:** worst lead corner −0.072 mm against +0.155 mm needed; typical lead +0.233. Not JLC-soldered |

The table uses three geometries for `R_cs`:
- **1-D** is the repo convention (`stack_calc.py`, no spreading credit).
- **Bound** keeps only the tab-side greased faces and the shim bulk over the shim area; the AlN and the PE-side grease are dropped.
- **Spread est.** sets the AlN to zero and spreads the PE-side grease over one 18 mm tile pitch. This is generous (EST): the tile's spreading length
  √(k t R'') is 3.52 mm.

### (a1) per-FET HOT-side shim: details

- **Stack:** tab | grease | shim | grease | AlN | grease | pedestal. That is one more greased face than M11, plus one per extra shim layer.
  - The shim is the only contact, so both tab-side faces carry the heat over the shim area only.
  - Shim area: 126.7 mm² at the small tab and 208.2 mm² at the large, with ± 0.5 mm EST hand placement inside E1 × D1 less the hole.
  - The unshimmed (most-proud) device keeps the baseline 0.399–0.634 °C/W.
- **Grease value that meets 0.7 exactly** at the smallest tab with one 2.2 mm shim (1-D):

  | Shim | Grease threshold | Fraction of the conservative figure |
  |---|---|---|
  | Al | ≤ 0.207 °C·cm²/W | 50 % |
  | Cu | ≤ 0.233 °C·cm²/W | 56 % |
  | Al, two layers | ≤ 0.156 °C·cm²/W | 38 % |

  At the large tab the Al threshold is 0.398 °C·cm²/W, so the large-tab conservative corner passes only with Cu (+0.014).
  **The interface has to be measured.** A shim's resistance is mostly its greased faces: Cu saves only 0.06 °C/W over Al.
- **Isolation:** each shim stays inside its own tab metal (x ≤ E1 min − 1.0 = 11.38 mm, z ≤ D1 min − 1.0 = 12.08 mm).
  - Tab to tab: no metal reaches closer to a neighbour than the tab already does.
  - HOT to PE: the tile overhang measured from the shim edge is at least the overhang from the tab edge.
  - A floating shim is treated as HOT at its tab's net.
  - A shim wider than the tab metal, up to the 16 mm body, would cut the 2.770 mm gap further. Do not use one.
- **One shared tile, flat load:** the shims make every face coplanar, so tiles A and B stay as designed and item 80's four stacks are unchanged.
  - Coplanarity budget (EST terms, linear sum: 0.025 mm step rounding, shim thickness, extra bond line, measurement):

    | Shim build | Budget | Against 0.05 mm |
    |---|---|---|
    | One piece | 0.0425 mm | passes |
    | Two layers | 0.0625 mm | fails |

    So each FET takes **one** shim, ground or chosen to the measured gap. A recessed device cannot be pulled onto the tile: the leads are 11924 N/mm
    stiff (`tolerance.md`).
  - Lean is straightened by the comb about the leads, as on the bench. The 0.0112 rad inspection limit spends 10.3 N at the 16 mm finger line,
    which leaves 49.7 N of the 60 N floor (≥ 45 N).
- **Three changes this needs in the M11 drawings** (they apply to (b) too; fixture boards need none):
  1. **Comb:** a shimmed device's front sits up to 2.2 mm further out. The specified finger goes to 5.2 mm of deflection, 141 N (accept ≤ 102 N)
     and 1474 MPa (Rm 1300). That fails.
     - Fix: G-10 front spacers of s_max − s_i under the strip on the proud devices, plus an s_max offset at the comb root. A straight strip and
       nominal finger deflection then return.
     - Or re-rate the comb.
     - The spacers are insulating, sit on mould compound and go in from above with the strip (`m11-stack-build` order).
  2. **Sink float:** the tile plane sits on the most-proud tab, 0–1.050 mm toward the sink. Shims only add, so a board whose tabs are all
     recessed is shimmed to nominal. The drawing's Y 244.3 ± 1 is **0.050 mm short** on the sink side; make it ± 1.1.
     - A proud plane only lengthens the HOT→PE paths (the tile and sink move away from the board).
  3. **BR1:** back face to tile B is −0.100 to 2.080 mm, against 0.465 nominal; the 1.0 mm pad compresses to 0.47–0.87 mm.
     - The owner fits BR1 after the FETs, so choose its pad grade (and its lean, c60 pass 2) from the measured tile plane.
     - BR1 has no D-36 row.

### (b) compliant interface: details

- **Bound:** the device with the largest gap carries a compliant layer at least Δ thick, so `R_cs` ≥ Δ / (k A) for that layer alone.
- **U spreads:** a 2.1 mm datasheet spread at k 5 W/mK (GAP PAD 5000S35, the best compliant k in `bench_params.py`) gives ≥ 2.778 °C/W at the
  small tab and ≥ 1.749 °C/W at the large. FAIL.
- **Pre-cut pads** inside the catalogue's 10–30 % strain window need t0 = Δ / 0.2: 10.5 mm for U, 1.35 mm for R-lot. Their bulk alone is
  ≥ 1.012 °C/W even in the best case.
- **Dispensed filler, R spreads:** k needed at the small tab, every other layer free / optimistic / conservative:

  | Spread | k needed |
  |---|---|
  | R-lot, 0.270 mm | 2.6 / 3.1 / 5.3 W/mK |
  | R-datasheet, 0.570 mm | 5.4 / 6.6 / 11.1 W/mK |

  This holds only if the board's measured spread is that small, which needs JLC to honour the remark.
  - The proud device's minimum bond line, and the filler's own contact resistance, add to these figures. No filler datasheet is in the repo.
- **Insulation:** unchanged as long as the layer is non-conductive and kept inside the tab metal. AlN remains the 29.3.1 reinforced insulator.
- **Clamp:** at 27–98 psi over the tab, the comb change in (a1) applies here as well.

### (c) fixture

The c60 result stands unchanged (DECISIONS 89 / 90).
- It closes for a typical 1.20 × 0.60 lead (+0.233 mm). It fails the datasheet's largest 1.40 × 0.89 lead in a 1.72 mm hole (−0.072 mm against the
  +0.155 mm needed).
- 2.04 mm drills would leave a 0.23 mm ring, under JLC's 0.254 mm, so the board-level fix is closed.
- Thermally it is the baseline: 0.634 °C/W, +0.066 margin on the conservative basis. It is the only option that keeps that margin without new data.
  It is owner hand-soldering, which DECISIONS 91 wants to avoid.

## What has to be measured

1. **Grease joint resistance** (Electrolube HTCP20S, the M11 compound) per interface at the comb pressure.
   - The (a1) gate: ≤ 0.207 °C·cm²/W (Al) or ≤ 0.233 (Cu), one shim, smallest tab.
   - Cheapest source: at bench-sink-r1 bring-up, grease the FET shims with HTCP20S. Compare (Tcase − Tsink) / P on a shimmed and an unshimmed FET
     at the same strip force. The bench already plans case thermocouples (BENCH-PLAN P2), and its shims are greased faces.
2. **FET lot outline** (the same 25 parts as DECISIONS 90's lead measurement):
   - E1 and D1: shim size and area, and the E1 ≤ 13.720 mm tab-to-tab check above;
   - b and c on all three leads (c60);
   - A1 within the lot.
3. **Per JLC board:** each tab's offset from a straight edge at the two gauge heights (`tolerance.md` §3). This gives the shim set, the lean check and
   the realised spread, which decides whether (b) is even in range.
4. **Shim stock thickness tolerance**, which replaces the EST 0.010 mm per layer in the coplanarity budget.
5. **Comb:** spacer set or re-rated finger. It needs a load–deflection check over 0–2.2 mm of extra deflection.

## Timing

- **Before ordering s57: no.** No option touches the board, Gerbers, BOM or the JLC-solder plan. The only board-level lever, 2.04 mm holes for the
  fixture route, is already closed (ring 0.23 mm < 0.254 mm).
- **Before the R45 M11 build: yes.** Measurement 1 decides (a1) against fixture-soldered enclosure boards. The tab-to-tab finding (E1, or the
  certifier) has to be settled whichever option is chosen.
- **Before the AlN tile RFQ: no**, unless (a2) were chosen. (a1), (b) and (c) all keep the two shared tiles.

**Recommendation.** Plan the enclosed builds on (a1): one single-piece Al or Cu shim per FET, inside the tab metal, plus the comb spacers and the
± 1.1 mm sink float. Gate it on measurement 1. If the greased interface measures above 0.21 °C·cm²/W, a small-tab lot does not meet D-36 with
shims, and the enclosure boards fall back to (c), which also needs the lot's leads to measure inside c60's limits. Drop (b) and (a2).
