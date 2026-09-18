"""Aggregation: descendant-inclusive, and fail-closed on anything unmeasured."""

from __future__ import annotations

import pytest

from temper_harness.ledger import aggregate, aggregate_lower_bound
from temper_harness.ledger.aggregate import AggregateNotClosedError
from temper_harness.ledger.errors import UnresolvedLineageError
from temper_harness.ledger.lineage import LineageRegistry
from temper_harness.ledger.store import LedgerStore

USAGE = {
    "prompt_tokens": None,
    "completion_tokens": None,
    "reasoning_tokens": None,
    "cached_input_tokens": None,
    "total_tokens": None,
}


def _usage(prompt: int, completion: int, *, reasoning: int | None = None) -> dict[str, int | None]:
    """A usage block whose provider total is the additive sum, as measured.

    ``total_tokens`` is filled in because the committed schema requires it and
    because the aggregate reconciles against it; a row that omitted it would be
    counted as un-reconcilable rather than as agreeing.
    """
    return {
        **USAGE,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "total_tokens": prompt + completion,
    }


def _tree(
    registry: LineageRegistry,
) -> tuple[str, str, str, str]:
    """Build root -> child -> grandchild and close one call at each level."""
    root_id = registry.open_root()
    registry.register_session("root-session")
    registry.register_session("child", parent_session_id="root-session")
    registry.register_session("grandchild", parent_session_id="child")
    for session, prompt, completion in (
        ("root-session", 100, 0),
        ("child", 200, 0),
        ("grandchild", 300, 0),
    ):
        handle = registry.open_call(session)
        registry.close_call(
            handle,
            status="ok",
            served_from="live",
            usage=_usage(prompt, completion),
            usage_source="provider",
        )
    return root_id, "root-session", "child", "grandchild"


def test_reconciliation_invariant(registry: LineageRegistry, store: LedgerStore) -> None:
    """inclusive == exclusive + descendants, over a three-level tree."""
    root_id, *_ = _tree(registry)
    result = aggregate(store, root_id)

    assert result.root_exclusive_tokens == 100
    assert result.descendant_tokens == 500
    assert result.inclusive_tokens == 600
    assert result.inclusive_tokens == (result.root_exclusive_tokens + result.descendant_tokens)
    assert result.call_count == 3
    assert not result.is_lower_bound


def test_root_only_sum_would_under_report(registry: LineageRegistry, store: LedgerStore) -> None:
    """The incident shape this module exists to prevent.

    Six root sessions reported 331.9 M tokens against a true 2.68 B. Here the
    root-exclusive figure is 100 of a true 600, so any API that returned the
    exclusive number as "the cost" would be wrong by 83 %.
    """
    root_id, *_ = _tree(registry)
    result = aggregate(store, root_id)
    assert result.root_exclusive_tokens != result.inclusive_tokens


def test_aggregate_is_the_only_public_cost_entry_point() -> None:
    """R2: no public API may hand back a session- or level-exclusive total."""
    import temper_harness.ledger as ledger_pkg

    public = set(ledger_pkg.__all__)
    assert "aggregate" in public
    assert "aggregate_lower_bound" in public
    assert not any(name.startswith(("sum_", "total_")) for name in public)


def test_unregistered_root_raises(registry: LineageRegistry, store: LedgerStore) -> None:
    registry.open_root()
    with pytest.raises(UnresolvedLineageError):
        aggregate(store, "root-never-opened")


