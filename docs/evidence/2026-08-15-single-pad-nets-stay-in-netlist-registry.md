<!-- provenance: branch=fix/acl-single-pad-net-parser base=origin/main (9898dc813) dirty=false -->

# Single-pad nets stay in the netlist registry (parser contract change)

**Date:** 2026-08-15
**Branch:** `fix/acl-single-pad-net-parser`
**Blocked-by-this:** PR #1178 and descendants (#1200, #1204, #1205, #1206,
#1210, #1201) — `test_apply_net_class_mapping_strict` failed on them with
`ac_l` no longer a parsed net.

## 1. Symptom

`Netlist.apply_net_class_mapping_strict` (Rust, `netlist_contracts.rs`)
raised `ValueError` naming `ac_l` as an unresolved key on the PR #1178
lineage. On those branches `ac_l` is a **single-pad net** (F1 pin 1 only):
the authorized ZCD orphan-footprint removal (and the board resync) deleted
the second `ac_l` pad (R6 pin 1 on main).

## 2. Root cause

`extract_nets_pure` (Rust, `packages/temper-design-bundle/src/parse_engine.rs`,
ported from the pre-migration Python `_extract_nets_from_pcb`) dropped nets
with fewer than 2 pins:

```python
return [n for n in nets_dict.values() if len(n.pins) >= 2]   # pre-migration
```

This filter was ported faithfully — it is not a porting defect. It was the
pre-migration *behavior*, and it erases real electrical entities from the
netlist registry. A single-pad net still carries a net class assignment
(DRC, DRU emission, safety classification) and still needs to resolve in
`apply_net_class_mapping_strict` — the very check `temper_constraints.yaml`'s
`net_classes:` keys (10 keys, including `ac_l: ACMains`) are validated
against. On main the drop was latent: `ac_l` had 2 pads, and the strict
mapping happened to resolve every config key. The ZCD removal turned `ac_l`
single-pad and the latent gap became a hard failure.

Measured on main's board before the fix: **29 of 139 distinct nets are
single-pad** (`usb_dn`, `tx`, `rx`, `rtd_force_n`, `gpio18`, …) — all were
silently missing from the parsed netlist (110 nets). The board was already
losing a fifth of its nets to this filter.

## 3. Fix (parser-level, board-independent)

1. `extract_nets_pure` now retains every named net (>= 1 pin). A net is
   created only when a pin names it, so the registry is exactly the pin
   census: no net is invented, none is dropped.
2. The pinned parse-engine oracle
   (`tests/io/_parse_engine_py_oracle/_parse_nets.py`) changed **in
   lockstep** so the R1a differential (`test_parse_engine_rust_differential.py`)
   stays a parity check rather than asserting the pre-migration drop. Same
   precedent as the documented 0.25 → 0.20 `default_trace_width` correction
   in that file ("a deliberate value correction has to be made on both sides
   or the differential starts asserting the defect"). These oracle files are
   not content-hash pinned (`_parse_nets.py` does not match the
   `_*_py_oracle.py` glob in `scripts/check_oracle_hashes.py`), so no
   re-pin was required.
3. Routing is untouched: `router_v6.routing_space._routable_net_names`
   already requires >= 2 pins, `_pipeline_route` skips nets with < 3
   terminals, and completion rate is computed from per-net routing reports
   (single-pad nets never get one), so routing sets and rates are
   byte-identical.
4. P2 property test re-specified from "nets have >= 2 pins" to the new
   contract (registry == pin census, >= 1 pin, non-empty names, and an
   anti-vacuity assertion that corpora known to carry single-pad nets
   actually retain one). The re-spec is not a weakening: the new property is
   strictly stronger for the new contract and would catch a drop regression.

## 4. Verification

| Check | Result |
|---|---|
| `test_apply_net_class_mapping_strict` (10 tests) | pass |
| `test_parse_engine_rust_differential` (R1a parity, 58) | 55 pass / 3 pre-existing skips |
| `test_parse_engine_pbt` (41) | pass |
| `tests/io/` full suite | 961 pass; 2 pre-existing env failures (no `KICAD7_FOOTPRINT_DIR` on this machine — fail identically on main checkout) |
| `tests/validation/` | 2046 pass; 9 failures all pre-existing/env (mfem binary, thermal battery, DRC validator availability, atopile `elec/build/default.net` artifact — 8 confirmed identical on main checkout) |
| `tests/core/` net-class/netlist/net-order (287) | pass |
| deterministic net-order + integration roundtrip | pass |
| `cargo check --tests --features python` | compiles (unit test added for single-pad retention; cannot *link* under `cargo test` — pre-existing dormant-tests condition, `extension-module` in pyo3 features, handoff §5) |
| import linter | 0 new violations |
| oracle hash gate | pre-existing 2-drift (same on main checkout) |

Scenario check (the blocked branches): `ac_l` parses as single-pad (F1-1)
on `origin/fix/zcd-orphan-footprint-removal`,
`origin/fix/layer-architecture-ssot`, and `origin/fix/router-nlayer-routing`;
the strict mapping applies all 10 config keys and lands `ac_l` on
`ACMains` on all three boards, and on main's board (where `ac_l` still has
2 pads).
