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

#: The usage fields that ADD. Measured against captured bytes rather than
#: assumed, and the distinction is not academic.
#:
#: ``reasoning_tokens`` is a SUBSET of ``completion_tokens``: a captured trivial
#: completion reported ``completion_tokens=18`` with
#: ``completion_tokens_details.reasoning_tokens=15`` and three tokens of content.
#: ``cached_input_tokens`` is likewise a subset of ``prompt_tokens``. Summing
#: either on top of its superset over-counts -- by 15 of 18 output tokens in that
#: example, so the error is not a rounding artefact but the majority of the
#: figure. This module exists because the prior attempt *under*-reported; an
#: aggregate that over-reports is the same defect with the sign flipped, and just
#: as quotable.
ADDITIVE_USAGE_FIELDS = ("prompt_tokens", "completion_tokens")

#: Retained for pricing rather than for summing: cached input is priced
#: differently from uncached, and reasoning output is priced differently from
#: visible output on some providers. They are breakdowns of the addends above.
BREAKDOWN_USAGE_FIELDS = ("reasoning_tokens", "cached_input_tokens")

#: The provider's own sum, kept for the reconciliation check and never added.
PROVIDER_TOTAL_FIELD = "total_tokens"

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
    #: How many rows contributed to the totals. In lower-bound mode that is fewer than
    #: the rows in scope, because the excluded ones are not summed -- and `reconciles`
    #: gates on this being non-zero, so counting an excluded row would let a lower bound
    #: claim a non-vacuous agreement it had not earned.
    call_count: int
    #: How many of the counted rows carried a computable price. `inclusive_usd` is the sum of
    #: those, so when this is short of `call_count` the USD figure is a *lower bound* on the
    #: run's cost, and `usd_is_complete` says so rather than leaving a reader to assume the
    #: total is the total.
    priced_rows: int = 0
    provider_total_tokens: int = 0
    rows_without_provider_total: int = 0
    is_lower_bound: bool = False
    excluded: tuple[str, ...] = field(default=())

    @property
    def inclusive_tokens(self) -> int:
        return self.root_exclusive_tokens + self.descendant_tokens

    @property
    def inclusive_usd(self) -> float:
        return self.root_exclusive_usd + self.descendant_usd

    @property
    def usd_is_complete(self) -> bool:
        """Whether every counted row contributed to `inclusive_usd`.

        False means the figure is a lower bound, and the caller must say so when quoting it.
        """
        return self.call_count > 0 and self.priced_rows == self.call_count

    @property
    def reconciles(self) -> bool:
        """Whether this client's arithmetic agrees with the provider's own sum.

        KTD7 wanted an external check on the accounting and could not have one
        for cost -- the provider reports no cost field -- so this is the one
        available, and it compares a number we computed against a number the
        provider computed rather than against ourselves.

        Fails closed on three counts: no rows at all (a vacuous agreement),
        any row that withheld the provider's total, and an actual mismatch. A
        caller that wants to know "is this total trustworthy" gets ``False``
        rather than a reassuring sum over rows nobody checked.
        """
        return (
            self.call_count > 0
            and self.rows_without_provider_total == 0
            and self.inclusive_tokens == self.provider_total_tokens
        )


def _tokens(row: dict[str, Any]) -> int:
    """Sum the additive usage fields.

    ``None`` contributes nothing but is not zero (R4) -- which is why the
    reconciliation below counts rows that withheld the provider's own total,
    rather than treating a missing number as agreement.
    """
    usage = row.get("usage") or {}
    return sum(v for k, v in usage.items() if k in ADDITIVE_USAGE_FIELDS and isinstance(v, int))


def _provider_total(row: dict[str, Any]) -> int | None:
    value = (row.get("usage") or {}).get(PROVIDER_TOTAL_FIELD)
    return value if isinstance(value, int) else None


def _usd(row: dict[str, Any]) -> float | None:
    """The row's cost, or ``None`` when it has none.

    ``None`` and not ``0.0``: a row the harness could not price -- unpriced, or priced
    against a table that does not know the model -- must not contribute zero to a total a
    reader will quote as "what this run cost". The distinction the usage fields keep (R4) has
    to hold for USD too, and it did not: an all-unpriced run reported ``inclusive_usd == 0.0``
    with ``reconciles`` True, which reads as a free run.
    """
    value = row.get("estimated_usd")
    return float(value) if isinstance(value, (int, float)) else None


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
    provider_total = 0
    missing_provider_total = 0
    counted = 0
    priced = 0

    for row in in_scope:
        if is_lower_bound and (
            row.get("status") in CLOSED_STATUSES or row.get("served_from") == "replay"
        ):
            continue
        counted += 1
        lineage = row["lineage"]
        is_root_exclusive = lineage.get("parent_session_id") is None
        tokens = _tokens(row)
        usd = _usd(row)
        if usd is not None:
            priced += 1
        reported_total = _provider_total(row)
        if reported_total is None:
            missing_provider_total += 1
        else:
            provider_total += reported_total
        if is_root_exclusive:
            exclusive_tokens += tokens
            if usd is not None:
                exclusive_usd += usd
        else:
            descendant_tokens += tokens
            if usd is not None:
                descendant_usd += usd

    return Aggregate(
        root_id=root_id,
        root_exclusive_tokens=exclusive_tokens,
        descendant_tokens=descendant_tokens,
        root_exclusive_usd=exclusive_usd,
        descendant_usd=descendant_usd,
        call_count=counted,
        priced_rows=priced,
        provider_total_tokens=provider_total,
        rows_without_provider_total=missing_provider_total,
        is_lower_bound=is_lower_bound,
        excluded=excluded,
    )