def test_unattributable_row_fails_the_whole_aggregate(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """A row whose chain does not resolve is evidence, not an omission.

    The aggregate must refuse rather than skip it, because skipping is exactly
    how spend leaves the total without anyone noticing.
    """
    root_id, *_ = _tree(registry)
    store.append_ledger(
        {
            "kind": "call_terminal",
            "lineage": {
                "root_id": root_id,
                "session_id": "ghost-session",
                "parent_session_id": None,
                "call_id": "call-ghost",
                "attempt": 0,
            },
            "status": "ok",
            "served_from": "live",
            "usage": _usage(9_999, 0),
            "usage_source": "provider",
            "price_table_id": "t",
            "price_window": None,
            "provider_reported_usd": None,
            "estimated_usd": None,
        }
    )
    with pytest.raises(AggregateNotClosedError) as excinfo:
        aggregate(store, root_id)
    assert any("ghost-session" in reason for reason in excinfo.value.reasons)


def test_crash_leaves_inflight_and_fails_closed(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """A killed worker cannot close a row; the open record is the proof."""
    root_id, *_ = _tree(registry)
    registry.open_call("child")  # never closed: simulates the crash

    with pytest.raises(AggregateNotClosedError) as excinfo:
        aggregate(store, root_id)
    assert any("never reached a terminal record" in reason for reason in excinfo.value.reasons)


@pytest.mark.parametrize("status", ["cancelled", "incomplete"])
def test_unmeasured_terminals_fail_closed(
    registry: LineageRegistry, store: LedgerStore, status: str
) -> None:
    """A cancelled or truncated call consumed tokens we cannot count."""
    root_id, *_ = _tree(registry)
    handle = registry.open_call("child")
    registry.close_call(handle, status=status, served_from="live")

    with pytest.raises(AggregateNotClosedError):
        aggregate(store, root_id)


def test_replayed_rows_cannot_be_scored(registry: LineageRegistry, store: LedgerStore) -> None:
    """A replay run must not be quotable as spend at fixed expenditure."""
    root_id, *_ = _tree(registry)
    handle = registry.open_call("child")
    registry.close_call(
        handle,
        status="ok",
        served_from="replay",
        usage=_usage(1, 1),
        usage_source="provider",
    )

    with pytest.raises(AggregateNotClosedError) as excinfo:
        aggregate(store, root_id)
    assert any("recording" in reason for reason in excinfo.value.reasons)


def test_lower_bound_is_labelled_and_excludes_the_gaps(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """R15's escape hatch: allowed, but it must say so out loud.

    The cancelled call carries usage precisely so the exclusion is observable —
    a cancelled row with a null usage block would make this test pass for the
    wrong reason.
    """
    root_id, *_ = _tree(registry)
    handle = registry.open_call("child")
    registry.close_call(
        handle,
        status="cancelled",
        served_from="live",
        usage=_usage(9_999, 0),
        usage_source="provider",
    )

    with pytest.raises(AggregateNotClosedError):
        aggregate(store, root_id)

    result = aggregate_lower_bound(store, root_id)
    assert result.is_lower_bound
    assert result.excluded
    assert result.inclusive_tokens == 600  # the 9_999 is excluded, not summed
    # Counts the rows that were summed, not the rows in scope: `reconciles` gates on
    # this being non-zero, so counting an excluded row would let a lower bound claim a
    # non-vacuous agreement it had not earned.
    assert result.call_count == 3


def test_every_reason_is_reported_not_just_the_first(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """One run should surface every gap, not drip-feed them across retries."""
    root_id, *_ = _tree(registry)
    registry.open_call("child")
    handle = registry.open_call("grandchild")
    registry.close_call(handle, status="cancelled", served_from="live")

    with pytest.raises(AggregateNotClosedError) as excinfo:
        aggregate(store, root_id)
    assert len(excinfo.value.reasons) >= 2


# -- the token arithmetic, pinned by the capture -----------------------------


def test_reasoning_tokens_do_not_add_to_completion_tokens(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """The over-count this module would have shipped.

    Captured from the live provider: a trivial completion reported
    ``completion_tokens=18`` with ``completion_tokens_details.reasoning_tokens=15``
    and three tokens of visible content. Reasoning is a SUBSET of completion, so
    summing both reports 33 output tokens where the provider counted 18 -- an
    error larger than the value it is measuring, and in the direction that makes
    a fixed-expenditure comparison look more expensive than it was.

    This is the fault injection for the additive set: move ``reasoning_tokens``
    into ``ADDITIVE_USAGE_FIELDS`` and this test goes red.
    """
    root_id = registry.open_root()
    registry.register_session("root-session")
    handle = registry.open_call("root-session")
    registry.close_call(
        handle,
        status="ok",
        served_from="live",
        usage=_usage(37, 18, reasoning=15),
        usage_source="provider",
    )

    result = aggregate(store, root_id)
    assert result.inclusive_tokens == 55  # 37 + 18, not 37 + 18 + 15
    assert result.inclusive_tokens == result.provider_total_tokens


def test_the_aggregate_reconciles_against_the_providers_own_total(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """The one external check on the accounting that this provider allows.

    KTD7 wanted computed and provider-reported *cost* to agree; the provider
    reports no cost field at all, so tokens are where that check can live.
    """
    root_id, *_ = _tree(registry)
    result = aggregate(store, root_id)
    assert result.rows_without_provider_total == 0
    assert result.reconciles


def test_reconciliation_fails_closed_when_a_row_withholds_the_total(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """Silence is not agreement, and the schema lets a field be null (R4)."""
    root_id, *_ = _tree(registry)
    handle = registry.open_call("child")
    registry.close_call(
        handle,
        status="ok",
        served_from="live",
        usage={**_usage(1, 1), "total_tokens": None},
        usage_source="provider",
    )

    result = aggregate(store, root_id)
    assert result.rows_without_provider_total == 1
    assert not result.reconciles


def test_reconciliation_fails_closed_on_an_empty_selection(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """A vacuous agreement -- 0 == 0 over no rows -- is not a clean verdict."""
    root_id = registry.open_root()
    registry.register_session("root-session")
    result = aggregate(store, root_id)
    assert result.call_count == 0
    assert not result.reconciles


def test_reconciliation_reports_a_genuine_mismatch(
    registry: LineageRegistry, store: LedgerStore
) -> None:
    """A provider total that disagrees with the parts is a real finding."""
    root_id = registry.open_root()
    registry.register_session("root-session")
    handle = registry.open_call("root-session")
    registry.close_call(
        handle,
        status="ok",
        served_from="live",
        usage={**_usage(37, 18, reasoning=15), "total_tokens": 9_999},
        usage_source="provider",
    )

    result = aggregate(store, root_id)
    assert result.rows_without_provider_total == 0
    assert not result.reconciles
    assert result.inclusive_tokens == 55
