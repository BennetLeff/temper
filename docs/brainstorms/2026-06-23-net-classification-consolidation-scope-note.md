---
date: 2026-06-23
topic: net-classification-consolidation-scope-note
status: scope-note (expand when sequenced after docs 1-2)
---

# Net Classification Consolidation (Doc 3 of 4) — Scope Note

## Place in sequence

Doc 3 of 4. Ships after **Doc 1 (Layer Names)** and **Doc 2 (Pad-Position)** because both may be touched by net classification code. The 4-doc sequence is: layer names → pad-position → net classification → A* primitives. Doc 3 is broadest in scope (20+ lists across 7 packages) but is mostly drift-prevention (no real bug, just maintenance burden).

## Audit findings (from /ce-code-simplify consolidation audit)

**20+ distinct lists** defining what counts as power/ground/signal across the codebase:
- `core/net_types.py:283-285` — `ground_patterns` (frozenset), `power_patterns` (frozenset) — most curated
- `core/design_rules.py:252, 264-280` — `ground_patterns` and `power_patterns` lists
- `routing/constraints/design_rules.py:519, 525-537` — duplicate of the above
- `routing/heuristics.py:299, 305` — `power_names`, `ground_names`
- `routing/maze_router.py:5015, 5019` — `_is_power_net` / `_is_ground_net` (private, ~7 power / 6 ground keywords)
- `router_v6/thermal_relief.py:92-104` — `_is_power_net` (4 keywords)
- `router_v6/astar_pathfinding.py:407` — inline `["GND", "VCC", "HV", "AC_", "+", "VBUS"]` (substring)
- `router_v6/channel_mapping.py:37` — `power_keywords = ["GND", "VCC", "VBUS", "+", "PWR", "V+", "V-"]`
- `routing/critical_net_detector.py:168-189` — `POWER_PIN_PATTERNS`, `GROUND_PIN_PATTERNS`, `CLOCK_PIN_PATTERNS`
- `losses/enhanced_congestion.py:114` — `(["GND", "VCC", "VDD", "VSS", "PGND", "CGND", "+"], 5.0)`
- `heuristics/organizational.py:565, 585, 751` — `power_patterns` (multiple)
- `heuristics/style.py:52` — `power_patterns`
- `heuristics/structural.py:279-281, 500` — `power_patterns`
- `heuristics/force_directed.py:34` — `{"GND": 0.3}` (weight dict)
- `routing/c_space_pipeline.py:71-72` — `["VCC", "GND"]`
- `routing/post_processing/trace_ballooner.py:33, 36` — `["VCC", "GND"]`
- `routing/pdn_router.py:194` — `["VCC", "VDD", "VIN", "PWR", "POWER", "V+", "VBAT"]`
- `io/net_class_manager.py:11` — `POWER_KEYWORDS` (15 entries)
- `io/dsn_exporter.py:370` — `power_prefixes = ["GND", "PGND", "CGND", "VCC", "VDD", "DC_BUS", "_PLUS"]`
- `io/zone_manager.py:151-152, 239-240` — `gnd_nets: ("GND",)`, `vcc_nets: ("+15V", "+5V", "+3V3", "VCC")` — duplicate of each other
- `io/config_loader.py:673-678, 761` — inline `if "GND" in upper …`
- `experiments/feedback_effectiveness.py:55` — `{"+340V_BUS", "SW_NODE", "GND", "+15V", …}`
- `deterministic/stages/zone_aware_slot_generation.py:20-32` — `plane_nets` with `["GND", "VCC", "VBUS", "+3V3"]`

**Three existing plane-net sets (already partially consolidated in the simplify pass):**
- `router_v6/routing_space.py:23-37` — `PLANE_NETS` (13 nets, exact match, used by router_v6 to skip routing)
- `deterministic/stages/power_plane.py:26-46` — `TEMPER_PLANE_NETS` (6 nets, exact match, used to mark layer assignments)
- `deterministic/stages/via_validation.py:24-40` — `PLANE_NET_PATTERNS` (13 patterns, substring match)

## Key decisions to make during expansion

- **Canonical home:** extend `core/net_types.py` (which already has `ground_patterns` / `power_patterns` frozensets) with a full `NetClassifier` enum or similar, or create a new `routing/net_classification.py` with helpers.
- **API surface:** helpers like `is_ground(name)`, `is_power(name)`, `is_hv(name)`, `is_skip(name)`, plus the closed-world `PLANE_NETS` from doc 1's neighbor module.
- **Migration strategy:** big-bang (matching doc 1's choice). 20+ lists is a lot but the audit shows they all have similar intent.
- **Conflict resolution:** the lists have drifted. Which one is canonical? The most curated (`core/net_types.py:283-285`) is a likely winner.
- **Whether to merge `PLANE_NETS` into the same module:** yes — they are policy (closed-world override + priority hints) and belong in the same place as the pattern-based helpers.

## Open questions for expansion

- Which file's keyword list is the most accurate? (E.g., is `+3V3` a power net? Some lists say yes, some say no.)
- Should the API expose `is_hv(name)` separately from `is_power(name)`, or combine them? The audit shows HV patterns ("AC_L", "AC_N", "PE", "DC_BUS", "SW_NODE", "+340V") are sometimes a separate category.
- Is there a test that pins down the exact behavior of any of these `is_power_net` / `is_ground_net` implementations? If so, the consolidation can use it as a regression test.
- The `PLANE_NET_PATTERNS` substring-match style in `via_validation.py` is different from the exact-match `PLANE_NETS` in `routing_space.py`. Are these meant to be different, or is one a bug?
