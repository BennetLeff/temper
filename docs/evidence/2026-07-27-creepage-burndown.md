# Creepage burn-down: are the 24 real, durable defects?

<!-- provenance: commit=02e907b9a5e1dbca4eae9a0a53f8a2be6dc862c5 (base), branch creepage-burndown -->

**Date:** 2026-07-27

**Scope:** `docs/evidence/2026-07-27-drc-checks-repaired.md` §3 fixed
`creepage_check.py` from a per-segment-pair over-count (257,597 violations)
down to a per-net-pair count (24, against 180 checks) on one live re-route.
This task's job was **not** to fix more violations first -- it was to make
the measurement trustworthy (route_pcb's completion is non-deterministic
run-to-run) and classify the 24 by origin (placement vs. routing) before
spending any fix effort.

## Falsifier, stated up front

**"These 24 are real, durable, placement-derived defects. If most turn out
to be routing-derived artifacts of a 38.5%-complete route, then this
burn-down is largely premature and the honest deliverable is that finding,
not a reduced number."**

**The falsifier fired, and harder than expected.** Not only are the
violations predominantly routing-derived rather than placement-derived --
the check's own HV-net classifier is independently broken in a way that
makes most of its 16-net "HV" set semantically wrong (SELV/logic nets
matched by accidental substring collision, not real mains/DC-bus
conductors). See §4. The placement layer, checked independently via the
domain-clearance machinery this task was told to prefer, **already reports
zero violations on the current committed board** (§3) -- so there is no
placement-side backlog for this task to fix via `domain_clearance.py`.

---

## 1. Reproduction: exact invocation

```
uv run python3 <harness>.py <run_idx> <out.json>
```

where `<harness>.py` (kept outside the repo, scratch-only) does exactly:

```python
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.netclass_loader import load_netclass_rules
from temper_placer.router_v6.adapter import route_pcb

rules = load_netclass_rules(Path("packages/temper-placer/configs/netclass_rules.yaml"))
parse_result = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
netlist = parse_result.netlist
parsed_stub = type("ParsedStub", (), {"source_path": PCB_PATH, "nets": netlist.nets})()

routing_result = route_pcb(
    parsed_stub, {},
    design_rules=rules.design_rules,
    enable_manufacturing_drc=True,
)
```

`RouterV6Pipeline.run` is monkeypatched (read-only, no source change) to
capture its return value, whose `.manufacturing_report.creepage` carries
the `CreepageReport` (`violations`, `total_checks`, `errored`) -- the same
technique `docs/evidence/2026-07-27-drc-checks-repaired.md` used, because
`route_pcb()` does not itself re-expose the full manufacturing report.

This is the same call shape as
`packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py`
(production board, real netclass rules, no CP-SAT placement --
routing-only pass over the committed board's existing footprint positions)
with `enable_manufacturing_drc=True` added.

---

## 2. Stability: N runs, spread of violation_count and total_checks

<!-- FILLED IN BELOW ONCE RUNS COMPLETE -->

---

## 3. Independent check: is the placement layer already clean?

Before trusting the routing-side `creepage_check.py` number at all, this
task re-ran the **placement-side** domain-clearance check that
`docs/evidence/2026-07-27-domain-clearance-constraint.md` fixed 22->0 on
2026-07-27, directly against the **current** committed board (after `make
netlist` rebuilt `elec/build/default.net` fresh, per METHODOLOGY.md's
staleness warning):

```
$ uv run python -m pytest packages/temper-placer/tests/requirements/safety/test_clearance.py \
    -k test_temper_board_clearance_compliance -q
packages/temper-placer/tests/requirements/safety/test_clearance.py .   [100%]
1 passed, 22 deselected in 0.32s
```

**0 violations, confirmed on this commit, not carried forward from the
prior evidence doc.** This is the component-position-level (courtyard/
center-distance) check governed by `domain_clearance.py` +
`elec/domain_manifest.yaml` + `IEC60335_REQUIREMENTS` -- the exact
machinery this task was told to prefer for placement-derived fixes. It
finds nothing to fix. Any of the 24 `creepage_check.py` violations that
turn out to be placement-derived would represent a **new** disagreement
between this already-verified-clean placement check and the routing-side
DFM check, not a known, already-tracked backlog item.

---

## 4. The HV-net classifier is independently broken (found before the
placement/routing split could even be evaluated cleanly)

`creepage_check.py::_is_high_voltage_net` is a **standalone regex
heuristic**, textually unrelated to `elec/domain_manifest.yaml` (the
hand-reviewed SSOT) or `TEMPER_NET_ASSIGNMENTS` (the netclass SSOT used
elsewhere). Run directly against every net on the current board:

```
$ uv run python3 -c "
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.router_v6.creepage_check import _is_high_voltage_net
pr = parse_kicad_pcb(Path('pcb/temper.kicad_pcb'))
nets = sorted(n.name for n in pr.netlist.nets)
hv = [n for n in nets if _is_high_voltage_net(n)]
print(len(hv), 'of', len(nets))
"
16 of 108
```

