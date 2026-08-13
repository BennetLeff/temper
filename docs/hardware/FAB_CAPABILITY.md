# Fabricator Capability Envelope (JLCPCB, primary target)

**Status:** Proposed single source of truth for real manufacturing limits.
**Full derivation, board measurement, and verdicts:**
`docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md` — read that
document before changing anything here; this file is the condensed
reference table it produced, not independent analysis.

No fabricator was named anywhere in this repo before this document. Every
geometry figure in `docs/hardware/TRACE_WIDTH_CALCULATIONS.md`,
`scripts/generate_kicad_dru.py`'s `DEFAULT_ROUTING_CLEARANCE_MM`, and
`packages/temper-placer/.../trace_width_assignment.py`'s trace-width
defaults was derived from generic IPC-2221B, not checked against any real
fab's published minimum. This file exists so the next geometry decision has
something real to check against.

## Why JLCPCB, and why 2oz matters

The user selected a mainstream high-volume house ("JLCPCB or something"),
not a specialist. This board is designed around **2oz (70µm) outer
copper** (`docs/specs/PCB_SPECIFICATION.md` §3.1, §12.2;
`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §1). A fab's headline
trace/space figure is almost always a **1oz** number — heavier copper
etches with more lateral undercut, so the real minimum at 2oz is larger.
Every figure below is the **2oz-specific** number where JLCPCB publishes
one, not the 1oz headline.

## 1. JLCPCB — sourced capability table

Source: <https://jlcpcb.com/capabilities/pcb-capabilities> (fetched
2026-08-13; live/self-updating page, no version number or last-modified
date shown — re-verify before relying on this table for a real order).
Supplementary: <https://jlcpcb.com/help/article/jlcpcb-copper-weight>,
<https://jlcpcb.com/help/article/UL-Certification>,
<https://jlcpcb.com/pcb-fabrication/fr4-pcb> (all fetched 2026-08-13).

| # | Parameter | 1oz (multilayer) | **2oz (multilayer) — this board's copper weight** | Notes |
|---|---|---|---|---|
| 1a | Min. track width & spacing | 0.09 / 0.09 mm (3.5 / 3.5 mil) | **0.15 / 0.15 mm (6 / 6 mil)** | 2-layer-only figures (0.16mm@2oz, 0.2mm@2.5oz...) do not apply — this is a 4-layer board |
| 1b | Outer copper weight options | 1oz | **1oz, 2oz** (standard, not special-order) | Multilayer maxes at 2oz; 2.5–4.5oz are 2-layer-only. "1oz, 2oz (standard)" per the copper-weight help article |
| 1c | Inner copper weight options | — | 0.5oz (**default**), 1oz, 2oz | This board's docs assume 1oz inner — must be an explicit order note, not the default |
| 2a | Min. PTH annular ring | Recommended ≥0.20mm; absolute min 0.15mm | **0.254mm or above** (no separate "absolute minimum" published for 2oz) | Same figure for 2-layer and multilayer |
| 2b | Min. drill diameter | 0.15mm (2+ layer; "more costly") | 0.15mm | Not broken out by copper weight |
| 2c | Min. hole-to-copper | PTH-to-track: 0.28mm abs. min, 0.35mm recommended; via-hole-to-copper: 0.2mm; inner PTH-pad-hole-to-copper: 0.3mm | not broken out by copper weight | |
| 3 | 2oz on a 4-layer board | — | **Standard capability**, not an "Advanced" tier item | "Advanced options such as ... heavy copper (up to 3oz) ... require DFM review" — that sentence's "heavy copper" is the 2-layer-only 2.5–4.5oz tier, not this board's 2oz/4-layer combination |
| 4 | Inner copper for current capacity | 0.5oz default, 1oz/2oz available | Order must say "1oz inner" explicitly | If left at JLCPCB's default (0.5oz), IPC-2221B current-capacity derivations assuming 1oz internal copper are invalid |
| 5a | Min. board-edge-to-copper (routed) | ≥0.2mm | not broken out by copper weight | |
| 5b | Min. board-edge-to-copper (V-cut) | ≥0.4mm | | |
| 5c | Min. plated slot width | 2-layer 0.5mm; multilayer **0.35mm** | | Slot length ≥2× width |
| 5d | Min. non-plated slot width | 1.0mm | | |
| 6a | Laminate | FR-4, Grade A (Nan Ya / KB / Shengyi) | | Dielectric constants 4.1–4.5 depending on prepreg |
| 6b | UL94 rating | V-0 (stated on JLCPCB's FR4 marketing/blog pages; **not printed on the capabilities page itself**) | | UL file **E479892**; classes JLC-1/JLC-4 cover FR-4 multilayer (4–32 layers) |
| 6c | Material certification per order | **Not confirmed.** JLCPCB links generic material datasheets and an ISO9001/14001/RoHS/REACH "Certifications Center"; no published statement of a per-order Material Test Report / Certificate of Conformance | | Would need to be requested directly from JLCPCB support — do not assume it exists |
| 7a | Solder mask min. dam/bridge width | 1oz: 0.10mm (color), 0.13mm (black/white) | **2oz: 0.20mm (any color)** | |

## 2. Named alternatives — where they differ materially

| Fab | 2oz outer, multilayer, min trace/space | Source |
|---|---|---|
| **JLCPCB** (primary target) | **0.15 / 0.15 mm (6/6 mil)** | jlcpcb.com/capabilities/pcb-capabilities, fetched 2026-08-13 |
| PCBWay | Not broken out by copper weight on their own capabilities page (general min 0.1mm/4mil quoted without an oz qualifier); their dedicated "min track/spacing by copper weight" help page exists but its numbers are embedded in images, not extractable as text | pcbway.com/capabilities.html; pcbway.com/helpcenter/.../What_is_the_Min_Track_Spacing... (fetched 2026-08-13, both) |
| Advanced Circuits / AdvancedPCB (US, specialist-adjacent) | **0.007in / 0.007in (7/7 mil) Standard tier**; 0.0055in (Advanced tier); 0.004in (Development tier, premium) | advancedpcb.com/en-us/resources/pcb-capabilities-and-expanded-capabilities/, fetched 2026-08-13 |

Advanced Circuits' **Standard** tier at 2oz (7/7 mil) is materially *looser*
than JLCPCB's 2oz multilayer figure (6/6 mil) — i.e. JLCPCB's mainstream
tier is tighter than a US specialist's standard tier here. Do not assume
"specialist == tighter" without checking; it depends on the tier compared.

## 3. Board's own declared copper weight — a gap, not just a number

`pcb/temper.kicad_pcb` has **no `(stackup ...)` block** and
`pcb/temper.kicad_pro`'s `board` key has **no `stackup` field at all**
(verified directly against both files, resync-branch commit `a3fbaff37`).
Nothing in the actual KiCad project — the artifact that would be exported
to Gerbers and sent to a fab — declares 2oz copper anywhere. The 2oz
assumption exists only in `docs/specs/PCB_SPECIFICATION.md`,
`docs/hardware/TRACE_WIDTH_CALCULATIONS.md`, and code comments. If this
project were exported and ordered today without a manual order-form
override, JLCPCB would build it at whatever their instant-quote configurator
defaults to — not necessarily 2oz. See the evidence doc §3 for the full
argument and the internal doc-vs-doc disagreement this uncovered (whether
the bottom/control layer is 1oz or 2oz).

## 4. Repo values that must move if 2oz is confirmed as the real target

See the evidence doc §6–7 for the measured board comparison this table
summarizes.

| Repo value | Value | vs. JLCPCB 2oz floor | Verdict |
|---|---|---|---|
| `scripts/generate_kicad_dru.py: DEFAULT_ROUTING_CLEARANCE_MM` | 0.2mm | floor is 0.15mm | **PASS** (0.05mm margin) |
| `trace_width_assignment.py: default_width` ("5mil standard") | 0.127mm | floor is 0.15mm | **FAIL** — below floor; not currently used by any routed track on the real board, but latent |
| `netclass_rules.yaml` / `pcb/temper.kicad_pro`: `FinePitch`, `Differential` `trace_width` | 0.127mm | floor is 0.15mm | **FAIL** — below floor |
| `netclass_rules.yaml` / `pcb/temper.kicad_pro`: `FinePitch`, `Differential`, "Same footprint pads" `clearance` | 0.1mm | floor is 0.15mm | **FAIL** — below floor (unchanged by this fix; out of scope, see below) |
| Board's actual via geometry (was 0.4mm/0.2mm and 0.8mm/0.4mm size/drill) | **FIXED 2026-08-13**: now 0.8mm/0.2mm and 1.0mm/0.4mm (0.3mm ring, both families) | floor is 0.254mm | **PASS** (0.046mm margin) — all 44 vias on the board, plus every `TEMPER_NET_CLASSES`/`netclass_rules.yaml`/`pcb/temper.kicad_pro` via template raised in lock-step so a future route does not regress. See `docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md` §9 and this fix's own PR. |
| `scripts/generate_kicad_dru.py`: "Via hole clearance" rule | **FIXED 2026-08-13**: now 0.28mm | JLCPCB PTH-to-track absolute min is 0.28mm | **PASS** — raised to the fab floor exactly (not the 0.35mm recommended figure — see the rule's own derivation comment for why). This does not, by itself, fix the 90 pre-existing `hole_clearance` findings (hole-to-*neighboring-copper* congestion, a routing problem, not a via-pad-vs-own-drill geometry problem) — those remain scoped to the router-congestion/rerouting effort. |

The `FinePitch`/`Differential` `trace_width`/`clearance` latent-risk rows above are unchanged by this fix — they govern trace geometry, not via annular ring or hole-to-copper spacing, and are explicitly out of this fix's scope (see the fix's own PR description).

---

## 5. Machine-readable summary (gate input)

**This fenced block is the single source of truth `scripts/check_fab_capability_floor.py`
parses at CI time** — it is not independent of the cited table above, it is
the same §1 figures in a form a script can load without regexing prose.
Keep both in sync: a change to any figure below must also update the
matching row in §1 (and vice versa), same convention as this repo's other
generated-from-declared pairs (e.g. `netclass_rules.yaml` vs
`pcb/temper.kicad_pro`).

```yaml
# JLCPCB, 2oz outer multilayer (this board's declared copper weight, §3).
# Every key here traces to a §1 table row; see that row for citation.
jlcpcb_2oz_multilayer:
  min_annular_ring_mm: 0.254          # §1 row 2a
  min_hole_to_copper_pth_to_track_abs_min_mm: 0.28    # §1 row 2c
  min_hole_to_copper_pth_to_track_recommended_mm: 0.35  # §1 row 2c
  min_hole_to_copper_via_to_copper_mm: 0.2            # §1 row 2c
  min_drill_mm: 0.15                  # §1 row 2b
  min_track_width_mm: 0.15            # §1 row 1a
  min_track_spacing_mm: 0.15          # §1 row 1a
  min_solder_mask_dam_mm: 0.20        # §1 row 7a
  min_board_edge_to_copper_routed_mm: 0.2   # §1 row 5a
  min_plated_slot_width_mm: 0.35      # §1 row 5c
```
