"""Diagnostics for the bounded lazy-creepage cutting-plane loop.

These tests intentionally stay at the solver boundary.  They document that
each accepted verifier round appends hard cuts to the same CP-SAT model and
that the current total-deadline budget calculation can leave a later round
with only a tiny remainder.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from temper_placer.placer.cp_sat import _encoder_solve
from temper_placer.placer.cp_sat.handlers import separated as separated_handler


def _three_component_netlist() -> SimpleNamespace:
    def component(ref: str) -> SimpleNamespace:
        return SimpleNamespace(ref=ref, pins=[], bounds=(2.0, 2.0))

    return SimpleNamespace(
        components=[component("A"), component("B"), component("C")],
        nets=[],
    )


def test_lazy_creepage_cuts_are_monotone_across_verifier_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every successful cut round retains all constraints from prior rounds."""

    monkeypatch.setattr(_encoder_solve, "_resolve_loop_components", lambda _nl: {})
    verifier_rounds = iter(
        [
            [("A", "B", 12.6, 0.0)],
            [("A", "C", 12.6, 0.0)],
            [],
        ]
    )
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.netclass_constraints.verify_generated_creepage",
        lambda *_args: next(verifier_rounds),
    )

    original_encode = separated_handler.encode_separated
    cut_ids: list[str] = []
    model_constraint_counts: list[tuple[int, int]] = []

    def record_cut(constraint, components, model, ctx):
        before = len(model.model_ref.Proto().constraints)
        labels = original_encode(constraint, components, model, ctx)
        after = len(model.model_ref.Proto().constraints)
        cut_ids.append(constraint.id)
        model_constraint_counts.append((before, after))
        return labels

    monkeypatch.setattr(separated_handler, "encode_separated", record_cut)
    result = _encoder_solve.solve_placement(
        _three_component_netlist(),
        SimpleNamespace(width=40.0, height=30.0, zones=[], constraints=[]),
        timeout_ms=3_000,
        lazy_creepage=True,
        lazy_creepage_max_rounds=3,
    )

    assert result.status in ("optimal", "feasible")
    assert cut_ids == [
        "lazy_creepage_0_0_A_B",
        "lazy_creepage_1_0_A_C",
    ]
    assert result.decomposed_creepage_cuts == [
        ("A", "B", 12.6),
        ("A", "C", 12.6),
    ]
    # Encoding a cut only appends model constraints.  In particular, the
    # second round starts with the first round's post-encoding model size.
    assert model_constraint_counts[0][1] > model_constraint_counts[0][0]
    assert model_constraint_counts[1][0] >= model_constraint_counts[0][1]
    assert model_constraint_counts[1][1] > model_constraint_counts[1][0]


def test_lazy_budget_diagnostic_later_round_can_be_starved() -> None:
    """A first solve near the deadline leaves almost no post-cut budget.

    This is the reason a replay-seeded run can be FEASIBLE in round one and
    UNKNOWN immediately after adding a valid cut: the helper reserves no
    time for the next verification solve; it returns only the wall-clock
    remainder (subject to the optional per-round cap).
    """

    first_round_budget = _encoder_solve._lazy_solver_budget_seconds(
        1_000,
        elapsed_s=0.0,
        iteration_timeout_ms=None,
    )
    after_seed_and_verification_budget = _encoder_solve._lazy_solver_budget_seconds(
        1_000,
        elapsed_s=0.995,
        iteration_timeout_ms=None,
    )

    assert first_round_budget == pytest.approx(1.0)
    assert after_seed_and_verification_budget == pytest.approx(0.005)
    assert after_seed_and_verification_budget < first_round_budget * 0.01
