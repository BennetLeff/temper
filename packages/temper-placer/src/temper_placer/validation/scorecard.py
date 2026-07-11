"""
Continuous-margin scorecard with independent-instrument scoring contract.

U2 delivers per-gate MARGIN records (continuous, engineering units) rather
than binary CLEAN/VIOLATIONS flags.  A systematically-worse-but-still-passing
board is detectable because its thermal headroom *decreases* without dropping
below zero.

The scoring contract structurally separates the **scorer** (independent
instrument) from the **field** under test: the API raises if the field's own
solver is passed as its scorer (runtime assertion guard).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from temper_placer.regression.physics_oracle import (
    PhysicsOracleResult,
    compute_oracle_margins,
)

# ---------------------------------------------------------------------------
# Independence guard
# ---------------------------------------------------------------------------


class IndependenceViolationError(ValueError):
    """Raised when a field's own solver is passed as its independent scorer."""


def _assert_independent(scorer_id: str, field_id: str) -> None:
    """Runtime guard: scorer and field must be different instruments.

    Two references to the same value is self-consistency, not validation.
    """
    if scorer_id == field_id:
        raise IndependenceViolationError(
            f"Independence violation: scorer '{scorer_id}' is the same "
            f"instrument as field '{field_id}'.  "
            f"Self-scoring is self-consistency, not validation.  "
            f"Pass a genuinely independent scorer (e.g. physics oracle, "
            f"thermal camera, or a different solver)."
        )


# ---------------------------------------------------------------------------
# Scoring protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ScorerFunction(Protocol):
    """Protocol for an independent scoring instrument.

    Any callable that accepts placement info and returns a
    ``PhysicsOracleResult`` satisfies this protocol.
    """

    def __call__(
        self,
        placement: Any,
        board: Any,
        netlist: Any,
    ) -> PhysicsOracleResult: ...


# ---------------------------------------------------------------------------
# Gate margin record
# ---------------------------------------------------------------------------


@dataclass
class GateMargin:
    """Continuous margin for a single validation gate."""

    gate_name: str
    value: float
    unit: str
    raw_score: float = 0.0
    is_scorable: bool = True

    @property
    def margin(self) -> float:
        """Alias for ``value`` — the signed headroom in engineering units."""
        return self.value


# ---------------------------------------------------------------------------
# Margin scorecard
# ---------------------------------------------------------------------------


@dataclass
class MarginScorecard:
    """Continuous-margin scorecard for a placement under test.

    Produced by an *independent* scorer (not the field's own solver)
    so the recorded margins are genuine validation signals, not
    self-consistency artifacts.
    """

    board_id: str
    scorer_id: str
    margins: list[GateMargin] = field(default_factory=list)

    @classmethod
    def from_oracle_result(
        cls,
        result: PhysicsOracleResult,
        *,
        scorer_id: str,
        max_heatspread_mm: float = 10.0,
        hv_lv_threshold_mm: float = 6.5,
        max_loop_area_mm2: float = 100.0,
    ) -> MarginScorecard:
        """Build a scorecard from a physics-oracle result.

        Extracts continuous margins from the oracle's ``quality_report``
        and converts them to engineering-unit headroom values.

        A gate whose metric returned the default pass-through value
        (e.g.  ``1.0`` because no components were present) is flagged as
        ``is_scorable=False`` — the dynamic-range smoke test fails, and
        the scorecard consumer MUST NOT treat that margin as validation
        signal.
        """
        report = result.quality_report or {}
        margin_dict = compute_oracle_margins(
            report,
            max_heatspread_mm=max_heatspread_mm,
            hv_lv_threshold_mm=hv_lv_threshold_mm,
            max_loop_area_mm2=max_loop_area_mm2,
        )

        gate_margins: list[GateMargin] = []

        # --- Thermal headroom (°C proxy via edge-distance mm) ---
        thermal_score = report.get("thermal_score", 1.0)
        thermal_scorable = _is_scorable_metric(
            thermal_score, report, key="thermal_score"
        )
        gate_margins.append(
            GateMargin(
                gate_name="thermal",
                value=margin_dict.get("thermal_headroom_mm", 0.0),
                unit="mm",
                raw_score=thermal_score,
                is_scorable=thermal_scorable,
            )
        )

        # --- HV/LV clearance margin (mm) ---
        clearance_score = report.get("hv_lv_clearance_score", 1.0)
        clearance_scorable = _is_scorable_metric(
            clearance_score, report, key="hv_lv_clearance_score"
        )
        gate_margins.append(
            GateMargin(
                gate_name="hv_lv_clearance",
                value=margin_dict.get("clearance_margin_mm", 0.0),
                unit="mm",
                raw_score=clearance_score,
                is_scorable=clearance_scorable,
            )
        )

        # --- Loop area margin (mm²) ---
        loop_score = report.get("loop_area_score", 1.0)
        loop_scorable = _is_scorable_metric(
            loop_score, report, key="loop_area_score"
        )
        gate_margins.append(
            GateMargin(
                gate_name="loop_area",
                value=margin_dict.get("loop_area_margin_mm2", 0.0),
                unit="mm2",
                raw_score=loop_score,
                is_scorable=loop_scorable,
            )
        )

        # --- Compactness (utilization ratio) ---
        compact_score = report.get("compactness_score", 1.0)
        compact_scorable = _is_scorable_metric(
            compact_score, report, key="compactness_score"
        )
        gate_margins.append(
            GateMargin(
                gate_name="compactness",
                value=compact_score,
                unit="ratio",
                raw_score=compact_score,
                is_scorable=compact_scorable,
            )
        )

        return cls(
            board_id=result.board_id,
            scorer_id=scorer_id,
            margins=gate_margins,
        )

    def scorable_margins(self) -> list[GateMargin]:
        """Return only margins that passed the dynamic-range smoke test."""
        return [m for m in self.margins if m.is_scorable]

    def margin_for(self, gate_name: str) -> GateMargin | None:
        """Look up a margin by gate name."""
        for m in self.margins:
            if m.gate_name == gate_name:
                return m
        return None


