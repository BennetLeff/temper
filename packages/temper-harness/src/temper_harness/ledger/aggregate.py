"""Root-scoped cost aggregation that fails closed.

R2 makes this the only public way to obtain a cost total, and R15 makes it
refuse rather than under-report. Both clauses exist because of one incident
shape: the prior harness attempt's six root sessions reported 331.9 M tokens
against a true 2.68 B, with 73.7 % of spend sitting in subagent workers that a
root-only sum could not see. An aggregate that silently sums what it can see is
worse than no aggregate, because it is quotable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from temper_harness.ledger.errors import UnresolvedLineageError
from temper_harness.ledger.store import LedgerStore

USAGE_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_input_tokens",
)

#: Terminal statuses the aggregate refuses to fold into a total (R15).
CLOSED_STATUSES = ("cancelled", "incomplete")


class AggregateNotClosedError(Exception):
    """The subtree contains something the aggregate must not sum past.

    ``reasons`` enumerates every cause, not just the first, so one run reports
    all the gaps rather than drip-feeding them across retries.
    """

    def __init__(self, root_id: str, reasons: list[str]) -> None:
        self.root_id = root_id
        self.reasons = reasons
        joined = "; ".join(reasons)
        super().__init__(f"aggregate for root {root_id!r} is not closed: {joined}")


@dataclass(frozen=True, slots=True)
class Aggregate:
    """A closed total: ``inclusive == exclusive + descendants``."""

    root_id: str
    root_exclusive_tokens: int
    descendant_tokens: int
    root_exclusive_usd: float
    descendant_usd: float
    call_count: int
    is_lower_bound: bool = False
    excluded: tuple[str, ...] = field(default=())

    @property
    def inclusive_tokens(self) -> int:
        return self.root_exclusive_tokens + self.descendant_tokens

    @property
    def inclusive_usd(self) -> float:
        return self.root_exclusive_usd + self.descendant_usd


def _tokens(row: dict[str, Any]) -> int:
    """Sum known usage fields. ``None`` contributes nothing but is not zero."""
    usage = row.get("usage") or {}
    return sum(v for k, v in usage.items() if k in USAGE_FIELDS and isinstance(v, int))


def _usd(row: dict[str, Any]) -> float:
    value = row.get("estimated_usd")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _diagnose(store: LedgerStore, root_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Return the in-scope rows plus the reasons the subtree is not closed."""
    reasons: list[str] = []
    if root_id not in store.root_ids():
        raise UnresolvedLineageError(f"root {root_id!r} is not registered in this ledger")

    rows = store.call_rows()

    # A row anywhere whose chain does not resolve means the ledger contains
    # spend nobody can attribute. Fail the whole aggregation rather than
    # omitting it: an orphan is evidence of incompleteness, not a row without a
    # home.
    for row in rows:
        try:
            store.resolve_root(row["lineage"]["session_id"])
        except UnresolvedLineageError as exc:
            reasons.append(f"unattributable row {row['lineage']['call_id']!r}: {exc}")

    in_scope = [r for r in rows if r["lineage"]["root_id"] == root_id]

    closed = {r["lineage"]["call_id"]: r for r in in_scope}
    opened = {r["call_id"]: r for r in store.inflight_records() if r.get("root_id") == root_id}
    for call_id in opened:
        if call_id not in closed:
            reasons.append(f"call {call_id!r} was opened and never reached a terminal record")

    for row in in_scope:
        status = row.get("status")
        if status in CLOSED_STATUSES:
            reasons.append(
                f"call {row['lineage']['call_id']!r} terminated as {status!r}; its usage is unmeasured or partial"
            )
        if row.get("served_from") == "replay":
            reasons.append(
                f"call {row['lineage']['call_id']!r} was served from a recording, not the provider"
            )

    return in_scope, reasons


def aggregate(store: LedgerStore, root_id: str) -> Aggregate:
    """Return the closed cost total for ``root_id``, or raise."""
    in_scope, reasons = _diagnose(store, root_id)
    if reasons:
        raise AggregateNotClosedError(root_id, reasons)
    return _summarize(store, root_id, in_scope, is_lower_bound=False, excluded=())


def aggregate_lower_bound(store: LedgerStore, root_id: str) -> Aggregate:
    """Return a total explicitly labelled as a lower bound.

    The escape hatch R15 allows, and only that: the result says out loud that
    it excludes rows, so a caller cannot quote it as the cost.
    """
    in_scope, reasons = _diagnose(store, root_id)
    return _summarize(store, root_id, in_scope, is_lower_bound=True, excluded=tuple(reasons))


def _summarize(
    store: LedgerStore,
    root_id: str,
    in_scope: list[dict[str, Any]],
    *,
    is_lower_bound: bool,
    excluded: tuple[str, ...],
) -> Aggregate:
    exclusive_tokens = 0
    exclusive_usd = 0.0
    descendant_tokens = 0
    descendant_usd = 0.0

    for row in in_scope:
        if is_lower_bound and (
            row.get("status") in CLOSED_STATUSES or row.get("served_from") == "replay"
        ):
            continue
        lineage = row["lineage"]
        is_root_exclusive = lineage.get("parent_session_id") is None
        tokens = _tokens(row)
        usd = _usd(row)
        if is_root_exclusive:
            exclusive_tokens += tokens
            exclusive_usd += usd
        else:
            descendant_tokens += tokens
            descendant_usd += usd

    return Aggregate(
        root_id=root_id,
        root_exclusive_tokens=exclusive_tokens,
        descendant_tokens=descendant_tokens,
        root_exclusive_usd=exclusive_usd,
        descendant_usd=descendant_usd,
        call_count=len(in_scope),
        is_lower_bound=is_lower_bound,
        excluded=excluded,
    )
