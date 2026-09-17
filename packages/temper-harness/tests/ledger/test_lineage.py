"""Lineage registration: the refusals that keep accounting honest."""

from __future__ import annotations

import pytest

from temper_harness.ledger.errors import (
    AmbientRootError,
    NestedRootError,
    UnregisteredRootError,
    UnresolvedLineageError,
)
from temper_harness.ledger.lineage import ROOT_ENV_VAR, LineageRegistry, active_root


def test_open_root_registers_and_activates(registry: LineageRegistry, store) -> None:
    root_id = registry.open_root()
    assert active_root() == root_id
    assert root_id in store.root_ids()


def test_nested_open_root_is_refused(registry: LineageRegistry, store) -> None:
    """The self-rooting escape: a child must not mint a sibling root.

    Without this refusal the child's rows stay schema-valid, its own root
    resolves, and the aggregate over the true root silently returns less than
    the real spend.
    """
    registry.open_root()
    with pytest.raises(NestedRootError):
        registry.open_root()
    assert len(store.root_ids()) == 1


def test_ambient_root_blocks_open_and_attach_recovers(
    registry: LineageRegistry, store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forked child inherits the root and must attach, not open a sibling."""
    parent_root = registry.open_root()
    registry.register_session("worker")
    registry.detach_root()

    monkeypatch.setenv(ROOT_ENV_VAR, parent_root)
    with pytest.raises(AmbientRootError):
        registry.open_root()

    assert registry.attach_root(parent_root) == parent_root
    assert active_root() == parent_root
    assert len(store.root_ids()) == 1


def test_attach_unknown_root_is_refused(registry: LineageRegistry) -> None:
    with pytest.raises(UnregisteredRootError):
        registry.attach_root("root-does-not-exist")


def test_session_registration_requires_an_active_root(registry: LineageRegistry) -> None:
    with pytest.raises(NestedRootError):
        registry.register_session("orphan")


def test_session_under_unregistered_parent_is_refused(registry: LineageRegistry) -> None:
    registry.open_root()
    with pytest.raises(UnresolvedLineageError):
        registry.register_session("child", parent_session_id="never-registered")


def test_open_call_requires_a_registered_session(registry: LineageRegistry) -> None:
    registry.open_root()
    with pytest.raises(UnresolvedLineageError):
        registry.open_call("never-registered")


def test_open_call_writes_an_inflight_record(registry: LineageRegistry, store) -> None:
    registry.open_root()
    registry.register_session("root-session")
    handle = registry.open_call("root-session")

    inflight = store.inflight_records()
    assert [r["call_id"] for r in inflight] == [handle.call_id]
    assert store.call_rows() == []


def test_close_call_writes_exactly_one_terminal_row(registry: LineageRegistry, store) -> None:
    registry.open_root()
    registry.register_session("root-session")
    handle = registry.open_call("root-session")
    registry.close_call(handle, status="ok", served_from="live")

    rows = store.call_rows()
    assert len(rows) == 1
    assert rows[0]["lineage"]["call_id"] == handle.call_id


def test_a_retry_is_a_separate_row_not_a_collapsed_one(registry: LineageRegistry, store) -> None:
    """R3: retries are never collapsed, so a failed attempt stays visible."""
    registry.open_root()
    registry.register_session("root-session")
    first = registry.open_call("root-session", attempt=0)
    registry.close_call(first, status="failed", served_from="live")
    second = registry.open_call("root-session", attempt=1)
    registry.close_call(second, status="ok", served_from="live")

    rows = store.call_rows()
    assert len(rows) == 2
    assert [r["lineage"]["attempt"] for r in rows] == [0, 1]
    assert [r["status"] for r in rows] == ["failed", "ok"]


def test_unreported_usage_is_null_never_zero(registry: LineageRegistry, store) -> None:
    """R4: a missing count and a measured zero are different facts.

    A column that reads 0 because the provider said nothing is the
    structurally-always-zero publishable figure this repo has been bitten by.
    """
    registry.open_root()
    registry.register_session("root-session")
    handle = registry.open_call("root-session")
    registry.close_call(handle, status="failed", served_from="live", usage_source="unknown")

    usage = store.call_rows()[0]["usage"]
    assert usage == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "reasoning_tokens": None,
        "cached_input_tokens": None,
    }
    assert usage["prompt_tokens"] is None


def test_price_table_identity_is_recorded_per_row(registry: LineageRegistry, store) -> None:
    registry.open_root()
    registry.register_session("root-session")
    handle = registry.open_call("root-session")
    registry.close_call(
        handle,
        status="ok",
        served_from="live",
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "reasoning_tokens": None,
            "cached_input_tokens": None,
        },
        usage_source="provider",
        price_table_id="2026-09-17",
        provider_reported_usd=0.02,
        estimated_usd=0.019,
    )

    row = store.call_rows()[0]
    assert row["price_table_id"] == "2026-09-17"
    assert row["provider_reported_usd"] == 0.02
    assert row["estimated_usd"] == 0.019


def test_sequence_numbers_are_monotonic(registry: LineageRegistry, store) -> None:
    registry.open_root()
    registry.register_session("a")
    handle = registry.open_call("a")
    registry.close_call(handle, status="ok", served_from="live")

    seqs = [r["seq"] for r in store.ledger_records()]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
