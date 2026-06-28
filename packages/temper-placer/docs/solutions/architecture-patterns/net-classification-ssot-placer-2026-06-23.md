---
title: "Net Classification Single Source of Truth in the Placer"
date: "2026-06-23"
category: architecture-patterns
module: routing/net_classification
problem_type: architecture_pattern
component: routing
severity: medium
applies_when:
  - Adding a new net classification check anywhere in the placer codebase
  - Adding new net-name or pin-name patterns (ground, power, HV, clock)
  - Auditing code for duplicate pattern lists
tags: [net-classification, routing, power-nets, ground-nets, hv-nets, ssot, consolidation]
---

# Net Classification Single Source of Truth in the Placer

## Context

The placer codebase had 20+ duplicate, slightly divergent lists of power/ground/HV net-name patterns
scattered across `core/`, `routing/`, `router_v6/`, `heuristics/`, `losses/`, `io/`, `experiments/`,
and `deterministic/`.  Each list encoded its own slight variation:

- Some used substring match, others exact match.
- Some included "GND" in the power-keywords list (a bug in `channel_mapping.py:37`).
- `PLANE_NETS` (13 exact names), `TEMPER_PLANE_NETS` (12 exact names), and
  `PLANE_NET_PATTERNS` (13 substring patterns) were three public constants with
  overlapping but non-identical contents.
- Pin-name patterns in `critical_net_detector.py` were broader than the
  canonical sets, including entries like "VBAT", "VCC_IN", "0V".

Adding a new net to a pattern required edits in multiple unrelated files.
Audits invariably found drift.

## Guidance

### Canonical surface

**Module:** `routing/net_classification.py`

**Net patterns** (matched case-insensitive, substring, precedence: ground > power > hv > signal):

| Constant | Values |
|----------|--------|
| `GROUND_NET_PATTERNS` | `{"GND", "PGND", "CGND", "AGND", "DGND", "VSS"}` |
| `POWER_NET_PATTERNS` | `{"+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"}` |
| `HV_NET_PATTERNS` | `{"AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"}` |

**Helpers:**

- `is_ground_net(name)` / `is_power_net(name)` / `is_hv_net(name)` / `is_signal_net(name)`
- `classify_net_type(name)` → one of `"ground"`, `"power"`, `"hv"`, `"signal"`

**Pin patterns** (matched case-insensitive, substring — distinct from net patterns):

| Constant | Values |
|----------|--------|
| `GROUND_PIN_PATTERNS` | `{"GND", "VSS", "AGND", "DGND", "PGND", "CGND"}` |
| `POWER_PIN_PATTERNS` | `{"VCC", "VDD", "VIN", "VOUT", "PVCC", "VBUS", "PWR"}` |
| `HV_PIN_PATTERNS` | `{"AC_L", "AC_N", "PE", "HV", "MAINS", "RECT"}` |
| `CLOCK_PIN_PATTERNS` | `{"CLK", "CLOCK", "XTAL1", "XTAL2", "OSC_IN", "OSC_OUT"}` |

**Helpers:** `is_ground_pin(name)` / `is_power_pin(name)` / `is_hv_pin(name)` / `is_clock_pin(name)`

### How to use

```python
from temper_placer.routing.net_classification import is_power_net, is_ground_net

# Instead of:
#   power_patterns = ["VCC", "VDD", "+3V3", "+5V"]
#   if any(p in net_name.upper() for p in power_patterns):
if is_power_net(net_name):
    ...
```

**In modules that share a public function name with a helper** (e.g., `io/net_class_manager.py`
already defines `is_power_net`), alias the import to avoid shadowing:

```python
from temper_placer.routing.net_classification import (
    is_power_net as _is_power_net,
    is_ground_net as _is_ground_net,
)

def is_power_net(net_name: str) -> bool:
    """Check if net is a power/ground net."""
    return _is_ground_net(net_name) or _is_power_net(net_name)
```

**In modules with a `core → routing` circular-import risk** (e.g., `core/design_rules.py`,
`routing/constraints/design_rules.py`), use function-level imports:

```python
def _is_ground_net(self, net_name: str) -> bool:
    from temper_placer.routing.net_classification import is_ground_net
    return is_ground_net(net_name)
```

### What was removed

Three public constant sets that were duplicates of the canonical patterns:

| Constant | Module | Status |
|----------|--------|--------|
| `PLANE_NET_PATTERNS` | `deterministic/stages/via_validation.py` | **Removed** — 13 patterns, identical to `GROUND_NET_PATTERNS ∪ POWER_NET_PATTERNS` |
| `PLANE_NETS` | `router_v6/routing_space.py` | **Removed** — 13 exact names, replaced by `is_*_net` helpers in all call sites |
| `TEMPER_PLANE_NETS` | `deterministic/stages/power_plane.py` | **Kept** for backward compatibility (test asserts exact equality with a 12-name set) |

