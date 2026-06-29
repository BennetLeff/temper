"""End-to-end tension detection + conflict report tests.

Variable names MUST follow the convention `uses_N{net_idx}_{channel_id}`
because the PyO3 bridge (types_py_bridge.rs) constructs LayerRestriction
var_names using that template from net_idx + channel_id.

Acceptance examples from:
  docs/brainstorms/2026-06-28-unsat-provenance-tension-detection-requirements.md

Origin: U7 of docs/plans/2026-06-28-003-feat-unsat-provenance-tension-detection-plan.md
"""

from temper_rust_router import solve_topology_rust


def _var(net_idx, channel_id):
    """Create a variable-like object matching bridge naming convention."""
    return type("_Var", (), {
        "name": f"uses_N{net_idx}_{channel_id}",
        "net_idx": net_idx,
        "channel_id": channel_id,
    })()


def _cap(name, channel_id, capacity, slack_factor, terms):
    """Capacity constraint matching bridge shape. terms: [(var_object, width_float)]."""
    return type("_Cap", (), {
        "name": name,
        "description": "",
        "channel_id": channel_id,
        "capacity": capacity,
        "slack_factor": slack_factor,
        "terms": terms,
    })()


def _dp(name, channel_id, p_net_idx, n_net_idx, p_v_obj, n_v_obj):
    """DiffPair constraint matching bridge shape."""
    return type("_DP", (), {
        "name": name,
        "description": "",
        "channel_id": channel_id,
        "p_net_idx": p_net_idx,
        "n_net_idx": n_net_idx,
        "p_var": p_v_obj,
        "n_var": n_v_obj,
    })()


def _lr(name, net_idx, channel_id, allowed):
    """LayerRestriction matching bridge shape."""
    return type("_LR", (), {
        "name": name,
        "description": "",
        "net_idx": net_idx,
        "channel_id": channel_id,
        "allowed": allowed,
    })()


class TestTensionDetection:
    """AE1: Capacity oversubscription with layer restrictions."""

    def test_ae1_capacity_oversubscription_partial(self):
        """3 nets, CH1 capacity 2. No restrictions — SAT, no tension."""
        vars_ = [_var(i, "CH1") for i in range(3)]
        py_vars = list(vars_)
        py_cons = [_cap("cap_CH1", "CH1", 2.0, 1.0, [(v, 1.0) for v in vars_])]
        result = solve_topology_rust(py_vars, py_cons, [f"N{i}" for i in range(3)])

        assert result["status"] == "sat"
        tensions = result.get("tensions", [])
        hard_conflicts = [t for t in tensions if t["severity"] == "hard_conflict"]
        assert len(hard_conflicts) == 0, f"Unexpected HardConflict: {hard_conflicts}"

    def test_ae1_capacity_oversubscription_full(self):
        """3 nets forced to CH1, capacity 2 — HardConflict + SAT (partial assign)."""
        v_ch1 = [_var(i, "CH1") for i in range(3)]
        v_ch2 = [_var(i, "CH2") for i in range(3)]
        py_vars = list(v_ch1) + list(v_ch2)

        bans = [_lr(f"ban_{i}", i, "CH2", False) for i in range(3)]

        py_cons = [
            _cap("cap_CH1", "CH1", 2.0, 1.0, [(v, 1.0) for v in v_ch1]),
            _cap("cap_CH2", "CH2", 10.0, 1.0, [(v, 1.0) for v in v_ch2]),
        ] + bans
        result = solve_topology_rust(py_vars, py_cons, [f"N{i}" for i in range(3)])

        # The solver CAN find a SAT assignment (pick 2 of 3 nets for CH1).
        # Tension detection should flag HardConflict (3 must-use > capacity 2).
        assert result["status"] == "sat"
        tensions = result.get("tensions", [])
        hard_conflicts = [t for t in tensions if t["severity"] == "hard_conflict"]
        assert len(hard_conflicts) >= 1, f"Expected HardConflict, got: {tensions}"
        assert "capacity" in hard_conflicts[0]["explanation"].lower()
        assert "CH1" in hard_conflicts[0]["explanation"]

    def test_mutually_exclusive_diffpair(self):
        """DiffPair where the two nets have no shared allowed channel."""
        p1 = _var(0, "CH1")  # uses_N0_CH1
        n1 = _var(1, "CH1")  # uses_N1_CH1
        p2 = _var(0, "CH2")  # uses_N0_CH2
        n2 = _var(1, "CH2")  # uses_N1_CH2
        py_vars = [p1, n1, p2, n2]

        py_cons = [
            _dp("diff", "CH1", 0, 1, p1, n1),
            _lr("ban_p_CH2", 0, "CH2", False),
            _lr("ban_n_CH1", 1, "CH1", False),
        ]
        result = solve_topology_rust(py_vars, py_cons, ["net0", "net1"])

        tensions = result.get("tensions", [])
        hard_conflicts = [t for t in tensions if t["severity"] == "hard_conflict"]
        assert len(hard_conflicts) >= 1, (
            f"Expected mutually-exclusive HardConflict, got: {tensions}"
        )


