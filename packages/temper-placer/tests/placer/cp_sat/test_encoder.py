"""Tests for CP-SAT encoder — U2: per-type encoding tests."""

from __future__ import annotations

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    CompilationTarget,
    ConstraintTier,
    ConstraintType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.placer.cp_sat.encoder import (
    EncoderContext,
    encode_constraints,
)
from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY
from temper_placer.placer.cp_sat.model import CpSatModel


class TestHandlerCoverage:
    """All 8 ConstraintType values must have a handler."""

    def test_all_constraint_types_covered(self) -> None:
        for ct in ConstraintType:
            if CompilationTarget.CP_SAT in ct.supported_targets:
                assert ct in HANDLER_REGISTRY, f"No handler for {ct}"
        assert len(HANDLER_REGISTRY) == 8


class TestSeparated:
    """SEPARATED encoding tests."""

    def test_separated_enforces_clearance(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_component("B", 0, 0, 200, 200)
        model.add_rotation("A", is_polarized=True)
        model.add_rotation("B", is_polarized=True)
        model.set_bounds(0, 0, 3000, 3000)

        c = SeparatedConstraint("A", "B", min_distance_mm=5.0, tier=ConstraintTier.HARD,
                                 because="Isolation requirement per safety analysis")
        ctx = EncoderContext(board_w_mm=30.0, board_h_mm=30.0,
                             board_x_max_units=3000, board_y_max_units=3000)
        encode_constraints([c], model, ctx)

        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        ax, ay = sol.positions["A"]
        bx, by = sol.positions["B"]
        gap_x = abs(ax - bx) - 200
        gap_y = abs(ay - by) - 200
        assert gap_x >= 480 or gap_y >= 480, f"gap_x={gap_x}, gap_y={gap_y}, expected >=500units clearance"


class TestEnclosing:
    """ENCLOSING encoding tests."""

    def test_enclosing_within_zone(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("Q1", 0, 0, 100, 100)
        model.add_component("Q2", 0, 0, 100, 100)
        model.add_rotation("Q1", is_polarized=True)
        model.add_rotation("Q2", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)

        c = EnclosingConstraint(
            outer="HV_ZONE", inner=["Q1", "Q2"], tier=ConstraintTier.HARD,
            because="All high voltage parts must stay in HV safety zone for isolation",
        )
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0,
            board_x_max_units=2000, board_y_max_units=2000,
            zones={"HV_ZONE": (5.0, 5.0, 15.0, 15.0)},
        )
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        for ref in ["Q1", "Q2"]:
            x, y = sol.positions[ref]
            sw, sh = sol.sizes[ref]
            assert x - sw // 2 >= 500, f"{ref} x_start too low"
            assert y - sh // 2 >= 500, f"{ref} y_start too low"
            assert x + sw // 2 <= 1500, f"{ref} x_end too high"
            assert y + sh // 2 <= 1500, f"{ref} y_end too high"


class TestAdjacent:
    """ADJACENT encoding tests."""

    def test_adjacent_proximity(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("Q1", 0, 0, 100, 100)
        model.add_component("Q2", 0, 0, 100, 100)
        model.add_rotation("Q1", is_polarized=True)
        model.add_rotation("Q2", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)

        c = AdjacentConstraint(
            "Q1", "Q2", max_distance_mm=10.0, tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close to minimize loop area ind",
        )
        ctx = EncoderContext(board_w_mm=20.0, board_h_mm=20.0,
                             board_x_max_units=2000, board_y_max_units=2000)
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        ax, ay = sol.positions["Q1"]
        bx, by = sol.positions["Q2"]
        dist_x = abs(ax - bx)
        dist_y = abs(ay - by)
        assert dist_x <= 1000, f"x centre distance {dist_x} > 1000 units"
        assert dist_y <= 1000, f"y centre distance {dist_y} > 1000 units"

    def test_adjacent_edge_to_edge_allows_wide_parts_side_by_side(self) -> None:
        # Regression: two wide parts that cannot overlap must still satisfy
        # a small edge_to_edge adjacency. Under the old (buggy) center-to-center
        # encoding this was infeasible (centers >= width apart >> max_distance).
        from temper_placer.pcl.constraints import DistanceMetric

        model = CpSatModel(units_per_mm=100)
        # 25.3mm x 3.5mm parts (like the IGBTs), on a 100x150mm board.
        model.add_component("Q1", 0, 0, 2530, 350)
        model.add_component("Q2", 0, 0, 2530, 350)
        model.add_rotation("Q1", is_polarized=True)
        model.add_rotation("Q2", is_polarized=True)
        model.set_bounds(0, 0, 10000, 15000)
        model.add_no_overlap_2d(["Q1", "Q2"])

        c = AdjacentConstraint(
            "Q1", "Q2", max_distance_mm=10.0, tier=ConstraintTier.HARD,
            metric=DistanceMetric.EDGE_TO_EDGE,
            because="Half-bridge IGBTs within 10mm edge-to-edge for tight loop",
        )
        ctx = EncoderContext(board_w_mm=100.0, board_h_mm=150.0,
                             board_x_max_units=10000, board_y_max_units=15000)
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible, "edge_to_edge adjacency of wide parts must be feasible"

    def test_adjacent_center_to_center_still_supported(self) -> None:
        from temper_placer.pcl.constraints import DistanceMetric

        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_component("B", 0, 0, 200, 200)
        model.add_rotation("A", is_polarized=True)
        model.add_rotation("B", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)
        c = AdjacentConstraint(
            "A", "B", max_distance_mm=5.0, tier=ConstraintTier.HARD,
            metric=DistanceMetric.CENTER_TO_CENTER,
            because="Center-to-center metric must remain available and correct",
        )
        ctx = EncoderContext(board_w_mm=20.0, board_h_mm=20.0,
                             board_x_max_units=2000, board_y_max_units=2000)
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        ax, ay = sol.positions["A"]
        bx, by = sol.positions["B"]
        assert abs(ax - bx) <= 500 and abs(ay - by) <= 500


class TestOnSide:
    """ON_SIDE encoding tests."""

    def test_on_side_left_edge(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("J1", 0, 0, 200, 200)
        model.add_rotation("J1", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)

        from temper_placer.pcl.constraints import BoardSide, EdgeType
        c = OnSideConstraint(
            components=["J1"], side=BoardSide.LEFT, edge=EdgeType.FLUSH,
            max_distance_mm=2.0, tier=ConstraintTier.HARD,
            because="Connector must be on left edge for external access housing",
        )
        ctx = EncoderContext(board_w_mm=20.0, board_h_mm=20.0,
                             board_x_max_units=2000, board_y_max_units=2000)
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        x, y = sol.positions["J1"]
        sw, sh = sol.sizes["J1"]
        x_start = x - sw // 2
        assert x_start <= 200, f"J1 x_start={x_start} > 200 units from left edge"


class TestAnchored:
    """ANCHORED encoding tests."""

    def test_anchored_position_fix(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("U_MCU", 0, 0, 300, 300)
        model.add_rotation("U_MCU", is_polarized=True)
        model.set_bounds(0, 0, 3000, 2000)

        c = AnchoredConstraint(
            component="U_MCU", tier=ConstraintTier.HARD,
            position=(15.0, 10.0),
            because="MCU must be centered in MCU zone for antenna clearance",
        )
        ctx = EncoderContext(board_w_mm=30.0, board_h_mm=20.0,
                             board_x_max_units=3000, board_y_max_units=2000)
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        x, y = sol.positions["U_MCU"]
        assert abs(x - 1500) < 50, f"U_MCU x={x} expected 1500"
        assert abs(y - 1000) < 50, f"U_MCU y={y} expected 1000"


class TestKeepout:
    """KEEPOUT encoding tests."""

    def test_keepout_zone_exclusion(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_rotation("A", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)

        c = KeepoutConstraint(
            zone_name="NO_FLY", tier=ConstraintTier.HARD,
            because="No components allowed in keepout for safety isolation zone",
        )
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0,
            board_x_max_units=2000, board_y_max_units=2000,
            zones={"NO_FLY": (4.0, 4.0, 6.0, 6.0)},
        )
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        x, y = sol.positions["A"]
        sw, sh = sol.sizes["A"]
        x1, x2 = x - sw // 2, x + sw // 2
        y1, y2 = y - sh // 2, y + sh // 2
        # Should not overlap the keepout [400,600] x [400,600]
        assert not (x1 < 600 and x2 > 400 and y1 < 600 and y2 > 400), (
            f"A at ({x1},{y1})-({x2},{y2}) overlaps keepout"
        )


class TestAligned:
    """ALIGNED encoding tests."""

    def test_aligned_pairwise_x_axis(self) -> None:
        model = CpSatModel(units_per_mm=100)
        for ref in ["C1", "C2", "C3"]:
            model.add_component(ref, 0, 0, 80, 50)
            model.add_rotation(ref, is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)

        from temper_placer.pcl.constraints import Axis
        c = AlignedConstraint(
            components=["C1", "C2", "C3"], axis=Axis.X, tolerance_mm=0.5,
            tier=ConstraintTier.HARD,
            because="Align decoupling capacitors for visual consistency and routing",
        )
        ctx = EncoderContext(board_w_mm=20.0, board_h_mm=20.0,
                             board_x_max_units=2000, board_y_max_units=2000)
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        xs = [sol.positions[r][0] for r in ["C1", "C2", "C3"]]
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                assert abs(xs[i] - xs[j]) <= 50, (
                    f"C{i+1}-C{j+1} x diff {abs(xs[i] - xs[j])} > 50 units"
                )


class TestLoopArea:
    """LOOP_AREA encoding tests."""

    def test_loop_area_ceiling(self) -> None:
        model = CpSatModel(units_per_mm=100)
        for ref in ["C_BUS", "Q1", "Q2", "C_OUT"]:
            model.add_component(ref, 0, 0, 200, 200)
            model.add_rotation(ref, is_polarized=True)
        model.set_bounds(0, 0, 5000, 5000)

        c = LoopAreaConstraint(
            loop_name="commutation", max_area_mm2=500.0, tier=ConstraintTier.HARD,
            because="Minimize commutation loop to reduce voltage overshoot and EMI emission",
        )
        ctx = EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0,
            board_x_max_units=5000, board_y_max_units=5000,
            loop_components={"commutation": ["C_BUS", "Q1", "Q2", "C_OUT"]},
        )
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        # Verify AABB area <= 500 mm^2
        xs = [sol.positions[r][0] - sol.sizes[r][0] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        ys = [sol.positions[r][1] - sol.sizes[r][1] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        xe = [sol.positions[r][0] + sol.sizes[r][0] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        ye = [sol.positions[r][1] + sol.sizes[r][1] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        aabb_w = (max(xe) - min(xs)) / 100.0
        aabb_h = (max(ye) - min(ys)) / 100.0
        aabb_area = aabb_w * aabb_h
        assert aabb_area <= 500.0, f"Loop area {aabb_area:.1f} mm^2 > 500"


class TestEncoderDispatch:
    """Encoder dispatch and stub behavior."""

    def test_encode_empty_list(self) -> None:
        model = CpSatModel()
        ctx = EncoderContext(board_w_mm=10.0, board_h_mm=10.0,
                             board_x_max_units=1000, board_y_max_units=1000)
        assumptions = encode_constraints([], model, ctx)
        assert assumptions == []

    def test_unsupported_type_tracked(self) -> None:
        from temper_placer.placer.cp_sat.encoder import UNSUPPORTED_TYPES
        UNSUPPORTED_TYPES.clear()
        assert len(UNSUPPORTED_TYPES) == 0


class TestValidateConstraintRefs:
    """Fail-closed guard against config↔netlist drift (silent constraint drop)."""

    def _c(self, **kw):
        return SeparatedConstraint(
            a=kw["a"], b=kw["b"], min_distance_mm=1.0,
            tier=ConstraintTier.STRONG, because="test rationale ok", id=kw.get("id", "s1"),
        )

    def test_all_resolvable_is_clean(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs
        c = self._c(a="R1", b="R2")
        report = validate_constraint_refs(
            [c], component_refs={"R1", "R2"}, zone_names=set(), loop_names=set(),
        )
        assert report == {}

    def test_zone_operand_resolves(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs
        # A zone name is a valid operand (zones expand to members).
        c = self._c(a="HV_ZONE", b="R1")
        report = validate_constraint_refs(
            [c], component_refs={"R1"}, zone_names={"HV_ZONE"}, loop_names=set(),
        )
        assert report == {}

    def test_unresolved_ref_raises(self) -> None:
        import pytest

        from temper_placer.placer.cp_sat.encoder import (
            UnresolvedConstraintRefsError,
            validate_constraint_refs,
        )
        c = self._c(a="J_AC", b="R1", id="sep_J_AC_R1")  # J_AC not on board
        with pytest.raises(UnresolvedConstraintRefsError) as exc:
            validate_constraint_refs(
                [c], component_refs={"R1"}, zone_names=set(), loop_names=set(),
            )
        assert "J_AC" in str(exc.value)

    def test_warn_policy_does_not_raise(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs
        c = self._c(a="J_AC", b="R1", id="sep_J_AC_R1")
        report = validate_constraint_refs(
            [c], component_refs={"R1"}, zone_names=set(), loop_names=set(),
            on_unresolved="warn",
        )
        assert report == {"sep_J_AC_R1": ["J_AC"]}

    def test_enclosing_inner_and_outer(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs
        c = EnclosingConstraint(
            outer="HV_ZONE", inner=["Q1", "GHOST"], tier=ConstraintTier.HARD,
            because="containment rationale", id="enc_HV",
        )
        report = validate_constraint_refs(
            [c], component_refs={"Q1"}, zone_names={"HV_ZONE"}, loop_names=set(),
            on_unresolved="warn",
        )
        assert report == {"enc_HV": ["GHOST"]}
