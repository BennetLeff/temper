<!-- provenance: this document (docs/jlcpcb-fab-capability-envelope branch, worktree
/home/bennet/Desktop/temper-fab-envelope, based on origin/main 849c0ce63). Board measured:
origin/fix/board-schematic-resync (PR #1134) at commit a3fbaff37, checked out read-only in
/home/bennet/Desktop/temper-board-schematic-resync (a pre-existing, up-to-date worktree; verified
`git log -1 origin/fix/board-schematic-resync` == a3fbaff37 before measuring). pcb/temper.kicad_pcb
sha256=b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6 -- matches the hash prefix
`b7d865b7...091c1d6` recorded in that branch's OWN power_pcb_dataset/drc_ceiling.json
_march["2026-08-13-clearance-saturation-correction"] entry, confirming this document measures the
exact board that PR #1134's own clearance re-measurement measured. Neither pcb/temper.kicad_pcb nor
pcb/temper.kicad_dru nor any clearance/creepage/safety constant is edited by this document or by any
script it used -- every kicad-cli run below was against a scratch copy under
/tmp/.../scratchpad/fab_measure/, built with scripts/measure_uncapped_drc.py's own
make_scratch_board()/run_kicad_drc() (imported, not modified). kicad-cli 10.0.5. No subagents were
dispatched; all web fetches and board measurements below were performed directly. -->

# JLCPCB fabricator capability envelope, and the board checked against it

**Verdict up front.**

1. **No fabricator was named anywhere in this repo before this document.** JLCPCB is now the
   sourced, primary target (`docs/hardware/FAB_CAPABILITY.md`), per the user's selection of a
   mainstream commodity house.
2. **The board's actual routed trace width comfortably clears JLCPCB's 2oz floor.** Measured
   minimum trace width on the resynced board: **0.25mm (9.84 mil)**, against a JLCPCB 2oz-multilayer
   floor of 0.15mm (6 mil). **PASS**, ~0.10mm margin.
3. **`DEFAULT_ROUTING_CLEARANCE_MM` (0.2mm) is NOT the binding constraint** — it clears JLCPCB's 2oz
   floor (0.15mm) with 0.05mm to spare. This corrects a hypothesis stated in the task brief: the
   named constant passes. The values that actually sit below the 2oz floor are different ones (next
   item).
4. **Three repo values ARE below JLCPCB's 2oz floor, and one repo value is below JLCPCB's floor at
   *any* copper weight:**
   - `trace_width_assignment.py`'s `default_width=0.127mm` and the `FinePitch`/`Differential`
     netclasses' `trace_width` (also 0.127mm) sit below the 0.15mm 2oz floor. **Not currently used by
     any routed track on the real board** (measured: only 0.25/0.3048/0.508mm widths exist on-board)
     — a latent risk, not a present violation.
   - `FinePitch`/`Differential`/"Same footprint pads" `clearance` (0.1mm) sits below the 0.15mm 2oz
     floor.
   - **Every via on the board** (44/44) has an annular ring (0.1mm or 0.2mm) below JLCPCB's 2oz PTH
     annular-ring floor (0.254mm). The smaller family (4 vias, 0.1mm ring) fails even JLCPCB's 1oz
     absolute minimum (0.15mm).
   - `scripts/generate_kicad_dru.py`'s "Via hole clearance" rule (0.25mm) is below JLCPCB's published
     PTH-to-track absolute minimum (0.28mm) **independent of copper weight** — this repo number was
     never a fab-safe floor, at 1oz or 2oz.
5. **The board's own `.kicad_pcb`/`.kicad_pro` declare NO copper weight anywhere** — no `stackup`
   block exists in either file. The 2oz assumption lives only in prose docs and code comments, not in
   the artifact that would actually be sent to a fab (§3).
6. **Of the repo's 1,085 true `clearance` DRC findings on this board (PR #1134's own measurement,
   `power_pcb_dataset/drc_ceiling.json`), only 145 (13.4%) are also genuine JLCPCB-2oz-floor
   manufacturability failures.** The remaining 940 are the repo's own IEC-60335-derived safety margin
   above JLCPCB's manufacturing floor — real findings against the repo's stricter rules, not things
   JLCPCB's line would refuse to build. §7.2.