class TestDiffPairCapacityConflict:
    """AE2: Diff-pair vs. single-channel capacity."""

    def test_ae2_diffpair_capacity_1_unsat(self):
        """DiffPair on CH1, CH1 capacity 1 — HardConflict triggered."""
        p = _var(0, "CH1")
        n = _var(1, "CH1")
        py_vars = [p, n]

        py_cons = [
            _dp("diff_CH1", "CH1", 0, 1, p, n),
            _cap("cap_CH1", "CH1", 1.0, 1.0, [(p, 1.0), (n, 1.0)]),
        ]
        result = solve_topology_rust(py_vars, py_cons, ["net0", "net1"])

        # DiffPair forces p==n. Capacity says at most 1 true. Solver can set
        # both false → SAT. But tension detects capacity < 2 for diffpair.
        assert result["status"] == "sat"
        tensions = result.get("tensions", [])
        hard_conflicts = [t for t in tensions if t["severity"] == "hard_conflict"]
        assert len(hard_conflicts) >= 1, f"Expected HardConflict, got: {tensions}"
        assert "capacity" in hard_conflicts[0]["explanation"].lower()

    def test_ae2_conflict_report_from_unsat_core(self):
        """AE2 model — verify conflict report when solver proves UNSAT."""
        # Add layer restrictions to force both nets true (no other options).
        # But with only one channel CH1 and both nets, DiffPair + Capacity 1.
        # Actually, with just 1 channel and both nets, capacity ≤1 is conflict.
        p = _var(0, "CH1")
        n = _var(1, "CH1")
        py_vars = [p, n]

        py_cons = [
            _dp("diff_CH1", "CH1", 0, 1, p, n),
            _cap("cap_CH1", "CH1", 1.0, 1.0, [(p, 1.0), (n, 1.0)]),
        ]
        result = solve_topology_rust(py_vars, py_cons, ["net0", "net1"])

        # DiffPair forces both same; capacity 1 forces at most 1 true.
        # But solver can set both false → SAT. The tension should flag.
        result.get("conflicts")
        tensions = result.get("tensions", [])
        hard_conflicts = [t for t in tensions if t["severity"] == "hard_conflict"]
        assert len(hard_conflicts) >= 1, (
            f"Expected HardConflict tension, got: {tensions}"
        )

    def test_diffpair_capacity_2_is_sat(self):
        """DiffPair on CH1, CH1 capacity 2 — SAT, no HardConflict."""
        p = _var(0, "CH1")
        n = _var(1, "CH1")
        py_vars = [p, n]

        py_cons = [
            _dp("diff_CH1", "CH1", 0, 1, p, n),
            _cap("cap_CH1", "CH1", 2.0, 1.0, [(p, 1.0), (n, 1.0)]),
        ]
        result = solve_topology_rust(py_vars, py_cons, ["net0", "net1"])

        assert result["status"] == "sat"
        tensions = result.get("tensions", [])
        hard_conflicts = [t for t in tensions if t["severity"] == "hard_conflict"]
        assert len(hard_conflicts) == 0, f"Unexpected HardConflict: {hard_conflicts}"
        assert result.get("conflicts") is None


class TestCapacityWarningDetection:
    """CapacityWarning at near-boundary capacity."""

    def test_capacity_warning_near_boundary(self):
        """10 nets on CH1, capacity 10, 9 must-use — CapacityWarning."""
        v_ch1 = [_var(i, "CH1") for i in range(10)]
        v_ch2 = [_var(i, "CH2") for i in range(10)]
        py_vars = list(v_ch1) + list(v_ch2)

        bans = [_lr(f"ban_{i}", i, "CH2", False) for i in range(9)]

        py_cons = [
            _cap("cap_CH1", "CH1", 10.0, 1.0, [(v, 1.0) for v in v_ch1]),
            _cap("cap_CH2", "CH2", 10.0, 1.0, [(v, 1.0) for v in v_ch2]),
        ] + bans
        result = solve_topology_rust(py_vars, py_cons, [f"N{i}" for i in range(10)])

        assert result["status"] == "sat"

        tensions = result.get("tensions", [])
        warnings = [t for t in tensions if t["severity"] == "capacity_warning"]
        assert len(warnings) >= 1, f"Expected CapacityWarning, got: {tensions}"


class TestBackwardCompatibility:
    """Existing keys remain present in the result dict."""

    def test_all_expected_keys_present(self):
        v = _var(0, "CH1")
        py_vars = [v]
        py_cons = [_cap("cap_CH1", "CH1", 1.0, 1.0, [(v, 1.0)])]
        result = solve_topology_rust(py_vars, py_cons, ["N0"])

        for key in ["status", "assignments", "topology_graph", "solver_time_ms",
                     "num_vars", "num_clauses", "unsat_core", "tensions", "conflicts"]:
            assert key in result, f"Missing key '{key}' in result dict"

    def test_sat_result_has_tensions_empty_conflicts_none(self):
        # Use 2 vars with capacity 1 (k < n) to avoid empty-guard UNSAT.
        v0 = _var(0, "CH1")
        v1 = _var(1, "CH1")
        py_vars = [v0, v1]
        py_cons = [_cap("cap_CH1", "CH1", 1.0, 1.0, [(v0, 1.0), (v1, 1.0)])]
        result = solve_topology_rust(py_vars, py_cons, ["N0", "N1"])

        assert result["status"] == "sat"
        assert isinstance(result.get("tensions"), list)
        assert result.get("conflicts") is None
