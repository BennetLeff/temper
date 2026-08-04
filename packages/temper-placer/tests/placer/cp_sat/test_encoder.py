"""Tests for CP-SAT encoder — U2: per-type encoding tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from temper_placer.core.netlist import Component, Netlist
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
from temper_placer.placer.cp_sat._encoder_core import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.encoder import (
    EncoderContext,
    encode_constraints,
    reconcile_constraint_refs,
    reconcile_loop_components,
    solve_placement,
    validate_constraint_refs,
)
from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY
from temper_placer.placer.cp_sat.model import CpSatModel


class TestReferenceReconciliation:
    """Aliases are explicit, canonical, and fail closed when incomplete."""

    def test_reconciles_component_and_loop_operands(self) -> None:
        constraints = [
            AdjacentConstraint(
                "OLD_Q1",
                "OLD_Q2",
                max_distance_mm=10.0,
                tier=ConstraintTier.HARD,
                because="Keep the commutation switches close",
            ),
            LoopAreaConstraint(
                "old_commutation",
                max_area_mm2=500.0,
                tier=ConstraintTier.HARD,
                because="Limit switching loop area",
            ),
        ]

        result = reconcile_constraint_refs(
            constraints,
            {
                "OLD_Q1": "Q1",
                "OLD_Q2": "Q2",
                "old_commutation": "commutation_loop",
            },
        )

        assert (result.constraints[0].a, result.constraints[0].b) == ("Q1", "Q2")
        assert result.constraints[1].loop_name == "commutation_loop"
        assert result.aliases_applied == (
            ("OLD_Q1", "Q1"),
            ("OLD_Q2", "Q2"),
            ("old_commutation", "commutation_loop"),
        )

    def test_alias_chains_are_canonicalized(self) -> None:
        constraint = AdjacentConstraint(
            "LEGACY_Q1",
            "Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Keep the commutation switches close",
        )

        result = reconcile_constraint_refs(
            [constraint], {"LEGACY_Q1": "OLD_Q1", "OLD_Q1": "Q1"}
        )

        assert result.constraints[0].a == "Q1"
        assert result.aliases_applied == (("LEGACY_Q1", "Q1"),)

    def test_alias_cycles_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="cycle"):
            reconcile_constraint_refs([], {"A": "B", "B": "A"})

    def test_alias_to_missing_target_stays_unresolved(self) -> None:
        constraint = AdjacentConstraint(
            "LEGACY_Q1",
            "Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Keep the commutation switches close",
        )
        result = reconcile_constraint_refs([constraint], {"LEGACY_Q1": "MISSING_Q1"})

        unresolved = validate_constraint_refs(
            list(result.constraints),
            component_refs={"Q1", "Q2"},
            zone_names=set(),
            loop_names=set(),
            on_unresolved="ignore",
        )

        assert unresolved == {"adj_LEGACY_Q1_Q2": ["MISSING_Q1"]}

    def test_loop_aliases_work_without_component_aliases(self) -> None:
        constraint = LoopAreaConstraint(
            "legacy_loop",
            max_area_mm2=100.0,
            tier=ConstraintTier.HARD,
            because="Keep the extracted loop bounded",
        )

        result = reconcile_constraint_refs(
            [constraint], loop_aliases={"legacy_loop": "commutation_loop"}
        )

        assert result.constraints[0].loop_name == "commutation_loop"

    def test_loop_components_reconcile_names_and_members(self) -> None:
        result = reconcile_loop_components(
            {"legacy_loop": ["OLD_Q1", "Q2"]},
            {"OLD_Q1": "Q1"},
            {"legacy_loop": "commutation_loop"},
        )

        assert result.loop_components == {"commutation_loop": ["Q1", "Q2"]}
        assert result.aliases_applied == (
            ("OLD_Q1", "Q1"),
            ("legacy_loop", "commutation_loop"),
        )

    def test_loop_alias_collision_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="multiple loop definitions"):
            reconcile_loop_components(
                {"legacy_a": ["Q1"], "legacy_b": ["Q2"]},
                loop_aliases={"legacy_a": "commutation", "legacy_b": "commutation"},
            )

    # ------------------------------------------------------------------
    # Metamorphic fail-closed invariant (rework of PR #498)
    # ------------------------------------------------------------------
    # The placement gate must be metamorphic with respect to the alias map:
    # the SAME legacy constraint either (a) fails closed at validation when
    # no source-backed map is supplied, or (b) is reconciled to live refs and
    # solves when the map is supplied. Nothing in between -- a broken source
    # reference can never silently place against nothing.

    @staticmethod
    def _component(ref: str) -> Component:
        return Component(ref=ref, footprint="R_0603", bounds=(1.6, 0.8), pins=[])

    def test_gate_fires_on_broken_ref_and_passes_on_reconciled(self) -> None:
        legacy_constraints = [
            AdjacentConstraint(
                "U_GATE",
                "C_BOOT",
                max_distance_mm=10.0,
                tier=ConstraintTier.HARD,
                because="Keep the gate-driver bootstrap close",
            ),
            AdjacentConstraint(
                "U_MCU",
                "C_MCU_1",
                max_distance_mm=15.0,
                tier=ConstraintTier.HARD,
                because="Keep the MCU decoupling close",
            ),
        ]
        live_refs = ["U7", "C17", "U27", "C37", "Q1", "Q2"]
        netlist = Netlist(components=[self._component(r) for r in live_refs], nets=[])
        board = SimpleNamespace(width=60.0, height=60.0, zones=[], constraints=[])
        aliases = {
            "U_GATE": "U7",
            "C_BOOT": "C17",
            "U_MCU": "U27",
            "C_MCU_1": "C37",
        }

        # Leg 1 (broken source reference): the same constraint that references
        # legacy conceptual names raises the fail-closed validator error.
        with pytest.raises(UnresolvedConstraintRefsError):
            solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=legacy_constraints,
                timeout_ms=200,
            )

        # Leg 2 (reconciled): with the source-backed map supplied, the same
        # constraint set validates and produces a placement.
        result = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=legacy_constraints,
            timeout_ms=200,
            reference_aliases=aliases,
        )
        assert result.status in ("optimal", "feasible", "unknown")
        assert set(result.positions) == set(live_refs)

    def test_gate_rejects_alias_to_missing_target_at_solve_time(self) -> None:
        """An alias whose target is not a live netlist ref must not silently
        no-op: the loader rejects it before the model is built."""
        netlist = Netlist(
            components=[self._component(r) for r in ("U7", "C17")], nets=[]
        )
        board = SimpleNamespace(width=60.0, height=60.0, zones=[], constraints=[])
        with pytest.raises(UnresolvedConstraintRefsError):
            solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=[
                    AdjacentConstraint(
                        "U_GATE",
                        "C_BOOT",
                        max_distance_mm=10.0,
                        tier=ConstraintTier.HARD,
                        because="bootstrap proximity",
                    )
                ],
                timeout_ms=200,
                reference_aliases={"U_GATE": "U7", "C_BOOT": "U999"},  # bad target
            )


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

        c = SeparatedConstraint(
            "A",
            "B",
            min_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            because="Isolation requirement per safety analysis",
        )
        ctx = EncoderContext(
            board_w_mm=30.0, board_h_mm=30.0, board_x_max_units=3000, board_y_max_units=3000
        )
        encode_constraints([c], model, ctx)

        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        ax, ay = sol.positions["A"]
        bx, by = sol.positions["B"]
        gap_x = abs(ax - bx) - 200
        gap_y = abs(ay - by) - 200
        assert gap_x >= 480 or gap_y >= 480, (
            f"gap_x={gap_x}, gap_y={gap_y}, expected >=500units clearance"
        )


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
            outer="HV_ZONE",
            inner=["Q1", "Q2"],
            tier=ConstraintTier.HARD,
            because="All high voltage parts must stay in HV safety zone for isolation",
        )
        ctx = EncoderContext(
            board_w_mm=20.0,
            board_h_mm=20.0,
            board_x_max_units=2000,
            board_y_max_units=2000,
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
            "Q1",
            "Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close to minimize loop area ind",
        )
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )
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
            "Q1",
            "Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            metric=DistanceMetric.EDGE_TO_EDGE,
            because="Half-bridge IGBTs within 10mm edge-to-edge for tight loop",
        )
        ctx = EncoderContext(
            board_w_mm=100.0, board_h_mm=150.0, board_x_max_units=10000, board_y_max_units=15000
        )
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
            "A",
            "B",
            max_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            metric=DistanceMetric.CENTER_TO_CENTER,
            because="Center-to-center metric must remain available and correct",
        )
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )
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
            components=["J1"],
            side=BoardSide.LEFT,
            edge=EdgeType.FLUSH,
            max_distance_mm=2.0,
            tier=ConstraintTier.HARD,
            because="Connector must be on left edge for external access housing",
        )
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )
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
            component="U_MCU",
            tier=ConstraintTier.HARD,
            position=(15.0, 10.0),
            because="MCU must be centered in MCU zone for antenna clearance",
        )
        ctx = EncoderContext(
            board_w_mm=30.0, board_h_mm=20.0, board_x_max_units=3000, board_y_max_units=2000
        )
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
            zone_name="NO_FLY",
            tier=ConstraintTier.HARD,
            because="No components allowed in keepout for safety isolation zone",
        )
        ctx = EncoderContext(
            board_w_mm=20.0,
            board_h_mm=20.0,
            board_x_max_units=2000,
            board_y_max_units=2000,
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
            components=["C1", "C2", "C3"],
            axis=Axis.X,
            tolerance_mm=0.5,
            tier=ConstraintTier.HARD,
            because="Align decoupling capacitors for visual consistency and routing",
        )
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        xs = [sol.positions[r][0] for r in ["C1", "C2", "C3"]]
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                assert abs(xs[i] - xs[j]) <= 50, (
                    f"C{i + 1}-C{j + 1} x diff {abs(xs[i] - xs[j])} > 50 units"
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
            loop_name="commutation",
            max_area_mm2=500.0,
            tier=ConstraintTier.HARD,
            because="Minimize commutation loop to reduce voltage overshoot and EMI emission",
        )
        ctx = EncoderContext(
            board_w_mm=50.0,
            board_h_mm=50.0,
            board_x_max_units=5000,
            board_y_max_units=5000,
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
        ctx = EncoderContext(
            board_w_mm=10.0, board_h_mm=10.0, board_x_max_units=1000, board_y_max_units=1000
        )
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
            a=kw["a"],
            b=kw["b"],
            min_distance_mm=1.0,
            tier=ConstraintTier.STRONG,
            because="test rationale ok",
            id=kw.get("id", "s1"),
        )

    def test_all_resolvable_is_clean(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs

        c = self._c(a="R1", b="R2")
        report = validate_constraint_refs(
            [c],
            component_refs={"R1", "R2"},
            zone_names=set(),
            loop_names=set(),
        )
        assert report == {}

    def test_zone_operand_resolves(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs

        # A zone name is a valid operand (zones expand to members).
        c = self._c(a="HV_ZONE", b="R1")
        report = validate_constraint_refs(
            [c],
            component_refs={"R1"},
            zone_names={"HV_ZONE"},
            loop_names=set(),
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
                [c],
                component_refs={"R1"},
                zone_names=set(),
                loop_names=set(),
            )
        assert "J_AC" in str(exc.value)

    def test_warn_policy_does_not_raise(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs

        c = self._c(a="J_AC", b="R1", id="sep_J_AC_R1")
        report = validate_constraint_refs(
            [c],
            component_refs={"R1"},
            zone_names=set(),
            loop_names=set(),
            on_unresolved="warn",
        )
        assert report == {"sep_J_AC_R1": ["J_AC"]}

    def test_enclosing_inner_and_outer(self) -> None:
        from temper_placer.placer.cp_sat.encoder import validate_constraint_refs

        c = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["Q1", "GHOST"],
            tier=ConstraintTier.HARD,
            because="containment rationale",
            id="enc_HV",
        )
        report = validate_constraint_refs(
            [c],
            component_refs={"Q1"},
            zone_names={"HV_ZONE"},
            loop_names=set(),
            on_unresolved="warn",
        )
        assert report == {"enc_HV": ["GHOST"]}


class TestUnresolvedRefPolicyIsReadLive:
    """The unresolved-ref policy must have exactly one live definition.

    ``_UNRESOLVED_REF_POLICY`` is defined in ``_encoder_core`` and consumed
    at ``_encoder_solve.solve_placement``'s ``validate_constraint_refs``
    call.  If ``_encoder_solve`` binds it with
    ``from _encoder_core import _UNRESOLVED_REF_POLICY``, that binding
    snapshots the value at import time and never changes again.  Tests that
    downgrade the policy to "warn" then set an attribute nothing reads: the
    fail-closed guard stays armed, the test still passes, and the downgrade
    is silently vacuous.  These tests pin the live-read wiring.
    """

    def test_solve_module_holds_no_policy_snapshot(self) -> None:
        from temper_placer.placer.cp_sat import _encoder_solve

        assert "_UNRESOLVED_REF_POLICY" not in vars(_encoder_solve), (
            "_encoder_solve has its own _UNRESOLVED_REF_POLICY binding, which "
            "snapshots the value at import time. Read it as "
            "_encoder_core._UNRESOLVED_REF_POLICY at call time instead, or "
            "monkeypatching the policy becomes a silent no-op."
        )

    def test_solve_placement_reads_policy_through_the_core_module(self) -> None:
        from temper_placer.placer.cp_sat._encoder_solve import solve_placement

        names = solve_placement.__code__.co_names
        assert "_encoder_core" in names and "_UNRESOLVED_REF_POLICY" in names, (
            "solve_placement no longer reads "
            "_encoder_core._UNRESOLVED_REF_POLICY as a module attribute; the "
            "policy can no longer be overridden at runtime."
        )

    def test_core_is_the_sole_definition(self) -> None:
        from temper_placer.placer.cp_sat import _encoder_core

        assert isinstance(_encoder_core._UNRESOLVED_REF_POLICY, str)
