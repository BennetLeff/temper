"""The concurrency probe: attribution under simultaneous calls.

Runs in CI because it needs no model -- it is handed a transport. That is the point
of keeping the attribution probe separate from the live canary: the property it
checks (every call lands on its own session and all of them reach the root) is a
property of the ledger and the transport, not of the provider.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from temper_harness.canary import probe_fanout
from temper_harness.ledger import AggregateNotClosedError, LedgerStore, LineageRegistry, aggregate
from temper_harness.ledger.errors import NestedRootError
from temper_harness.provider.errors import IncompleteStream
from temper_harness.provider.interface import Event, Request, Terminal
from temper_harness.provider.messages import ChatMessage

SESSIONS = tuple(f"worker-{index}" for index in range(6))


def _envelope(*, prompt: int, completion: int) -> dict[str, Any]:
    return {
        "id": "msg",
        "model": "deepseek-flash",
        "finish_reason": "stop",
        "content": "done",
        "reasoning_content": "",
        "system_fingerprint": "fp-test",
        "tool_calls": [],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": 0,
            "cached_input_tokens": 0,
            "total_tokens": prompt + completion,
        },
        "served_from": "live",
    }


class _ScriptedFanout:
    """A transport that answers each call with a distinct, known usage block.

    Thread-safe on purpose: the probe really does run these concurrently, so a fake
    with shared mutable state would be testing the fake rather than the probe.
    """

    def __init__(self, *, fail_from: int | None = None) -> None:
        self._lock = threading.Lock()
        self._served = 0
        self._fail_from = fail_from

    @property
    def served(self) -> int:
        with self._lock:
            return self._served

    def stream(self, request: Request) -> Iterator[Event]:
        with self._lock:
            index = self._served
            self._served += 1
        if self._fail_from is not None and index >= self._fail_from:
            raise IncompleteStream(f"call {index} was cut off")
        yield Terminal(_envelope(prompt=10 * (index + 1), completion=index + 1))


def _request() -> Request:
    return Request(
        model="deepseek-flash",
        messages=[ChatMessage(role="user", content="place it")],
        served_from="live",
    )


def _probe(tmp_path: Path, transport: _ScriptedFanout, *, sessions: tuple[str, ...] = SESSIONS):
    store = LedgerStore(tmp_path / "ledger")
    return probe_fanout(
        store=store, transport=transport, request=_request(), sessions=list(sessions)
    )


def test_every_concurrent_call_is_attributed_to_its_own_session(tmp_path: Path) -> None:
    transport = _ScriptedFanout()
    result = _probe(tmp_path, transport)

    assert transport.served == len(SESSIONS)
    assert sorted(result.sessions) == sorted(SESSIONS)
    assert len(set(result.sessions)) == len(SESSIONS)
    assert len({outcome.call_id for outcome in result.outcomes}) == len(SESSIONS)


def test_every_concurrent_call_is_included_in_the_root_aggregate(tmp_path: Path) -> None:
    """The incident shape, measured rather than assumed.

    Six root sessions reported 331.9 M tokens against a true 2.68 B, with 73.7 % of
    spend in workers the aggregate could not see. So the assertion is not that the
    probe returned six outcomes -- it is that the *aggregate* accounts for all six.
    """
    transport = _ScriptedFanout()
    result = _probe(tmp_path, transport)

    expected = sum(10 * (index + 1) + (index + 1) for index in range(len(SESSIONS)))
    assert result.aggregate.call_count == len(SESSIONS)
    assert result.aggregate.inclusive_tokens == expected
    assert result.aggregate.reconciles


def test_worker_spend_lands_in_the_descendant_bucket(tmp_path: Path) -> None:
    """The distinction the probe got wrong before a test caught it.

    The aggregate decides "root exclusive" from whether a row's session has a parent.
    Registering the workers as root-level sessions -- which this probe did, until this
    test existed -- files all of their spend under the root, which is the incident
    reproduced *inside the instrument meant to detect it*: six workers, 231 tokens,
    every one of them reported as the root's own.
    """
    transport = _ScriptedFanout()
    result = _probe(tmp_path, transport)

    expected = sum(10 * (index + 1) + (index + 1) for index in range(len(SESSIONS)))
    assert result.aggregate.descendant_tokens == expected
    assert result.descendant_tokens == expected
    assert result.aggregate.root_exclusive_tokens == 0
    assert result.aggregate.inclusive_tokens == result.aggregate.descendant_tokens


def test_the_root_session_is_not_itself_a_worker(tmp_path: Path) -> None:
    """Its spend would be root-exclusive and would hide the distinction above."""
    store = LedgerStore(tmp_path / "ledger")
    transport = _ScriptedFanout()
    with pytest.raises(ValueError, match="cannot also be a worker"):
        probe_fanout(
            store=store,
            transport=transport,
            request=_request(),
            sessions=["fanout-root"],
            root_session="fanout-root",
        )


def test_the_outcomes_carry_the_usage_the_aggregate_counted(tmp_path: Path) -> None:
    """Both views of the same six calls, so one cannot drift from the other."""
    transport = _ScriptedFanout()
    result = _probe(tmp_path, transport)

    per_call = sum(outcome.tokens for outcome in result.outcomes)
    assert per_call == result.aggregate.inclusive_tokens
    assert {outcome.usage_source for outcome in result.outcomes} == {"provider"}


def test_a_worker_thread_does_not_inherit_the_root(tmp_path: Path) -> None:
    """Why the probe attaches explicitly, asserted rather than assumed.

    ``contextvars`` do not cross a bare thread boundary, so a worker starts with no
    active root. The refusal is typed, which is the property that matters: an
    unattached worker fails loudly instead of minting a sibling root whose spend
    would be invisible to the parent's total.
    """
    store = LedgerStore(tmp_path / "ledger")
    registry = LineageRegistry(store)
    root_id = registry.open_root()
    registry.register_session("worker-0")

    failures: list[BaseException] = []

    def worker() -> None:
        try:
            LineageRegistry(store).open_call("worker-0")
        except BaseException as err:  # noqa: BLE001 - the point is which error
            failures.append(err)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert len(failures) == 1
    assert isinstance(failures[0], NestedRootError)
    assert store.call_rows() == []
    assert aggregate(store, root_id).call_count == 0


def test_an_attached_worker_is_attributed_to_the_parents_root(tmp_path: Path) -> None:
    """The documented path, and the one the probe takes."""
    store = LedgerStore(tmp_path / "ledger")
    registry = LineageRegistry(store)
    root_id = registry.open_root()
    registry.register_session("worker-0")

    def worker() -> None:
        child = LineageRegistry(store)
        child.attach_root(root_id)
        handle = child.open_call("worker-0")
        child.close_call(
            handle,
            status="ok",
            served_from="live",
            usage_source="unknown",
        )
        child.detach_root()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert aggregate(store, root_id).call_count == 1


def test_a_cut_off_call_fails_the_probe_rather_than_under_reporting(tmp_path: Path) -> None:
    """The escape hatch the aggregate refuses, refused here too.

    A probe whose purpose is to prove nothing went missing is the last place to accept
    a lower bound -- so an incomplete call raises instead of returning a total that
    quietly excludes it.
    """
    transport = _ScriptedFanout(fail_from=2)
    with pytest.raises(AggregateNotClosedError) as caught:
        _probe(tmp_path, transport)
    assert any("incomplete" in reason for reason in caught.value.reasons)


def test_the_probe_refuses_an_empty_or_duplicated_session_list(tmp_path: Path) -> None:
    """A duplicate session would merge two calls into one attribution."""
    store = LedgerStore(tmp_path / "ledger")
    transport = _ScriptedFanout()
    with pytest.raises(ValueError, match="at least one session"):
        probe_fanout(store=store, transport=transport, request=_request(), sessions=[])
    with pytest.raises(ValueError, match="own session"):
        probe_fanout(
            store=store,
            transport=transport,
            request=_request(),
            sessions=["worker-0", "worker-0"],
        )
