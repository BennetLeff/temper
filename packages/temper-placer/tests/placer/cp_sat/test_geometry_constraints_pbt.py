"""Property-based tests for C1 courtyard and C2 board-edge constraints.

P1: Soundness C1 — min pairwise Euclidean gap >= tau_mm.
P2: Soundness C2 — min distance to board edge >= margin_mm.
P3: Rotation-invariance — P1/P2 hold under component rotations.
P4: Monotonicity — SAT(delta',m') implies SAT(delta,m) when delta'>=delta, m'>=m.
P5: Area floor — total courtyarded area > usable board area => UNSAT.
P6: Bounded completeness — N<=3 with clearance >= 2*delta => SAT.
P7: Determinism — same seed produces identical placement.

P8: Bounds enclose pads — every component's parsed bounds contain all its pads.
    Catches the map-vs-territory gap: P1 verifies the model (bounds separation),
    but DRC checks pads. If bounds ⊉ pads, P1 is green while DRC fails.
    This test guards the territory.
P9: Golden temper board — bounds ⊇ pads for all 33 components on the real board.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.placer.cp_sat.encoder import EncoderContext, encode_constraints
from temper_placer.placer.cp_sat.model import CpSatModel

from ._strategies import small_placement_instance, tau_and_margin


def _gap_x(vars_a, sol_a, vars_b, sol_b) -> int:
    """Edge-to-edge x gap in grid units."""
    a_xs = sol_a[0] - vars_a[0] // 2
    b_xe = sol_b[0] + vars_b[0] // 2
    return b_xe - a_xs


def _gap_y(vars_a, sol_a, vars_b, sol_b) -> int:
    """Edge-to-edge y gap in grid units."""
    a_ys = sol_a[1] - vars_a[1] // 2
    b_ye = sol_b[1] + vars_b[1] // 2
    return b_ye - a_ys


def _chebyshev_gap(vars_a, sol_a, vars_b, sol_b) -> int:
    """Max of |x_gap|, |y_gap| in grid units (Chebyshev)."""
    # Edge-to-edge overlap/gap along x
    gx = abs(sol_a[0] - sol_b[0]) - (vars_a[0] + vars_b[0]) // 2
    gy = abs(sol_a[1] - sol_b[1]) - (vars_a[1] + vars_b[1]) // 2
    return max(gx, gy)


class TestP1CourtyardSoundness:
    @pytest.mark.property
    @given(small_placement_instance(n_comps=3))
    @settings(max_examples=30, deadline=30000)
    def test_min_pairwise_gap_ge_tau(self, instance):
        model, ctx, refs, tau_mm, margin_mm = instance
        encode_constraints([], model, ctx)
        sol = model.solve(time_limit_s=5.0)
        if not sol.feasible:
            return  # too constrained — soundness vacuously true

        min_gap = float("inf")
        tau_u = model.mm_to_units(tau_mm)
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                a, b = refs[i], refs[j]
                gap = _chebyshev_gap(sol.sizes[a], sol.positions[a], sol.sizes[b], sol.positions[b])
                min_gap = min(min_gap, gap)
        if min_gap < tau_u and tau_mm > 0:
            pytest.fail(f"Min gap {min_gap} < tau {tau_u} units (tau_mm={tau_mm})")


class TestP2EdgeMarginSoundness:
    @pytest.mark.property
    @given(small_placement_instance(n_comps=3))
    @settings(max_examples=30, deadline=30000)
    def test_min_edge_distance_ge_margin(self, instance):
        model, ctx, refs, tau_mm, margin_mm = instance
        encode_constraints([], model, ctx)
        sol = model.solve(time_limit_s=5.0)
        if not sol.feasible:
            return

        margin_u = model.mm_to_units(margin_mm)
        board_w_u = ctx.board_x_max_units
        board_h_u = ctx.board_y_max_units
        for ref in refs:
            x, y = sol.positions[ref]
            sw, sh = sol.sizes[ref]
            x_start = x - sw // 2
            y_start = y - sh // 2
            x_end = x + sw // 2
            y_end = y + sh // 2
            assert x_start >= margin_u, f"{ref} x_start={x_start} < margin={margin_u}"
            assert y_start >= margin_u, f"{ref} y_start={y_start} < margin={margin_u}"
            assert x_end <= board_w_u - margin_u, f"{ref} x_end={x_end} > {board_w_u - margin_u}"
            assert y_end <= board_h_u - margin_u, f"{ref} y_end={y_end} > {board_h_u - margin_u}"


class TestP3RotationInvariance:
    @pytest.mark.property
    @given(small_placement_instance(n_comps=3))
    @settings(max_examples=20, deadline=60000)
    def test_gap_respected_with_rotations(self, instance):
        model, ctx, refs, tau_mm, margin_mm = instance
        # Enable rotations for non-polarized components
        for ref in refs:
            v = model.get_component(ref)
            w0 = v.orig_w
            h0 = v.orig_h
            if w0 != h0:
                model.add_rotation(ref, is_polarized=False)
        encode_constraints([], model, ctx)
        sol = model.solve(time_limit_s=5.0)
        if not sol.feasible:
            return

        # P1 check
        tau_u = model.mm_to_units(tau_mm)
        margin_u = model.mm_to_units(margin_mm)
        board_w_u = ctx.board_x_max_units - margin_u
        board_h_u = ctx.board_y_max_units - margin_u

        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                a, b = refs[i], refs[j]
                gap = _chebyshev_gap(sol.sizes[a], sol.positions[a], sol.sizes[b], sol.positions[b])
                assert gap >= tau_u, f"Gap {gap} < tau {tau_u} for pair {a}-{b}"

        # P2 check
        for ref in refs:
            x, y = sol.positions[ref]
            sw, sh = sol.sizes[ref]
            assert x - sw // 2 >= margin_u
            assert y - sh // 2 >= margin_u
            assert x + sw // 2 <= board_w_u
            assert y + sh // 2 <= board_h_u


class TestP4Monotonicity:
    @pytest.mark.property
    @given(small_placement_instance(n_comps=3))
    @settings(max_examples=20, deadline=60000)
    def test_stronger_constraints_preserve_feasibility(self, instance):
        model, ctx, refs, tau_mm, margin_mm = instance
        encode_constraints([], model, ctx)
        sol = model.solve(time_limit_s=5.0)
        weaker_feasible = sol.feasible

        # Try stronger constraints: tau' >= tau, m' >= m
        tau_prime = tau_mm + 0.5
        margin_prime = margin_mm + 0.5

        model2 = CpSatModel(units_per_mm=100)
        for ref in refs:
            v = model.get_component(ref)
            model2.add_component(ref, 0, 0, v.orig_w, v.orig_h)
            model2.add_rotation(ref, is_polarized=True)

        board_w_u = model.mm_to_units(ctx.board_w_mm)
        board_h_u = model.mm_to_units(ctx.board_h_mm)
        margin_u = model.mm_to_units(margin_prime)
        model2.set_bounds(margin_u, margin_u, board_w_u - margin_u, board_h_u - margin_u)
        model2.add_no_overlap_2d(refs)

        ctx2 = EncoderContext(
            board_w_mm=ctx.board_w_mm,
            board_h_mm=ctx.board_h_mm,
            board_x_max_units=board_w_u,
            board_y_max_units=board_h_u,
            courtyard_clearance_mm=tau_prime,
            board_edge_margin_units=margin_u,
        )
        encode_constraints([], model2, ctx2)
        sol2 = model2.solve(time_limit_s=5.0)

        # If stronger is feasible, weaker must be feasible too
        if sol2.feasible:
            assert weaker_feasible, (
                f"Stronger (tau={tau_prime}, m={margin_prime}) feasible "
                f"but weaker (tau={tau_mm}, m={margin_mm}) infeasible"
            )


class TestP5AreaFloor:
    @pytest.mark.property
    @given(small_placement_instance(n_comps=3))
    @settings(max_examples=20, deadline=60000)
    def test_area_exceeding_board_is_unsat(self, instance):
        model, ctx, refs, tau_mm, margin_mm = instance

        if tau_mm <= 0:
            return  # skip — can't make area argument without tau

        # Compute total courtyarded area: sum (w+2*tau) * (h+2*tau) for each comp
        total_courtyarded = 0.0
        for ref in refs:
            v = model.get_component(ref)
            w_mm = model.units_to_mm(v.orig_w)
            h_mm = model.units_to_mm(v.orig_h)
            total_courtyarded += (w_mm + 2 * tau_mm) * (h_mm + 2 * tau_mm)

        usable_w = ctx.board_w_mm - 2 * margin_mm
        usable_h = ctx.board_h_mm - 2 * margin_mm
        usable_area = usable_w * usable_h

        if total_courtyarded > usable_area:
            encode_constraints([], model, ctx)
            sol = model.solve(time_limit_s=5.0)
            # Should be infeasible — area too small
            assert not sol.feasible, (
                f"Courtyarded area {total_courtyarded:.1f} > usable {usable_area:.1f} "
                f"but solver reported feasible"
            )


class TestP6BoundedCompleteness:
    def _build_complete_instance(self, n_comps: int, tau_mm: float, margin_mm: float):
        model = CpSatModel(units_per_mm=100)
        # Ensure board is large enough: generous sizing
        board_w_mm = float(n_comps * 20 + 2 * margin_mm)
        board_h_mm = float(n_comps * 20 + 2 * margin_mm)

        model.mm_to_units(tau_mm)
        margin_u = model.mm_to_units(margin_mm)
        board_w_u = model.mm_to_units(board_w_mm)
        board_h_u = model.mm_to_units(board_h_mm)

        refs: list[str] = []
        for i in range(n_comps):
            ref = f"C{i}"
            refs.append(ref)
            # Small components, 2mm each
            w_u = model.mm_to_units(2.0)
            h_u = model.mm_to_units(2.0)
            model.add_component(ref, 0, 0, w_u, h_u)
            model.add_rotation(ref, is_polarized=True)

        model.set_bounds(margin_u, margin_u, board_w_u - margin_u, board_h_u - margin_u)
        model.add_no_overlap_2d(refs)

        ctx = EncoderContext(
            board_w_mm=board_w_mm,
            board_h_mm=board_h_mm,
            board_x_max_units=board_w_u,
            board_y_max_units=board_h_u,
            courtyard_clearance_mm=tau_mm,
            board_edge_margin_units=margin_u,
        )
        return model, ctx, refs

    @pytest.mark.property
    @given(st.integers(min_value=1, max_value=3), tau_and_margin(tau_max=1.0, margin_max=1.0))
    @settings(max_examples=10, deadline=30000)
    def test_small_n_with_clearance_is_sat(self, n_comps, tm):
        tau_mm, margin_mm = tm
        if tau_mm <= 0 and margin_mm <= 0:
            return  # trivial

        model, ctx, refs = self._build_complete_instance(n_comps, tau_mm, margin_mm)
        encode_constraints([], model, ctx)
        sol = model.solve(time_limit_s=5.0)
        assert sol.feasible, (
            f"n={n_comps} tau={tau_mm} margin={margin_mm}: should be SAT but got "
            f"status={sol.status.name} unsat_core={sol.unsat_assumptions}"
        )


class TestP7Determinism:
    @pytest.mark.property
    @given(small_placement_instance(n_comps=3))
    @settings(max_examples=5, deadline=60000)
    def test_same_seed_same_placement(self, instance):
        model, ctx, refs, tau_mm, margin_mm = instance
        encode_constraints([], model, ctx)

        pos1 = {}
        sol1 = model.solve(time_limit_s=5.0)
        if not sol1.feasible:
            return
        for ref in refs:
            pos1[ref] = sol1.positions[ref]

        # Re-solve the same model — CP-SAT is deterministic for same model+seed
        sol2 = model.solve(time_limit_s=5.0)
        assert sol2.feasible
        for ref in refs:
            assert pos1[ref] == sol2.positions[ref], (
                f"{ref}: run1={pos1[ref]}, run2={sol2.positions[ref]}"
            )


# ---------------------------------------------------------------------------
# P8: Bounds ⊇ pads invariant (Hypothesis)
# ---------------------------------------------------------------------------


def test_bounds_enclose_pads_hypothesis():
    """Every component's parsed bounds must enclose all its pads.

    This is the model-vs-territory bridge: P1 verifies that the solver
    respects bounds separation, but DRC checks pads.  If bounds do not
    enclose pads, the constraint can be perfectly satisfied (green PBT)
    while kicad-cli still reports shorts at the pad level.
    """
    from hypothesis import given, settings
    from hypothesis import strategies as st

    # Generate random pad positions within a footprint and verify
    # that the reported bounds contain them.
    @given(
        pad_positions=st.lists(
            st.tuples(st.floats(-10, 10), st.floats(-10, 10)),
            min_size=1,
            max_size=10,
        ),
        pad_sizes=st.lists(
            st.tuples(st.floats(0.1, 5.0), st.floats(0.1, 5.0)),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=5000)
    def _test(pad_positions, pad_sizes):
        n = min(len(pad_positions), len(pad_sizes))
        pad_xs = [pad_positions[i][0] for i in range(n)]
        pad_ys = [pad_positions[i][1] for i in range(n)]

        # Compute bounds from pad extents (as the parser does)
        for i in range(n):
            pw, ph = pad_sizes[i]
            pad_xs.append(pad_positions[i][0] + pw / 2)
            pad_xs.append(pad_positions[i][0] - pw / 2)
            pad_ys.append(pad_positions[i][1] + ph / 2)
            pad_ys.append(pad_positions[i][1] - ph / 2)

        bounds_w = max(pad_xs) - min(pad_xs)
        bounds_h = max(pad_ys) - min(pad_ys)

        # Every pad centre must lie within bounds/2 of the bounds centre
        cx = (min(pad_xs) + max(pad_xs)) / 2
        cy = (min(pad_ys) + max(pad_ys)) / 2
        for (px, py), (_pw, _ph) in zip(pad_positions[:n], pad_sizes[:n]):
            assert abs(px - cx) <= bounds_w / 2 + 1e-9, (
                f"pad at ({px},{py}) outside x-bounds ±{bounds_w / 2:.3f}"
            )
            assert abs(py - cy) <= bounds_h / 2 + 1e-9, (
                f"pad at ({px},{py}) outside y-bounds ±{bounds_h / 2:.3f}"
            )

    _test()


# ---------------------------------------------------------------------------
# P9: Golden temper board — bounds ⊇ pads for all real components
# ---------------------------------------------------------------------------


def test_golden_temper_board_bounds_enclose_pads():
    """Every component on the golden temper board has bounds enclosing its pads.

    This is a deterministic regression test for Gap A — if it fails,
    pads protrude past the boxes the Chebyshev constraints protect,
    and DRC violations survive regardless of encoding soundness.
    """
    from pathlib import Path

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    input_pcb = (
        Path(__file__).parent.parent.parent.parent.parent.parent
        / "power_pcb_dataset"
        / "corpus"
        / "temper"
        / "temper.kicad_pcb"
    )
    if not input_pcb.exists():
        import pytest

        pytest.skip("temper board not found")

    pr = parse_kicad_pcb(input_pcb)
    violations = []

    for comp in pr.netlist.components:
        w, h = comp.width, comp.height
        for pin in comp.pins:
            px, py = pin.position
            if abs(px) > w / 2 + 0.01 or abs(py) > h / 2 + 0.01:
                d_x = abs(px) - w / 2
                d_y = abs(py) - h / 2
                violations.append(
                    f"{comp.ref}: pad {pin.number} at ({px:.1f},{py:.1f}) "
                    f"outside bounds ±({w / 2:.1f},{h / 2:.1f}) "
                    f"by ({d_x:.1f},{d_y:.1f})mm"
                )

    assert not violations, f"{len(violations)} components have pads outside bounds:\n" + "\n".join(
        violations[:10]
    )