The 16 nets the check treats as `hv_net` (the *only* nets that ever anchor
the outer loop of the O(hv_nets x other_nets) sweep):

| Net | Why it matched | `elec/domain_manifest.yaml` domain |
|---|---|---|
| `ac_l` | `AC` word-boundary regex | HV (correct) |
| `ac_n` | `AC` word-boundary regex | HV (correct) |
| `discharge.k_dis1-coil1` | **substring collision**: `COIL1` contains `L1` | SELV |
| `discharge.k_dis1-coil2` | **substring collision**: `COIL2` contains `L2` | SELV |
| `discharge.k_dis2-coil1` | **substring collision**: `COIL1` contains `L1` | SELV |
| `power_in.bypass_relay-coil1` | **substring collision**: `COIL1` contains `L1` | SELV |
| `power_in.bypass_relay-coil2` | **substring collision**: `COIL2` contains `L2` | SELV |
| `safety-line` | **substring collision**: `LINE` keyword (meant for AC line, not a signal named "line") | not declared (safety-logic net) |
| `safety-line-1/2/3` | same | not declared |
| `safety.coil_thermal-line` | same | not declared |
| `safety.ocp-line` | same | not declared |
| `safety.ovp-line` | same | not declared |
| `safety.thermal-line` | same | not declared |
| `safety.uvlo_logic-line` | same | **SELV, explicitly** -- `elec/domain_manifest.yaml` names this exact net and gives a multi-paragraph justification that it is "entirely SELV: the module monitors power_3v3 against the TPS3700's internal bandgap reference, and both its power and sense divider are power.vcc / power.gnd" |

**14 of 16 "hv_net" entries are false positives** -- SELV coil-drive or
internal safety-interlock logic nets, matched by two accidental substring
collisions: `"L1"`/`"L2"`/`"L3"` (meant to catch 3-phase line labels)
appearing inside `"COIL1"`/`"COIL2"`, and `"LINE"` (meant to catch an AC
line net) appearing inside `"...-line"` signal names that the design
itself names descriptively (e.g. `safety.ocp-line` is the OCP fault
signal, not a mains conductor).

**Meanwhile, real HV/mains-adjacent nets are *not* detected at all:**
`+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `GATE_HS`, `GATE_LS`,
`w1_1`, `w1_2`, `+15V_LS`, `zcd`, `a` -- every HV-domain net in
`elec/domain_manifest.yaml` except `ac_l`/`ac_n` -- is missed. (Contrast:
the sibling `clearance_check.py`'s outer HV gate is `["AC_", "HV_",
"HIGH_VOLTAGE", "MAINS"]` -- stricter, and does not hit the `L1`/`L2`/
`LINE` substring collisions, because it never runs its broader
`_classify_net_class` keyword set unless that stricter outer gate already
passed. This bug is specific to `creepage_check.py`, not systemic to the
manufacturing-DRC checks fixed in the prior task.)

Compounding this: `verify_creepage()` is called with no `voltage_ratings`
(`_pipeline_verify.py`'s `_run_manufacturing_drc` passes only
`routing_results`), so `hv_voltage = voltage_ratings.get(hv_net, 230.0)`
defaults **every** anchor net -- real or misclassified -- to 230V,
i.e. a flat 3.2mm requirement, regardless of the net's actual working
voltage.

**Consequence for the 24:** any violation whose `hv_net` is one of the 14
false-positive entries is not a mains-creepage defect at all -- it is two
low-voltage/SELV conductors, one of them misidentified by a regex bug,
being held to a 3.2mm mains-isolation bar they were never subject to. This
is a **third bucket**, distinct from placement-derived and
routing-derived, and it is proven by an independent, human-reviewed
document (`elec/domain_manifest.yaml`) disagreeing with the check's own
classifier -- the METHODOLOGY.md Sec 5 "Contradiction" falsification axis,
not a threshold tune.

---

## 5. Per-violation origin classification

<!-- FILLED IN BELOW ONCE RUNS COMPLETE -->

### Method

For each `(hv_net, lv_net)` pair the live run(s) flagged, compute the
**pad-to-pad geometric floor**: the minimum Euclidean distance between any
pad belonging to `hv_net` and any pad belonging to `lv_net`, using the
board's placement (component positions are identical across every routing
run -- routing never moves a footprint). This is the hard floor no routing
choice can improve on, because every route must terminate its copper
exactly at these pad locations.

- `floor < required_distance` -> **PLACEMENT-DERIVED**: any route, however
  good, is forced within `floor` mm of the other net right at the pads.
- `floor >= required_distance` -> **ROUTING-DERIVED**: the pads leave
  enough room; this run's specific path chose to bring copper closer than
  necessary somewhere along the way, and a different route could avoid it.

---

## 6. Fix

<!-- FILLED IN BELOW ONCE CLASSIFICATION IS KNOWN -->

---

## UNVERIFIED

- (running list, appended as the task proceeds)