### Intentionally NOT migrated

Some files use pattern lists that are *intentionally* different from net classification.
These are not duplicates and should not be migrated:

| File | Pattern list | Why distinct |
|------|-------------|--------------|
| `heuristics/structural.py:279-281` | Net power patterns (VIN, VBUS, +12V, +24V, +48V, DC_IN) | Broader set distinguishing power_input from power_output |
| `heuristics/style.py:52` | `power_patterns` regex list | Component reference patterns (Q1, U_BUCK, L1, etc.), not net names |
| `heuristics/force_directed.py:34` | `DEFAULT_NET_CLASS_WEIGHTS` | Weight map for graph construction, not a classifier |
| `losses/enhanced_congestion.py:114` | Criticality patterns with weights | Tiered criticality scoring (power=5.0, gate_drive=4.0, high_current=3.0, analog=2.0) |
| `routing/pdn_router.py:192` | Pin input indicators | Broader pin-power check (includes PWR, POWER, V+, VBAT) |
| `routing/post_processing/trace_ballooner.py:26-44` | `POWER_NET_KEYWORDS` | High-current trace set (MOTOR, HEATER, PWM, INPUT, OUTPUT) — thermal management concept |
| `routing/critical_net_detector.py:168-198` | Class-level `POWER_PIN_PATTERNS`, `GROUND_PIN_PATTERNS`, `CLOCK_PIN_PATTERNS` | Broader than canonical pin patterns (includes "VBAT", "POWER", "V+", "VCC_IN", "VCC_OUT", "0V"); class allows user override at construction |
| `deterministic/stages/zone_aware_slot_generation.py:39-66` | `POWER_NET_NAMES` | 28 exact-match names (includes "3V3", "5V", "12V" without "+" prefix) |
| `experiments/feedback_effectiveness.py:55` | `target_nets` set | Test-only hardcoded net names for an experiment fixture |

## Why This Matters

**Before**: A new power-rail naming convention (e.g., "+24V") required edits in ~15 files.
A bug in one list (e.g., "GND" in the power keywords) could go unnoticed for months.

**After**: Patterns live in one file. Adding a pattern requires one edit. The 20+ call sites
pick it up automatically. The substring-match semantic correctly classifies nets like
"GND_ANA" and "+3V3_AUX" that exact-match sets would miss.

## When to Apply

- **When adding a new net-name pattern** (e.g., a new voltage rail): add it to the
  appropriate frozenset in `routing/net_classification.py`. All call sites pick it up.
- **When you find a local pattern list in the codebase that looks like it classifies nets**
  (anything with words like "GND", "VCC", "+3V3", etc.): check whether it's already covered
  by the canonical helpers. If yes, migrate it. If the list includes non-net concepts
  (component references, criticality weights), it's intentionally distinct — leave it.

## Examples

### Before (duplicate list in heuristics.py)

```python
def is_power_net(net_name: str) -> bool:
    power_names = ["VCC", "VDD", "3V3", "5V", "12V", "VBUS", "VBAT", "V+"]
    return any(name in net_name.upper() for name in power_names)

def is_ground_net(net_name: str) -> bool:
    ground_names = ["GND", "VSS", "AGND", "DGND", "PGND", "V-"]
    return any(name in net_name.upper() for name in ground_names)
```

### After (delegates to canonical)

```python
def is_power_net(net_name: str) -> bool:
    from temper_placer.routing.net_classification import is_power_net as _is_power_net
    return _is_power_net(net_name)

def is_ground_net(net_name: str) -> bool:
    from temper_placer.routing.net_classification import is_ground_net as _is_ground_net
    return _is_ground_net(net_name)
```

### Bug fix (channel_mapping.py)

**Before** — GND incorrectly treated as a power keyword:

```python
power_keywords = ["GND", "VCC", "VBUS", "+", "PWR", "V+", "V-"]
if any(kw in name_upper for kw in power_keywords):
    return "B.Cu"
```

**After** — ground and power correctly separated:

```python
if is_power_net(net_name) or is_ground_net(net_name) or is_hv_net(net_name):
    return "B.Cu"
```

## Related Documents

- [Layer Index SSOT](layer-index-ssot-placer-2026-06-23.md)
- [Pad Position SSOT](pad-position-ssot-placer-2026-06-23.md)
- [Net Classification Requirements](../../brainstorms/2026-06-23-net-classification-consolidation-requirements.md)
- [Net Classification Plan](../../plans/2026-06-23-011-refactor-net-classification-consolidation-plan.md)
