<!-- provenance: commit=0490378440b6353283e28c3ae5c5f4dbcb193c95 dirty=false (HEAD at measurement time, branch docs/true-pad-connectivity-baseline; pcb/temper.kicad_pcb untouched by this task). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, identical to the hash recorded in docs/evidence/2026-08-11-stage4-placement-congestion-spike.md §1.1 -- same board, no re-route performed. -->

# True pad-connectivity baseline: how much of this board is actually routed?

**Date:** 2026-08-11

**Task:** re-establish the board's real completion number using
`pad_connectivity_audit.py` (the project's declared PRIMARY completion
metric), which was deleted 2026-08-08 by a dead-code pass that missed its
`scripts/route_board.py` caller, and restored by PR #1008 earlier today.
Measured directly against the committed `pcb/temper.kicad_pcb` — no
re-route was run or needed.

## Headline

**0 of the board's 110 real electrical nets (0.0%) are genuinely,
fully pad-connected.** The number everyone quotes — "64/110 nets carrying
copper (58.2%)" — is real (independently reproduced below) but it is not
a completion percentage; it is a lower bound on how many nets have *some*
copper stamped with the right net number. Every single one of those 64
nets fails a real pad-reachability check. **The honest, fabricable-board
figure is 0%, not 58%.** The gap between "58% complete" and "0% complete"
is not a rounding difference — it is the entire deliverable.

