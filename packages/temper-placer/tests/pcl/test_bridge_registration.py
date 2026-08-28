"""Contract tests for the explicit PCL-to-router compiler."""

from pathlib import Path

import pytest

from temper_placer.core.netlist import Component, Netlist
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    CompilationContext,
    ConstraintTier,
    ConstraintType,
    KeepoutConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.pcl.router_compiler import (
    EXPLICITLY_UNSUPPORTED_TYPES,
    TYPE_HANDLERS,
    CompilationDisposition,
    RouterConstraintCompilationError,
    _build_type_handlers,
    compile_pcl_for_router,
)


def _context(*refs: str) -> CompilationContext:
    components = [
        Component(ref=ref, footprint="SOIC8", bounds=(5, 5), pins=[])
        for ref in refs
    ]
    return CompilationContext(
        netlist=Netlist(components=components, nets=[]),
        skeletons={},
        channel_widths={},
    )


class TestExplicitRouterCompiler:
    """The router compiler is explicit, complete, and fail-closed."""

    def test_handler_catalog_covers_router_grounded_types(self):
        assert set(TYPE_HANDLERS) == set(ConstraintType) - EXPLICITLY_UNSUPPORTED_TYPES
        assert set(TYPE_HANDLERS) >= {
            ConstraintType.ADJACENT,
            ConstraintType.SEPARATED,
            ConstraintType.ENCLOSING,
            ConstraintType.ALIGNED,
            ConstraintType.ON_SIDE,
            ConstraintType.ANCHORED,
            ConstraintType.LOOP_AREA,
        }

    def test_removed_dispatch_architecture_cannot_reappear(self):
        src = Path(__file__).resolve().parents[2] / "src" / "temper_placer"
        forbidden = (
            "BaseConstraint.backends",
            "HANDLER_REGISTRY",
            "register_handler",
            "pcl.sat_bridge",
            "CompilationTarget",
            "SemanticTag",
            "supported_targets",
        )
        violations = [
            f"{path.relative_to(src)}: {token}"
            for path in src.rglob("*.py")
            for token in forbidden
            if token in path.read_text(encoding="utf-8")
        ]
        assert violations == []

    def test_handler_catalog_is_immutable(self):
        with pytest.raises(TypeError):
            TYPE_HANDLERS[ConstraintType.ADJACENT] = TYPE_HANDLERS[ConstraintType.ALIGNED]  # type: ignore[index]

    def test_duplicate_handler_entries_fail_during_construction(self):
        handler = TYPE_HANDLERS[ConstraintType.ADJACENT]
        with pytest.raises(RuntimeError, match="duplicate.*ADJACENT"):
            _build_type_handlers(
                (
                    (ConstraintType.ADJACENT, handler),
                    (ConstraintType.ADJACENT, handler),
                    *(
                        (constraint_type, TYPE_HANDLERS[constraint_type])
                        for constraint_type in TYPE_HANDLERS
                        if constraint_type is not ConstraintType.ADJACENT
                    ),
                )
            )

    def test_missing_supported_handler_fails_during_construction(self):
        entries = tuple(
            (constraint_type, TYPE_HANDLERS[constraint_type])
            for constraint_type in TYPE_HANDLERS
            if constraint_type is not ConstraintType.ADJACENT
        )
        with pytest.raises(RuntimeError, match="missing=ADJACENT"):
            _build_type_handlers(entries)

    def test_explicitly_unsupported_handler_fails_during_construction(self):
        entries = tuple(
            (constraint_type, TYPE_HANDLERS[constraint_type])
            for constraint_type in TYPE_HANDLERS
        ) + ((ConstraintType.KEEPOUT, TYPE_HANDLERS[ConstraintType.ALIGNED]),)
        with pytest.raises(RuntimeError, match="unexpected=KEEPOUT"):
            _build_type_handlers(entries)

    def test_compiler_receipt_accounts_for_every_input(self):
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Keep the switching pair close",
        )

        result = compile_pcl_for_router(
            ConstraintCollection([constraint]),
            _context("Q1", "Q2"),
        )

        assert len(result.receipts) == 1
        receipt = result.receipts[0]
        assert receipt.pcl_id == constraint.id
        assert receipt.disposition is CompilationDisposition.COMPILED
        assert receipt.outputs == ()  # no channel skeletons is a valid no-op
        result.require_complete(expected_count=1)

    def test_router_irrelevant_keepout_is_explicitly_not_applicable(self):
        constraint = KeepoutConstraint(
            zone_name="HV_KEEP_OUT",
            tier=ConstraintTier.HARD,
            margin_mm=1.0,
            because="Keep high-voltage components out of this zone",
        )

        result = compile_pcl_for_router(
            ConstraintCollection([constraint]),
            _context(),
        )

        assert len(result.receipts) == 1
        receipt = result.receipts[0]
        assert receipt.constraint_type is ConstraintType.KEEPOUT
        assert receipt.disposition is CompilationDisposition.NOT_APPLICABLE
        assert receipt.disposition is not CompilationDisposition.COMPILED
        assert receipt.outputs == ()
        # An explicitly accounted non-router constraint is still complete.
        result.require_complete(expected_count=1)

    def test_unresolved_constraint_fails_closed(self):
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Unresolvable references must fail",
        )

        with pytest.raises(RouterConstraintCompilationError, match=constraint.id):
            compile_pcl_for_router(
                ConstraintCollection([constraint]),
                _context(),
            )
