"""
Stage Ledger: tracked object cardinality across pipeline stage boundaries.

The StageLedger records pre-stage and post-stage object counts for
key pipeline artifacts (nets, channels, vias, trace segments, components)
and validates that cardinality changes are expected and consistent.

Follows the ``fail_on_violation=True`` pattern from DRCFence:
``StageLedgerImbalanceError`` is raised when an imbalance is detected
and the ledger is in strict mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)


class StageLedgerImbalanceError(Exception):
    """Raised when the ledger detects an object count mismatch across a stage."""


@dataclass
class LedgerReport:
    """Phase 1 ledger report: balanced state + log message.

    A full dataclass representation is deferred to Phase 2.
    """

    is_balanced: bool
    stage_name: str
    message: str

    def __str__(self) -> str:
        status = "BALANCED" if self.is_balanced else "IMBALANCED"
        return f"[LedgerReport {status}] {self.stage_name}: {self.message}"


@dataclass
class _CardinalitySnapshot:
    """Internal snapshot of tracked object counts."""

    net_count: int = 0
    component_count: int = 0
    channel_count: int = 0
    via_count: int = 0
    segment_count: int = 0


@dataclass
class StageLedger:
    """Tracks object cardinality before and after each stage.

    Records pre-stage and post-stage counts.  When ``fail_on_imbalance``
    is True, any imbalance detected at ``checkout()`` raises
    ``StageLedgerImbalanceError`` immediately rather than logging a
    warning.

    Typical use in an orchestrator::

        ledger = StageLedger(fail_on_imbalance=True)
        for stage in stages:
            ledger.checkin(state_before)
            new_state = stage.run(state_before)
            ledger.checkout(stage.name, state_after)
    """

    fail_on_imbalance: bool = False
    _pre: _CardinalitySnapshot | None = field(default=None, repr=False)
    _post: _CardinalitySnapshot | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    def checkin(self, state_or_pcb: Any) -> None:
        """Snapshot cardinality before a stage runs."""
        self._pre = _snapshot(state_or_pcb)

    def checkout(self, stage_name: str, state_or_pcb: Any) -> LedgerReport:
        """Snapshot cardinality after the stage ran and produce a report."""
        self._post = _snapshot(state_or_pcb)
        pre = self._pre
        post = self._post

        if pre is None or post is None:
            msg = "Ledger missing pre-snapshot; cannot check balance."
            report = LedgerReport(is_balanced=False, stage_name=stage_name, message=msg)
            self._raise_if_needed(report)
            return report

        imbalances = _diff(pre, post)
        if imbalances:
            lines = [f"Stage '{stage_name}' introduced cardinality imbalance:"]
            for field_name, before, after in imbalances:
                lines.append(f"  {field_name}: {before} -> {after}")
            msg = "\n".join(lines)
            report = LedgerReport(is_balanced=False, stage_name=stage_name, message=msg)
        else:
            report = LedgerReport(
                is_balanced=True,
                stage_name=stage_name,
                message="All tracked objects balanced across stage.",
            )

        self._raise_if_needed(report)
        return report

    def verify(
        self,
        stage_name: str,
        before: Any,
        after: Any,
    ) -> LedgerReport:
        """Convenience: checkin + checkout in one call."""
        self.checkin(before)
        return self.checkout(stage_name, after)

    def _raise_if_needed(self, report: LedgerReport) -> None:
        if not report.is_balanced and self.fail_on_imbalance:
            _logger.error(str(report))
            raise StageLedgerImbalanceError(str(report))
        if not report.is_balanced:
            _logger.warning(str(report))


# ------------------------------------------------------------------
def _snapshot(state_or_pcb: Any) -> _CardinalitySnapshot:
    """Extract cardinality counts from a BoardState, ParsedPCB, or
    pipeline result object."""
    snap = _CardinalitySnapshot()

    # BoardState (temper_placer.deterministic.state)
    if hasattr(state_or_pcb, "_parsed_pcb"):
        pcb = state_or_pcb._parsed_pcb
        if pcb is not None:
            if hasattr(pcb, "nets"):
                snap.net_count = len(pcb.nets)
            if hasattr(pcb, "components"):
                snap.component_count = len(pcb.components)
        if state_or_pcb.channel_skeletons:
            snap.channel_count = sum(
                len(getattr(s, "channels", []))
                for s in state_or_pcb.channel_skeletons.values()
            )
        escape_vias = getattr(state_or_pcb, "_escape_vias", None) or ()
        snap.via_count = len(escape_vias)
        return snap

    # ParsedPCB
    if hasattr(state_or_pcb, "nets"):
        snap.net_count = len(state_or_pcb.nets)
    if hasattr(state_or_pcb, "components"):
        snap.component_count = len(state_or_pcb.components)

    # Channel dicts (routing_spaces, skeletons)
    for attr in ("routing_spaces",):
        val = getattr(state_or_pcb, attr, None)
        if isinstance(val, dict):
            for v in val.values():
                if hasattr(v, "channels"):
                    snap.channel_count += len(v.channels)

    # Segment count from routing results
    results = getattr(state_or_pcb, "routing_results", None)
    if results is not None and hasattr(results, "compiled_routes"):
        for route in results.compiled_routes.values():
            path = getattr(route, "path", None)
            if hasattr(path, "segments"):  # type: ignore[union-attr]
                snap.segment_count += len(path.segments)  # type: ignore[union-attr]
            elif hasattr(path, "coordinates"):  # type: ignore[union-attr]
                snap.segment_count += max(0, len(path.coordinates) - 1)  # type: ignore[union-attr]

    return snap


def _diff(
    pre: _CardinalitySnapshot,
    post: _CardinalitySnapshot,
) -> list[tuple[str, int, int]]:
    """Return list of (field, before, after) for any count that changed."""
    diffs: list[tuple[str, int, int]] = []
    for field_name in ("net_count", "component_count", "channel_count", "via_count", "segment_count"):
        before = getattr(pre, field_name)
        after = getattr(post, field_name)
        if before != after:
            diffs.append((field_name, before, after))
    return diffs