This is worse than the previously-documented shape. The 2026-08-08
nlayer-spike evidence doc found 31/139 (audited-net, not netlist)
"fully pad-connected" and reported it as a real, if modest, success
count. Re-examining that same 31 (today's equivalent: 29, see §2) shows
every one of them is a single-pin net with nothing to connect — an
unpopulated GPIO, an NC pad, a floating USB/RTD test pin. **Zero real,
multi-pad, electrically-meaningful net has ever been shown fully
pad-connected on this board family**, in either measurement. This isn't
a new regression; it's a fact that was always true and never stated
this plainly.

## 1. Method

Ran `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file()` —
the exact function `scripts/route_board.py:audit_pad_connectivity()`
calls as its PRIMARY metric — directly against the committed
`pcb/temper.kicad_pcb` (sha256 `6928b7c8…`, unchanged since 2026-08-08,
identical to the hash the Stage4 congestion spike measured against). No
route was run. The module's own 19-test suite
(`test_pad_connectivity_audit.py`, `test_all_pad_connectivity.py`) was
run first and passes cleanly — the restored module works.

`audit_pcb_file` parses every net that has at least one footprint pin
(139 such names on this board) and, for each, unions segment/via geometry
and pad positions into a connectivity graph, reporting whether every pad
of that net lands in one connected component.

**Denominator note.** 139 ≠ 110. The extra 29 are board-only pin groups
that never made it into the schematic netlist (unpopulated MCU GPIOs,
NC pads, floating USB/RTD force-sense test pins) — every one of them has
exactly 1 pad, confirmed directly. All headline numbers below use the
**110-net official netlist** (`parse_kicad_pcb(...).netlist.nets`) as the
denominator, matching every prior evidence doc's "64/110" framing. The
139-net figure is reported only where noted, for continuity with the
2026-08-08 doc's own denominator.

## 2. The two numbers, side by side

| Metric | Count | % of 110 |
|---|---:|---:|
| Nets carrying copper (`nets_carrying_copper()`, the quoted figure) | 64 | 58.2% |
| Nets genuinely, fully pad-connected (`fully_connected`) | **0** | **0.0%** |

On the 139-net (audited-pins) denominator, for continuity with the prior
doc: 29/139 (20.9%) show `fully_connected=True` — but all 29 have exactly
1 pad (trivially "connected," nothing to join). **Restricted to the 110
nets that actually exist in the schematic — the nets a fabricated board
must actually carry signal or power on — the fully-connected count is
zero.**

Full per-net breakdown of the 110 official nets:

| Bucket | Count | Definition |
|---|---:|---|
| Fully pad-connected | 0 | every pad in one connected component |
| Fake completion | 51 | has explicit segment/via copper, but pads not all joined (the b39b382d shape) |
| Honest gap — zone-pour-only | 13 | net exists only inside a `(zone …)` pour; see §3's caveat |
| Honest gap — zero copper of any kind | 46 | no segment, no via, no zone; genuinely 0% routed |
| **Total** | **110** | |

(`0 + 51 + 13 + 46 = 110`. `51` fake-completion + `13` zone-only =
`64` "carrying copper" official nets — exactly reproducing the quoted
64/110, confirming this audit is measuring the same board the same way,
just adding the pad-reachability check nothing else in the pipeline
does.)

## 3. A real caveat in the audit tool itself, checked and confirmed live

`pad_connectivity_audit.py`'s connectivity graph is built only from
`(segment …)` and `(via …)` blocks — it does **not** parse `(zone …)`
polygons at all (confirmed by reading `_parse_segments_and_vias`, which
has no zone-handling code path, and independently by observing every
zone-only net report `has_any_copper=False` with `unreached_pads` equal
to literally all of its pads). This is a known, already-documented
limitation (2026-08-08 nlayer-spike doc §3.3 flags the identical gap),
re-confirmed here against the current committed board, not assumed.

**What this means for the 13 zone-only nets** (`+15V`, `+15V_LS`, `+3V3`,
`DC_BUS_RTN`, `GATE_HS`, `PWM_HS`, `PWM_LS`, `PWR_RTN`, `SW_NODE`,
`V_BUS_SENSE`, `ac_l`, `ac_n`, `vcc`): this audit cannot distinguish
"the pour genuinely reaches every pad" from "not connected at all." They
are reported in the honest-gap bucket by construction, not because they
have been shown broken. Real board-fab tools (KiCad's own DRC / ratsnest,
or an actual pad-in-polygon flood-fill check) would be needed to resolve
this specific subset. **This caveat affects only these 13 nets** — it
does not touch the 51 fake-completion nets (real segment/via copper,
independently verified not to reach all pads) or the 46 zero-copper nets
(verified to have no geometry of any kind, zone or otherwise — see next
paragraph).

**One result the zone question does *not* leave ambiguous: `gnd`.** The
board's single largest net — 86 pads, more than the next five largest
combined — has **zero copper of any kind**: no segment, no via, and (grep
of all 96 zone blocks' net numbers, confirmed) no zone pour either. This
is not a tool limitation; it is directly, unambiguously verifiable from
the file, and it means `nets_carrying_copper()`'s 64/110 headline
includes not one trace of the board's ground return. The 46-net
zero-copper bucket's other members by pad count: `+170V_BUS` (11),
`I_SENSE` (7), `refin_n` (5), plus 43 smaller (2–4 pad) nets, mostly
safety-comparator and RTD-frontend signal legs.

## 4. Severity: this is not evenly distributed

Sorted by fraction of pads actually reached (worst first), the largest
"carrying copper" nets are also the worst-connected in absolute terms —
not a coincidence, since bigger nets have more opportunities for the
2-endpoint-only routing shape (§5) to leave pads stranded:

| Net | Pads reached / total | Has explicit copper | Netclass |
|---|---:|:---:|---|
| `gnd` | 0/86 (all isolated) | no | ground |
| `+3V3` | 0/51 | no (zone-only) | power |
| `PWR_RTN` | 0/18 | no (zone-only) | power |
| `vcc` | 0/13 | no (zone-only) | power |
| `DC_BUS_RTN` | 0/12 | no (zone-only) | power |
| `+170V_BUS` | 0/11 | no | power |
| `+15V` | 0/10 | no (zone-only) | power |

(The audit's raw `pads_connected` field reports `1` for these — the size
of the largest same-net component, which is 1 because with zero copper
every pad is its own isolated singleton. The honest reading is **0 pads
reached from any other pad**, not "1 of N connected"; every pad of these
nets appears in `unreached_pads`.)

No net with more than 2 pads on this board reaches all of its pads. The
best-case partial nets are the many 2-pad nets sitting at 1-of-2 (a
single explicit trace exists but the audit's snapped-position union-find
does not find it joining both ends — consistent with the pre-existing
`fallback_channel_path`/wrong-waypoint defect the 2026-08-08 doc traced
to `channel_mapping.py:155-179`, not re-diagnosed here).

## 5. Who's implicated — component and netclass clustering

**Netclass: every class fails, without exception.**

| Netclass | Not fully connected | Total | Rate |
|---|---:|---:|---:|
| signal | 98 | 98 | 100% |
| hv | 3 | 3 | 100% |
| power | 8 | 8 | 100% |
| ground | 1 | 1 | 100% |

This is not an HV-clearance or netclass-specific problem — the failure is
uniform across every class, confirming (again, independently of the
Stage4 spike's own conclusion) that this is a structural/placement issue,
not a class-specific routing rule blocking one category.

**Component clustering** (counting, per not-fully-connected net, which
components own an unreached pad):

| Component | Nets touched (of 110 broken) |
|---|---:|
| **U27 (ESP32-S3 MCU)** | **24** |
| U7 | 12 |
| U9 (RTD front-end ADC) | 9 |
| U23, U26 | 9 each |
| U24 | 8 |
| U25 | 6 |

**U27 alone touches more than a fifth of every broken net on the
board** — over double the runner-up, U7. This sharpens (not contradicts)
the Stage4 congestion spike's finding that U27 touched 11/43 *A*-search
failures*: measured against the full pad-connectivity picture rather
than just A*'s live failure log, U27's footprint on the board's
incompleteness is more than twice as large again. U9, the RTD ADC named
alongside U27 in that spike as the other end of a forced ~211mm bus, also
reappears here. Nothing in this clustering contradicts the Stage4 spike's
placement-congestion diagnosis; it reinforces it with a stricter metric.

## 6. Cross-check against the Stage4 spike's 43-failure list — the real disagreement

The 2026-08-11 Stage4 placement-congestion spike reported a live run:
**60/103 raw Stage4 completion** (43 A*-search failures, 7 nets excluded
from A* entirely by `_should_route()` as zone-pour-covered — `103 + 7 =
110` ✓). Reproducing that exact partition against this audit:

- **All 43 of Stage4's live A*-failures are confirmed still not
  pad-connected.** No disagreement there — the stage-level view is not
  wrong about its own failures.
- **Of the 60 nets Stage4's live run counted as "routed successfully":
  zero are genuinely fully pad-connected.** 55 of the 60 (91.7%) have
  real segment/via copper that provably does not reach all of that net's
  pads — a definitive fake-completion finding, not a zone-audit ambiguity.
  The remaining 5 are zone-only nets this audit cannot independently
  confirm either way (§3's caveat).

**This is the disagreement the brief asked to lead with, stated
precisely: the stage-level "60/103 (58.3%)" view is not a conservative
estimate of real completion — it is almost entirely composed of nets that
look done and are not.** Pad-connectivity doesn't just corroborate the
Stage4 view's 43 known failures; it reveals that essentially the entire
"success" column is the same failure, uncounted. Combining both views:
of the 103 nets Stage4 ever attempted, at most 5 (4.9%) have any chance
of being genuinely complete, and even those 5 are unverified rather than
confirmed.

## 7. Honest completion percentage

**0 of 110 (0.0%)** electrical nets on `pcb/temper.kicad_pcb` are
verified, pad-to-pad, fully routed. At most 5 additional nets (4.5%) are
in an unverified zone-pour state this specific audit cannot resolve —
call it **0.0%–4.5%**, not 58.2%, as the honest range for "how much of
this board would pass inspection as actually connected." Even the
optimistic end of that range is nowhere close to fabricable. This board
is, by the metric this project explicitly designated as PRIMARY for
exactly this reason, **not routed** in any sense a fabrication house or
an electrical continuity check would accept — it is closer to
"topologically planned" than "routed."

## 8. What this changes, going forward

- **Stop quoting "64/110" or "58%" as completion.** Every future status
  report on this board should lead with the pad-connectivity number
  (0/110 today) alongside, not instead of, the carrying-copper number —
  exactly as `scripts/route_board.py`'s own `_format_run()` already does
  in its printed output (this was the entire point of restoring the
  module). This document is the first time that comparison has been
  made for the currently-committed production board rather than a
  transient spike-run board.
- **The zone-pour blind spot (§3) is worth closing**, separately from
  this task's scope: a pad-in-polygon containment check against `(zone
  …)` fill geometry would resolve the 13 (here, 5 live-relevant) nets
  this audit currently cannot adjudicate, and would very likely raise
  the honest number somewhat — but not from 0%, since 97 of the 110 nets
  fail for reasons unrelated to zone coverage.
- **`gnd` having zero copper of any kind is worth escalating on its own**,
  independent of the broader completion-percentage story — a board with
  no ground copper at all cannot be prototyped, let alone shipped,
  regardless of how every other net is doing.
- This document does not attempt a fix. Per this task's boundaries,
  `router_v6/**` production code (including the zone-blind-spot fix,
  the `fallback_channel_path` 2-pad-waypoint defect, and the placement
  congestion §5 reflects) is out of scope and owned by other concurrent
  work; this is a measurement, not a remediation.
