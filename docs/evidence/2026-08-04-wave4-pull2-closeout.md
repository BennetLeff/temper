# Wave-4 Pull-2 Closeout Record (U7)

**Date:** 2026-08-04
**Plan:** `docs/plans/2026-08-03-003-feat-wave4-phase3-first-pulls-plan.md` (U7)

## Catalog-to-pin cross-check (R11/R13)

Every pattern class in the committed catalog
(`packages/temper-design-bundle/VERIFICATION.md`, "Board/Netlist
consumer-semantics catalog") carries a differential pin in
`test_board_rust_differential.py` or `test_netlist_rust_differential.py`:

| Catalog pattern class | Pin |
|---|---|
| Container iteration | element-tuple canonicalization in `_board_canonical`/`_netlist_canonical` |
| `len()` / integer indexing | Rect tuple drop-in tests; Netlist index/lookup tests |
| Attribute reads | field-by-field canonical parity (all leaf tests) |
| Constructor call sites | identical-kwargs construction parity (full-kwargs fixtures) |
| Getter methods | per-method parity tests (get_zone, get_component, etc.) |
| numpy float32 surface | explicit dtype/shape assertions (KTD6) |
| `compute_eigenvector_centrality` | never gated (R10); shim delegation exercised |
| `find_isomorphic_groups` | shim delegation path (KTD7) |
| repr/str (B9/B10) | repr byte-parity asserted on every class |
| LayerIndex IntEnum | member/str/repr/from_name/value-construction identity; KTD2 deviations adapted in-PR |
| Identity checks / monkeypatch | 0 sites found in src+tests (catalog records n/a) |

Resolution-order cases (R12/AE1): no pattern required a pyclass compat
surface beyond the ones added (LayerIndex value construction, `ref`
keyword, dynamic attributes, field-based eq/hash); no R3 JUSTIFIED-KEEP
was needed. Every consumer adaptation landed inside the migration PRs.

## Perf A/B evidence (R5/KTD9)

Both pulls' mandatory performance A/B is covered by the delegation
carve-out record
(`docs/evidence/2026-08-04-wave4-slice-delegation-perf-carveout.md`):
pure-delegation surfaces carry "no regression beyond noise" with the
landed noise-floor evidence (n=19 CI deltas, worst 9.9%; n=20 ratio runs,
worst 7.72%) as calibration, and the existing `perf_ab.py` harness runs
unchanged. No margin re-tuning; the trigger condition for extending the
harness is recorded.

## Doc-path inventory (L2, shim-then-delete learning)

41 docs cite the pre-migration module paths (`core/board.py`,
`core/netlist.py`, `io/netclass_loader.py`, `io/loop_loader.py`). These
are overwhelmingly historical point-in-time records (evidence docs and
plans describing the pre-migration state) and are left intact — the
shim-then-delete lesson concerns current-guidance anchors surviving
deletion, which applies at the eventual delete phase, not the shim phase.
The migration PRs introduced no new stale anchors. At the delete phase,
this inventory is the starting grep.

## Pre-existing main debt observed during the sweep (not this slice's)

- `placer/deterministic.py::place_by_proximity` with `zone_name=None`
  places nothing (logic inside `if zone_name:`) — zero diff vs
  origin/main, mock-based test — placer/Phase-5 territory.
- `tests/validation/test_mfem_runner.py` requires the MFEM binary at
  `/tmp/mfem_tempsolve` (environment artifact).
- `tests/validation/test_ucc21550_contract_pbt.py` asserts a connection
  against `elec/src/modules.ato` that the current file no longer
  contains — elec/src is board-workstream territory (read-only for this
  program).