# ---------------------------------------------------------------------------
# Primary public API
# ---------------------------------------------------------------------------


def build_scorecard(
    placement: Any,
    board: Any,
    netlist: Any,
    *,
    scorer: ScorerFunction,
    scorer_id: str,
    field_id: str,
) -> MarginScorecard:
    """Build a margin scorecard using an **independent** scorer.

    Parameters
    ----------
    placement:
        The placement result produced by the *field under test*.
    board:
        Board geometry.
    netlist:
        Design netlist.
    scorer:
        *Independent* callable that scores the placement and returns a
        ``PhysicsOracleResult``.  Must be different from the field's own
        solver.
    scorer_id:
        Human-readable identifier for the scorer (e.g.
        ``"physics_oracle_v1"``).  Used in the independence assertion.
    field_id:
        Human-readable identifier for the field under test (e.g.
        ``"thermal_field_v2"``).  Used in the independence assertion.

    Returns
    -------
    MarginScorecard
        Continuous-margin scorecard with per-gate headroom values.

    Raises
    ------
    IndependenceViolationError
        If ``scorer_id == field_id`` — self-scoring is not validation.
    """
    _assert_independent(scorer_id=scorer_id, field_id=field_id)

    oracle_result: PhysicsOracleResult = scorer(placement, board, netlist)
    return MarginScorecard.from_oracle_result(
        oracle_result,
        scorer_id=scorer_id,
    )


def score_placement_via_oracle(
    placement: Any,
    board: Any,
    netlist: Any,
    *,
    scorer_id: str = "physics_oracle",
    field_id: str,
) -> MarginScorecard:
    """Convenience: score a placement through the physics oracle.

    This is the standard path for U3 consumers.  The scorer is the
    physics oracle (imported here), which is structurally independent of
    any placement field.
    """
    from temper_placer.regression.physics_oracle import score_placement

    def _oracle_scorer(placement, board, netlist):
        report = score_placement(placement, board, netlist)
        # Synthesize a minimal PhysicsOracleResult
        return PhysicsOracleResult(
            board_id=getattr(board, "name", "unknown"),
            passed=True,
            quality_report=report,
        )

    _assert_independent(scorer_id=scorer_id, field_id=field_id)
    result = _oracle_scorer(placement, board, netlist)
    return MarginScorecard.from_oracle_result(result, scorer_id=scorer_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_scorable_metric(
    score: float,
    report: dict[str, Any],
    *,
    key: str,
    default_value: float = 1.0,
) -> bool:
    """Dynamic-range smoke test for a single metric.

    A gate whose tolerance floor swallows ``0.0`` is a false-pass machine.
    This function guards against metrics that return their default value
    because no real computation happened (e.g. empty component set).

    Returns ``False`` if the metric is at its default pass-through value,
    indicating the metric was not exercised and the margin is not a
    genuine validation signal.
    """
    return score != default_value
