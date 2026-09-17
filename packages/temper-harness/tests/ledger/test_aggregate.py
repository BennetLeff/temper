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
}


def _usage(prompt: int, completion: int) -> dict[str, int | None]:
    return {**USAGE, "prompt_tokens": prompt, "completion_tokens": completion}


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