7. **`hole_clearance` is the opposite story: all 90 of 90 measured findings are also genuine JLCPCB
   floor failures** (§7.4) — this category has essentially zero "repo-only margin," because the
   repo's own DRU rule for it (0.25mm) already sits below JLCPCB's published floor (0.28mm), per
   item 4 above.
8. **No board-edge slot/cutout exists on this board today** (`Edge.Cuts` layer has only 2 graphic
   items — a single closed outline, not an internal milled slot). JLCPCB's slot-width limits (§1) are
   relevant to a technique this design does not currently use, not to an existing feature.
9. **Laminate is FR-4, UL94V-0-implied by JLCPCB's UL certification (file E479892, classes JLC-1/
   JLC-4)** but **not stated on JLCPCB's capabilities page itself**, and **per-order material
   certification is not confirmed published** — flagged as an open item, not assumed.

---

## 1. Method and sources

**Fabricator research.** JLCPCB's live capability page
(<https://jlcpcb.com/capabilities/pcb-capabilities>) was fetched twice independently on 2026-08-13 —
once via the harness's URL-summarization tool, once via raw `curl` + manual text extraction from the
served HTML (the page renders enough static content server-side for `curl` to retrieve real numbers;
this was cross-checked against the summarized fetch and found consistent). The raw-text extraction is
what every number in §2 below and in `docs/hardware/FAB_CAPABILITY.md` is sourced from, because it
preserves exact wording and avoids a summarizer's paraphrase risk. Supplementary JLCPCB pages
(copper-weight guide, UL certification, FR-4 material page, extra-charges help article) were fetched
the same day. PCBWay and Advanced Circuits/AdvancedPCB pages were fetched for the "named alternative
differs materially" comparison the task requires.

**Board measurement.** All geometry (§5–§7) was measured against
`origin/fix/board-schematic-resync` (PR #1134) — **not** `main`, per the task's explicit instruction,
because `main`'s board disagrees with `elec/src`. A pre-existing, already-synced worktree at
`/home/bennet/Desktop/temper-board-schematic-resync` was confirmed at the exact branch tip
(`a3fbaff37`, matching `git log -1 origin/fix/board-schematic-resync`) before any measurement. Two
independent techniques were used:

- **Literal geometry parsing**: a standalone, stdlib-only Python script reads `pcb/temper.kicad_pcb`'s
  S-expressions directly and extracts every track/arc segment width, every via's `(size, drill)` pair
  (annular ring = `(size - drill)/2`), and every through-hole pad's `(size, drill)` pair. This needs no
  DRC engine and is exhaustive by construction (every segment/via/pad in the file is visited). Used for
  §5 (trace width) and §6 (annular ring, drill).
- **Scratch-copy kicad-cli DRC**: `scripts/measure_uncapped_drc.py`'s own `make_scratch_board()` /
  `run_kicad_drc()` functions (imported unmodified) build a scratch copy of the real board+project
  under `/tmp/.../scratchpad/`, substitute a purpose-built `.kicad_dru` for the measurement in
  question, and run `kicad-cli pcb drc --all-track-errors --format json`. This never touches
  `pcb/temper.kicad_pcb`, `pcb/temper.kicad_dru`, or any committed file. Used for §7 (clearance,
  which has no literal per-pair field and must be computed by KiCad's own geometry engine) and to
  cross-check §6.

Every DRC run below reports `total_violations`/category counts directly from kicad-cli's JSON output;
where a category is known to saturate at kicad-cli's `ERROR_LIMIT=199`/`EXTENDED_ERROR_LIMIT=499` caps
(`docs/evidence/2026-08-12-uncapped-drc-measurement.md`), this is called out explicitly rather than
trusted at face value — none of the measurements this document's verdicts depend on land on a cap (the
largest raw count consulted, 145 fab-floor clearance violations, is far under 199).

---

## 2. JLCPCB — sourced capability table

Full table with per-row citations: `docs/hardware/FAB_CAPABILITY.md` §1. Reproduced here, condensed,
for the specific figures this board's verdicts depend on:

| Parameter | 1oz multilayer | **2oz multilayer (this board's copper weight)** |
|---|---|---|
| Min. track width & spacing | 0.09 / 0.09mm (3.5/3.5 mil) | **0.15 / 0.15mm (6/6 mil)** |
| Min. PTH annular ring | rec. ≥0.20mm, abs. min 0.15mm | **0.254mm** |
| Min. drill diameter | 0.15mm | 0.15mm (not broken out by oz) |
| Min. hole-to-copper (PTH-to-track) | 0.28mm abs. min, 0.35mm rec. | not broken out by oz |
| Solder mask min. dam width | 0.10mm (color) / 0.13mm (B/W) | **0.20mm (any color)** |
| Board-edge-to-copper (routed) | ≥0.2mm | not broken out by oz |
| Min. plated slot width (multilayer) | 0.35mm | not broken out by oz |
| Outer copper weight offered on 4-layer | 1oz | **2oz — standard, not special-order** |
| Inner copper weight | 0.5oz **default**, 1oz/2oz available | (same, copper weight is a stackup property, not outer-specific) |

Source: <https://jlcpcb.com/capabilities/pcb-capabilities>, fetched 2026-08-13 (raw HTML text
extraction; independently cross-checked via a second, tool-summarized fetch of the same URL the same
day). "2oz on 4-layer is standard" per
<https://jlcpcb.com/help/article/jlcpcb-copper-weight> ("1oz, 2oz (standard)"), fetched 2026-08-13.
UL94V-0 / UL file E479892 per <https://jlcpcb.com/pcb-fabrication/fr4-pcb> and
<https://jlcpcb.com/help/article/UL-Certification>, fetched 2026-08-13 — **note this is not printed on
the capabilities page itself**, only on the marketing/UL pages; treat as JLCPCB's claim about their
material, not as a certificate this repo has in hand.

**What was not obtainable.** PCBWay's own dedicated "min track/spacing by copper weight" help page
(<https://www.pcbway.com/helpcenter/ordering_parameter_instruction/What_is_the_Min_Track_Spacing_for_1oz__2oz__3oz__Copper_weight_.html>)
embeds its numbers in images (`Finished_copper.png`, `mini_trace_width_副本.png`) that this
environment's fetch tooling cannot OCR; PCBWay's general capabilities page gives only a copper-weight-
agnostic 4mil figure. A per-order JLCPCB material test report / certificate of conformance is not
confirmed to exist as a published, standing offering — the UL-Certification page links generic
material datasheets and points to a general "Certifications Center" (ISO 9001/14001, RoHS, REACH), not
a per-order MTR. Both are recorded as **open items**, not filled in with an estimate.

## 2.1 Named alternatives — material differences

| Fab | 2oz outer, multilayer, min trace/space | Source |
|---|---|---|
| **JLCPCB** | **0.15/0.15mm (6/6 mil)** | jlcpcb.com/capabilities/pcb-capabilities, 2026-08-13 |
| PCBWay | Not broken out by copper weight in their machine-readable capabilities page; the dedicated page exists but its numbers are image-only | pcbway.com/capabilities.html, pcbway.com/helpcenter/..., both 2026-08-13 |
| Advanced Circuits / AdvancedPCB (Aurora, CO facility) | **0.007in/0.007in (7/7 mil) Standard tier** — looser than JLCPCB; 0.0055in Advanced tier, 0.004in Development tier (premium) | advancedpcb.com/en-us/resources/pcb-capabilities-and-expanded-capabilities/, 2026-08-13 |

The materially interesting finding: Advanced Circuits' US **Standard** tier at 2oz is *looser* (7/7
mil) than JLCPCB's mainstream 2oz multilayer figure (6/6 mil). A domestic-specialist assumption of
"tighter" does not hold here without checking the specific tier.

---

## 3. The board's own files declare no copper weight at all

Checked directly against the resync-branch (`a3fbaff37`) `pcb/temper.kicad_pcb` and `pcb/temper.kicad_pro`:

```
$ python3 -c "text=open('pcb/temper.kicad_pcb').read(); print(text.find('(stackup'))"
-1        # no stackup block exists anywhere in the file

$ python3 -c "import json; d=json.load(open('pcb/temper.kicad_pro')); print(d['board'].keys())"
dict_keys(['3dviewports', 'design_settings', 'layer_presets', 'viewports'])
# no 'stackup' key
```

KiCad's project format has a place for a per-layer copper-weight/dielectric stackup
(`board.design_settings.stackup` in `.kicad_pro`, populated when a user visits Board Setup > Physical
Stackup and saves); this project has never populated it. **Nothing in the artifact that would actually
be exported to Gerbers and sent to a fab specifies 2oz copper anywhere.** The 2oz assumption exists
only in `docs/specs/PCB_SPECIFICATION.md` §3.1/§12.2, `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §1,
and scattered code/doc comments (`docs/hardware/GROUNDING_EMI_STRATEGY.md`,
`docs/hardware/POWER_PLANE_DESIGN.md`).

This also surfaced a **doc-vs-doc disagreement** worth recording: `docs/hardware/
GROUNDING_EMI_STRATEGY.md` (line 133) and `docs/hardware/POWER_PLANE_DESIGN.md` (line 54) both say the
bottom/control-signal layer (L4, `B.Cu`) is **1oz**, while `docs/specs/PCB_SPECIFICATION.md` §12.2's
"Order Specifications Summary" says generically "Copper: 2oz outer, 1oz inner" — which, read plainly,
means *both* outer layers (`F.Cu` **and** `B.Cu`) are 2oz. These two claims are inconsistent about
whether `B.Cu` is 1oz or 2oz, and — because no stackup is actually encoded anywhere — nothing currently
resolves the disagreement. Until a real stackup is entered into the KiCad project, this is undecided,
not merely undocumented.

`docs/specs/PCB_SPECIFICATION.md` §12.2 also already names JLCPCB and states "Min Trace/Space: 6/6
mil" as an order note — which happens to numerically equal JLCPCB's real 2oz-multilayer figure
measured in §2. This is very likely coincidence, not derivation: the same section's stackup line ("2oz
outer, 1oz inner") carries no oz-specific trace/space citation, "6/6 mil" is also a generic
industry-wide round-number heuristic used independent of fab or copper weight, and no other document in
this repo shows the 2oz-specific JLCPCB lookup being performed anywhere before this one. Treating a
coincidental match as "already checked against a real limit" would be the exact failure mode this task
was scoped to close.

**Consequence for inner-layer current capacity.** `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §3.6
derives the +5V distribution trace width assuming **1oz internal copper**. JLCPCB's inner-layer
**default** is 0.5oz (§2); 1oz is available but must be an explicit order-form choice. If this board
were ordered today — with no stackup in the KiCad project to carry the requirement forward, and no
order-form override — JLCPCB's default inner copper (0.5oz) would very likely be used instead of the
1oz the current-capacity derivation assumes, invalidating that derivation's margin (current capacity
scales sub-linearly but still meaningfully with thickness; roughly the ~1.3–1.4x factor IPC-2221B's own
exponents imply between 0.5oz and 1oz at fixed width/rise).

---

## 4. Board provenance for the measurements below

```
branch:  origin/fix/board-schematic-resync (PR #1134)
commit:  a3fbaff37 (fix(docs): correct placed/unplaced component count in drc_ceiling.json)
sha256(pcb/temper.kicad_pcb): b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6
```

This hash matches the hash prefix (`b7d865b7...091c1d6`) recorded in that same branch's own
`power_pcb_dataset/drc_ceiling.json`, `_march["2026-08-13-clearance-saturation-correction"]` entry —
confirming every measurement below is against the identical board content PR #1134's own DRC
re-measurement used, not a stale or drifted copy.

---

## 5. Measured: trace width

Literal parse of every `segment`/`arc` block in `pcb/temper.kicad_pcb` (2,149 total, 0 arcs):

| Width | Mils | Count |
|---|---|---|
| 0.2500mm | 9.84 mil | 1,785 |
| 0.3048mm | 12.00 mil | 192 |
| 0.5080mm | 20.00 mil | 172 |

**Minimum trace width present on the board: 0.25mm (9.84 mil).**

| Limit | Value | Verdict |
|---|---|---|
| JLCPCB 2oz multilayer min trace width | 0.15mm (6 mil) | **PASS** — 0.10mm margin |
| JLCPCB 1oz multilayer min trace width | 0.09mm (3.5 mil) | PASS (would also pass at 1oz) |

None of the three widths present on the board equal any `netclass_rules.yaml`/`pcb/temper.kicad_pro`
net-class `trace_width` value exactly (Default 0.2, Power 1.0, HighVoltage 5.0, GateDrive 0.4, etc.) —
they are narrower than every netclass's assigned width, which is a **repo self-consistency** gap
(design intent vs. actual routed width — the likely explanation for the repo's own, separately
tracked, `track_width` DRC category currently sitting at kicad-cli's 199-item report cap,
`power_pcb_dataset/drc_ceiling.json`'s `2026-08-13-clearance-saturation-correction` entry flags this
exact category as unverified-uncapped on this board). It is **not** a fab-floor question — every width
present clears JLCPCB's 2oz floor regardless.

**The 0.127mm defaults are absent from the real board.** `trace_width_assignment.py`'s
`default_width=0.127mm` and the `FinePitch`/`Differential` net classes' `trace_width` (also 0.127mm)
are below the 0.15mm 2oz floor (§2), but **zero segments at 0.127mm exist anywhere on this board** —
confirmed by the histogram above (only three distinct widths exist, none of them 0.127mm). This is a
latent risk in the configured defaults, not a present violation: if a future route ever falls through
to that default on a 2oz-copper layer, it would need to be caught and widened before fabrication, but
nothing on the board today is actually built that way.

---

## 6. Measured: annular ring and drill

Same literal-parse technique, over every `via` and every through-hole `pad` block.

### 6.1 Vias

44 vias total, two distinct geometries:

| Size | Drill | Annular ring | Count |
|---|---|---|---|
| 0.4mm | 0.2mm | **0.1000mm (3.94 mil)** | 4 |
| 0.8mm | 0.4mm | **0.2000mm (7.87 mil)** | 40 |

| Limit | Value | 0.1mm ring (4 vias) | 0.2mm ring (40 vias) |
|---|---|---|---|
| JLCPCB 2oz PTH annular ring | 0.254mm | **FAIL** | **FAIL** |
| JLCPCB 1oz PTH annular ring, absolute min | 0.15mm | **FAIL** | PASS (right at the edge) |
| JLCPCB 1oz PTH annular ring, recommended | 0.20mm | FAIL | meets exactly, no margin |

**Every via on the board (44/44) fails JLCPCB's 2oz annular-ring floor.** The 4 smaller vias fail even
JLCPCB's 1oz absolute minimum. The 40 larger vias meet JLCPCB's 1oz *recommended* figure exactly, with
zero margin — a real fab would likely flag this at DFM review even at 1oz.

The 4 smaller vias (0.1mm ring) are additionally already flagged by the project's **own** configured
KiCad constraints, independent of any fab comparison: `pcb/temper.kicad_pro`'s
`board.design_settings.rules.min_via_annular_width` is set to 0.15mm, `min_via_diameter` to 0.5mm, and
`min_through_hole_diameter` to 0.3mm — this via's 0.1mm ring, 0.4mm diameter, and 0.2mm drill fail all
three (confirmed: kicad-cli's built-in `annular_width`, `via_diameter`, and `drill_out_of_range` checks
each report exactly 4 violations on this board, matching this via family one-for-one). These 4 are a
pre-existing repo-internal-rule violation, not something this document's fab comparison introduces.

**Minimum drill used: 0.2mm** (the 4 smaller vias), vs. JLCPCB's multilayer minimum drill of 0.15mm —
**PASS**, 0.05mm margin.

### 6.2 Through-hole component pads

90 `thru_hole` pads (excludes 4 `np_thru_hole` mounting-hole pads on K1, which have zero designed
annular ring by construction — `pad_size == drill == 1.8mm` — a deliberate bare mechanical hole, not a
plated feature JLCPCB's PTH annular-ring spec applies to):

| Metric | Value | Reference |
|---|---|---|
| Minimum annular ring | **0.35mm (13.78 mil)** | J1/J2 connector pads, rect, size 1.7mm, drill 1.0mm |
| Minimum drill | **0.70mm (27.56 mil)** | R55 |

| Limit | Value | Verdict |
|---|---|---|
| JLCPCB 2oz PTH annular ring | 0.254mm | **PASS** — 0.10mm margin |
| JLCPCB 1oz PTH annular ring, recommended | 0.20mm | PASS |

Component through-hole pads clear the 2oz floor comfortably. **Vias are the entire annular-ring
problem on this board, not component pads.**

---

## 7. Measured: copper-to-copper spacing (clearance), via kicad-cli DRC on a scratch copy

Clearance has no literal per-object field — it is a computed pairwise distance, so this required
running kicad-cli's own DRC engine (not the literal parser) against a scratch copy of the resync
board, per the method in §1.

### 7.1 Fab-floor measurement: blanket 0.15mm clearance rule (JLCPCB 2oz multilayer floor)

A minimal, condition-less scratch `.kicad_dru` (`(constraint clearance (min 0.15mm))`, plus an
identical `track_width` rule for cross-checking §5) was substituted onto the scratch board copy and
run through `kicad-cli pcb drc --all-track-errors --format json`:

```
clearance violations (< 0.15mm anywhere on the board): 145
track_width violations (< 0.15mm anywhere on the board): 0   -- confirms §5's literal-parse result independently
```

Every violation's `description` field carries kicad-cli's own measured `actual` distance
(e.g. `"...clearance 0.1500 mm; actual 0.1226 mm)"`). Extracting all 145:

| Bucket | Count |
|---|---|
| < 0.01mm (essentially touching) | 4 |
| 0.01–0.05mm | 35 |
| 0.05–0.10mm | 24 |
| 0.10–0.15mm | 82 |

**Worst-case (minimum) actual spacing measured on the board: 0.001mm.** Median of the 145 sub-floor
locations: 0.11mm.

| Limit | Verdict |
|---|---|
| JLCPCB 2oz multilayer min spacing (0.15mm) | **FAIL at 145 distinct locations** |
| JLCPCB 1oz multilayer min spacing (0.09mm) | 92 of the 145 (63%) would PASS at 1oz; 53 (37%) fail even the 1oz floor — i.e. these 53 are congestion/routing defects independent of copper weight entirely |

### 7.2 How much of this is a fab problem vs. the repo's own stricter safety margin

PR #1134's own measurement (`power_pcb_dataset/drc_ceiling.json`,
`_march["2026-08-13-clearance-saturation-correction"]`, method: `scripts/measure_uncapped_drc.py
dru-category clearance`, the provably-exhaustive DRU-rule partition-and-sum method) established the
board's true `clearance` violation count under the repo's **own** (IEC-60335-derived, much stricter —
0.1–8.0mm depending on net-class pair) design rules as **1,085**, against the exact same board content
this document measured (hash match confirmed, §4). This document did not re-derive that number (no
reason to redo an already-cited, provably-exhaustive measurement — see `AGENTS.md`'s "Absence Is Not
Evidence" convention on reusing prior work rather than needlessly re-measuring it); a light
reproduction was run as a sanity check: a **capped** raw kicad-cli run against the board's real,
committed DRU reported 501 clearance violations, consistent with PR #1134's own capped reading (499,
within the ±0–14 run-to-run overshoot `docs/evidence/2026-08-12-uncapped-drc-measurement.md` documents
for `--all-track-errors`) — confirming this document is looking at the same board state PR #1134's own
1,085 figure describes.

**145 of 1,085 (13.4%) of the repo's own `clearance` findings are also genuine JLCPCB-2oz-floor
manufacturability failures.** The remaining 940 (86.6%) are locations that clear JLCPCB's real 0.15mm
2oz manufacturing floor but fall short of the repo's own, deliberately stricter, IEC-60335-derived
safety margins (0.1mm same-footprint / fine-pitch exceptions aside, most of that 1,085 total is the HV
domain's 2.0–8.0mm creepage/clearance figures, which have nothing to do with etch tolerance — they are
safety separation, not manufacturability). **These are different questions, and conflating them would
misreport a safety-margin gap as a manufacturability failure or vice versa.** Per the task's hard
constraint: JLCPCB's looser floor is never grounds to relax the repo's stricter safety figures where
they differ — the 940 remain real findings against the safety standard regardless of what JLCPCB's
line can etch.

### 7.3 Cross-check at the solder-mask-relevant 0.20mm figure

JLCPCB's 2oz solder-mask minimum dam width is 0.20mm (§2), tighter than the 0.15mm trace/space floor.
Re-running the same blanket-clearance measurement at 0.20mm:

```
clearance violations (< 0.20mm anywhere on the board): 265
```

(up from 145 at 0.15mm, as expected — a looser threshold catches more locations). kicad-cli's own
`solder_mask_bridge` check (governed independently of the custom `.kicad_dru` clearance value — its
count stayed fixed at **145** across both the 0.15mm and 0.20mm scratch runs, proving it is not a
distance-threshold check controllable through the DRU mechanism used here) reports **145** findings on
this board, matching PR #1134's own reported 145 exactly (cross-validation that this scratch board
setup reproduces the real board state). `solder_mask_bridge` fires specifically when two different-net
solder-mask apertures **overlap** (a topological, not distance, condition) — this board has
`pad_to_mask_clearance = 0` (`pcb/temper.kicad_pcb`'s `(setup (pad_to_mask_clearance 0))`), so a mask
aperture equals its underlying copper outline exactly, meaning an "overlap" here corresponds to an
effective solder-mask dam width **at or below 0mm**. That is below every published fab figure this
document found (JLCPCB's smallest is 0.10mm at 1oz color) — **all 145 `solder_mask_bridge` findings are
genuine fab-manufacturability failures, independent of which copper weight or fab is chosen**, not a
repo-only stricter-margin artifact.

### 7.4 hole_clearance (hole-to-copper)

The board's `Via hole clearance` DRU rule (0.25mm, `scripts/generate_kicad_dru.py`) produced 90
`hole_clearance` violations under the real, committed DRU (matching PR #1134's own reported 90 — not
capped, since `ERROR_LIMIT=199` and 90 is well under it). Extracting `actual` values from all 90:

```
min actual: 0.0mm     max actual: 0.235mm
```

| Limit | Count failing |
|---|---|
| JLCPCB PTH-to-track absolute minimum (0.28mm) | **90 of 90 (100%)** |
| JLCPCB PTH-to-track recommended (0.35mm) | 90 of 90 (100%) |
| JLCPCB via-hole-to-copper (0.2mm) | 78 of 90 (87%) |

**All 90 `hole_clearance` findings are also genuine JLCPCB floor failures.** This is the opposite
pattern from `clearance` (§7.2, where only 13.4% overlapped): here there is essentially no "repo-only
margin" gap, because the repo's own DRU rule (0.25mm) is *already below* JLCPCB's published absolute
minimum (0.28mm) — the repo's chosen number was never a fab-safe floor at any copper weight, not a case
of the repo choosing extra safety margin above a fab minimum.

### 7.5 copper_edge_clearance (board-edge-to-copper)

7 findings under the real, committed DRU (repo's own `min_copper_edge_clearance = 0.5mm`,
`pcb/temper.kicad_pro`), `actual` values:

```
0.2250mm  (x3)
0.0000mm  (x1)
0.4250mm  (x3)
```

| Limit | Verdict |
|---|---|
| JLCPCB routed board-edge-to-copper (0.2mm) | 6 of 7 **PASS** (0.225mm, 0.425mm); 1 of 7 **FAIL** (0.0mm — literally at the edge) |
| Repo's own constraint (0.5mm) | 7 of 7 fail |

**6 of these 7 are repo-margin-only** (below the repo's chosen 0.5mm safety figure, but above JLCPCB's
real 0.2mm manufacturing floor). **1 of the 7 (the 0.0mm case) is a genuine fab-floor failure** —
copper directly at the board edge, independent of any safety-margin question, and worth flagging for
priority attention over the other 6.

No milled slot/cutout exists on this board (`Edge.Cuts` has only 2 graphic items — a single closed
outline). JLCPCB's slot-width limits (§2) describe a technique not currently in use on this design.

---

## 8. Summary verdict table

| # | Limit | Board's measured value | Verdict |
|---|---|---|---|
| 1 | Min. trace width (2oz: 0.15mm) | 0.25mm min | **PASS** |
| 2 | Min. copper-to-copper spacing (2oz: 0.15mm) | 0.001mm worst-case, 145 locations below floor | **FAIL** (145 locations) |
| 3 | Min. PTH annular ring, vias (2oz: 0.254mm) | 0.1mm / 0.2mm | **FAIL** (44/44 vias) |
| 4 | Min. PTH annular ring, component pads (2oz: 0.254mm) | 0.35mm min | **PASS** |
| 5 | Min. drill (0.15mm) | 0.2mm min | **PASS** |
| 6 | Min. hole-to-copper (0.28mm abs. min) | 0.0–0.235mm, 90 findings | **FAIL** (90/90) |
| 7 | Min. board-edge-to-copper (0.2mm) | 0.0–0.425mm, 7 findings | **FAIL** (1/7); PASS (6/7) |
| 8 | Solder-mask min. dam (2oz: 0.20mm) | effective ≤0mm, 145 findings | **FAIL** (145/145) |
| 9 | Min. slot width | n/a — no slot on this board | **N/A** |
| 10 | Inner copper weight for current capacity (1oz assumed) | undeclared in the KiCad project; JLCPCB default is 0.5oz | **needs-design-change** (add explicit order note / stackup) |
| 11 | Outer copper weight declaration (2oz assumed) | undeclared in the KiCad project (no stackup block at all) | **needs-design-change** (add a real stackup to `pcb/temper.kicad_pro`, resolve the L4 1oz-vs-2oz doc disagreement, §3) |
| 12 | Laminate UL94V-0 | claimed by JLCPCB (not on capabilities page; UL file E479892) | **PASS, weakly sourced** — usable as a starting citation, not a certificate in hand |
| 13 | Per-order material certification | not confirmed published | **unresolved** — must be requested directly from JLCPCB |

---

## 9. What would have to change, and what that does to the IPC-2221B derivations

Items 2, 3, 6, and 8 above are the ones with real design consequences if 2oz outer copper is confirmed
as the production target:

- **Item 3 (via annular ring, 44/44 vias).** Every via on the board needs a larger pad for its drill
  size to reach a 0.254mm ring: the 0.4mm/0.2mm family needs to grow to at least 0.4mm+2×0.254 ≈
  0.91mm pad (or keep the pad and shrink the drill, which is the less attractive direction for a
  design that also wants low via resistance/inductance on power paths); the 0.8mm/0.4mm family needs
  to grow to ≈1.31mm pad or an equivalent drill reduction. This does **not** touch any IPC-2221B
  current-capacity derivation in `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §5 (via sizing there is
  driven by current, and none of the current-capacity table's requirement changes) — it is a pure
  manufacturability fix to via geometry, independent of the trace-width math.
- **Item 6 (`hole_clearance`, 90/90).** `scripts/generate_kicad_dru.py`'s "Via hole clearance" rule
  needs to move from 0.25mm to at least JLCPCB's 0.28mm absolute minimum (0.35mm recommended is safer
  and matches what a real DFM reviewer would ask for) — this is a pure DRU-rule-value correction, not a
  copper-weight-dependent one (§7.4 notes the repo's own 0.25mm is below JLCPCB's floor at 1oz too).
- **Item 2 (`clearance`, 145 of 1,085).** No IPC-2221B current-capacity derivation changes: these are
  spacing (isolation) violations, not width (current-carrying) ones. Fixing the 145 genuinely
  fab-blocking ones is a router congestion-relief problem in the affected areas, not a net-class-width
  redesign. The remaining 940 stay exactly what they already were — real findings against this repo's
  own IEC-60335 safety figures, unaffected by anything in this document (per the hard constraint: a
  looser fab floor is never grounds to relax them).
- **Item 8 (`solder_mask_bridge`, 145/145).** These are the same congested locations largely
  responsible for item 2 (both driven by the same `pad_to_mask_clearance=0` copper geometry) —
  resolving the router congestion that produces item 2's fab-floor failures should resolve most of
  these simultaneously, though the two categories were not proven to be the identical location set
  (§7.3), only strongly correlated by count and by shared root cause.
- **`trace_width_assignment.py`'s 0.127mm default and the `FinePitch`/`Differential` netclass values**
  should be raised to at least 0.15mm/0.15mm **before** any future routing pass could place them on a
  2oz-declared layer — currently latent (§5), not urgent, but a real trap for the next router run if
  left unaddressed alongside a stackup that finally declares 2oz.
- **Item 11 (no declared stackup).** This is the highest-leverage single fix: until a real
  `board.design_settings.stackup` exists in `pcb/temper.kicad_pro` naming 2oz outer / (1oz or 2oz)
  inner explicitly, every current-capacity number in `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` is
  contingent on a fab order-form note that nothing in the repo enforces or even records happened. This
  is a documentation-to-artifact gap, not a geometry failure, and it is arguably more consequential
  than any single trace-width number: a correct width at the wrong copper weight silently produces the
  wrong current capacity.
