"""Tests for check_ipc2221b_trace_width_floor.py.

Three groups:

1. ``TestRealRepoIntegration`` -- the gate passes clean against the real,
   live repo state as of this commit: `hb-gnd`'s production-assigned
   width (via the real `assign_trace_widths` entrypoint) meets its
   IPC-2221B requirement.
2. ``TestCatchesRegression`` -- the falsifier this gate exists for: wiring
   `find_violations` to a *pre-fix* `assign_trace_widths` substitute
   (one that calls the plain, keyword-only `_determine_trace_width`
   instead of `_determine_trace_width_ipc_aware`) reproduces the exact
   defect PR #1187's follow-up fixes -- `hb-gnd` assigned 0.508mm against
   a ~4.77mm requirement -- and proves the gate flags it.
3. ``TestAntiVacuity`` -- an empty net-current registry is itself treated
   as a violation, not a silent pass (see the module docstring: a check
   with nothing to check is the same failure shape as an unregistered
   gate, just inverted).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_ipc2221b_trace_width_floor import (  # noqa: E402
    EXIT_OK,
    EXIT_VIOLATION,
    find_violations,
    main,
)


class TestRealRepoIntegration:
    def test_gate_passes_clean_against_real_repo(self):
        violations, net_names = find_violations()
        assert net_names, "expected at least hb-gnd to be registered"
        assert violations == [], f"unexpected violations against live repo state: {violations}"

    def test_hb_gnd_is_the_registered_net(self):
        _violations, net_names = find_violations()
        assert "hb-gnd" in net_names

    def test_main_exits_ok(self):
        assert main() == EXIT_OK


class TestCatchesRegression:
    """Reconstructs the exact pre-follow-up-fix defect and proves this
    gate would have caught it: `hb-gnd` assigned via the plain,
    keyword-only classifier (0.508mm) against its real ~4.77mm IPC-2221B
    requirement (10-22.5A RMS, 40 degC rise, 2oz external -- see
    `packages/temper-geometry/src/ipc2221b_current_width.rs`).
    """

    @staticmethod
    def _pre_fix_assign_trace_widths(pathfinding_result, default_width, power_width, hv_width):
        """Reproduces `assign_trace_widths` wired to the OLD, keyword-only
        `_determine_trace_width` (pre this fix's `_determine_trace_width_ipc_aware`
        wiring) -- i.e. the exact production call chain PR #1187 left in
        place, still short of the current-derived requirement.
        """
        from temper_placer.router_v6.trace_width_assignment import (
            TraceWidthAssignment,
            _determine_trace_width,
        )

        assignments = {}
        routed_net_names = (
            set(pathfinding_result.routed_paths)
            | set(pathfinding_result.partial_paths)
            | set(pathfinding_result.tree_routes)
            | set(pathfinding_result.partial_tree_routes)
        )
        for net_name in routed_net_names:
            assignments[net_name] = _determine_trace_width(net_name, default_width, power_width, hv_width)
        return TraceWidthAssignment(assignments=assignments)

    def test_pre_fix_wiring_is_flagged(self):
        violations, net_names = find_violations(assign_fn=self._pre_fix_assign_trace_widths)
        assert net_names == ["hb-gnd"]
        assert len(violations) == 1
        v = violations[0]
        assert v.net_name == "hb-gnd"
        assert v.assigned_width_mm == 0.508
        assert v.required_width_mm > 4.5, f"expected ~4.77mm requirement, got {v.required_width_mm}"
        assert v.assigned_width_mm < v.required_width_mm

    def test_main_would_exit_violation_for_pre_fix_wiring(self, monkeypatch):
        import check_ipc2221b_trace_width_floor as gate_module

        original_find_violations = gate_module.find_violations

        def patched(*_args, **_kwargs):
            return original_find_violations(assign_fn=self._pre_fix_assign_trace_widths)

        monkeypatch.setattr(gate_module, "find_violations", patched)
        assert gate_module.main() == EXIT_VIOLATION


class TestAntiVacuity:
    def test_empty_registry_is_a_violation_not_a_silent_pass(self, monkeypatch):
        import check_ipc2221b_trace_width_floor as gate_module

        class _FakeTg:
            @staticmethod
            def known_net_current_names_py():
                return []

        monkeypatch.setitem(sys.modules, "temper_geometry", _FakeTg())
        assert gate_module.main() == EXIT_VIOLATION

    def test_missing_registry_entry_is_a_violation(self):
        """`known_net_current_py` disagreeing with
        `known_net_current_names_py` (a registry-internal-consistency bug)
        must fail closed, not skip the net silently."""

        @dataclass
        class _FakePathfindingResult:
            routed_paths: dict
            failed_nets: list

        class _FakeWidthAssignment:
            def get_width(self, _net_name):
                return 999.0  # would otherwise pass -- must not matter

        def fake_assign_fn(_result, **_kwargs):
            return _FakeWidthAssignment()

        import temper_geometry as real_tg

        class _PartiallyBrokenTg:
            known_net_current_names_py = staticmethod(real_tg.known_net_current_names_py)

            @staticmethod
            def known_net_current_py(_name):
                return None  # registry drift: name listed, entry missing

        import sys as _sys

        _sys.modules["temper_geometry"], saved = _PartiallyBrokenTg(), _sys.modules.get("temper_geometry")
        try:
            from check_ipc2221b_trace_width_floor import find_violations as fv

            violations, net_names = fv(assign_fn=fake_assign_fn)
            assert net_names
            assert len(violations) == len(net_names)
        finally:
            if saved is not None:
                _sys.modules["temper_geometry"] = saved
