"""The bounded concurrency probe: attribution when calls overlap.

S0 supplies this and not a session tree, and the plan is explicit about the
boundary: "no parent/child session semantics, no ``rlm`` primitive, no daemon". What
it measures is the thing that broke before and would break silently -- whether
simultaneous calls each land on their own session and all of them reach the root
aggregate. The prior attempt reported 6 root sessions at 331.9 M tokens against a
true 2.68 B, with 73.7 % of spend in workers a root-only sum could not see, which is
what "included in the aggregate" is worth measuring.

Two facts about the machinery, both load-bearing:

* **A worker thread must attach the root explicitly.** ``LineageRegistry`` keeps the
  active root in a ``contextvars.ContextVar``, and a bare thread starts with an empty
  context -- so the parent's root is *not* visible in a worker. The documented path is
  :meth:`attach_root`, and an unattached worker raises a typed refusal rather than
  silently minting a sibling root. The suite asserts both halves.
* **The transport is now safe to share.** It holds configuration and no per-call
  state, which is exactly what the concurrency fault forced when it found an
  instance-level cancellation flag.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from temper_harness.ledger import LineageRegistry, aggregate
from temper_harness.ledger.aggregate import Aggregate
from temper_harness.ledger.store import LedgerStore
from temper_harness.pricing import PriceTable, window_for
from temper_harness.provider.errors import IncompleteStream, TransportError
from temper_harness.provider.interface import BufferedTransport, Request, Terminal, Transport

#: The identity a row carries when it was not priced. A row is never silently priced at
#: zero: zero is a claim that the call was free, and `unpriced` is the honest state of a
#: call nobody could cost.
UNPRICED = "unpriced"


@dataclass(frozen=True, slots=True)
class CallOutcome:
    """One concurrent call, as it was attributed."""

    session_id: str
    call_id: str
    status: str
    usage: dict[str, int | None]
    usage_source: str = "unknown"
    error_category: str | None = None
    price_table_id: str = UNPRICED
    #: Which of the table's two windows priced this call, or ``None`` when it was unpriced.
    #: Off-peak is exactly half of peak, so the figure is not auditable without it.
    price_window: str | None = None
    #: Computed from the committed table, or ``None`` when the call could not be priced.
    #: A float because the ledger schema says `number`; the arithmetic itself is Decimal.
    estimated_usd: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def tokens(self) -> int:
        return sum(
            value
            for name in ("prompt_tokens", "completion_tokens")
            if isinstance(value := self.usage.get(name), int)
        )


@dataclass(frozen=True, slots=True)
class FanoutResult:
    """Every call's attribution, and the root total they add up to."""

    root_id: str
    root_session: str
    outcomes: tuple[CallOutcome, ...]
    aggregate: Aggregate

    @property
    def sessions(self) -> tuple[str, ...]:
        return tuple(outcome.session_id for outcome in self.outcomes)

    @property
    def descendant_tokens(self) -> int:
        """Worker spend, which is the figure a root-only sum cannot see.

        The prior attempt reported 6 root sessions at 331.9 M tokens against a true
        2.68 B, with 73.7 % of it in workers. This is that 73.7 %, named.
        """
        return self.aggregate.descendant_tokens

    def summary(self) -> str:
        failures = [
            f"{outcome.session_id}({outcome.error_category or outcome.status})"
            for outcome in self.outcomes
            if not outcome.ok
        ]
        return (
            f"{len(self.outcomes)} concurrent call(s) over {len(set(self.sessions))} session(s); "
            f"descendant {self.descendant_tokens} of {self.aggregate.inclusive_tokens} tokens "
            f"({'reconciled' if self.aggregate.reconciles else 'not reconciled'})"
            + (f"; failures: {failures}" if failures else "")
        )


def _usage_source(usage: dict[str, int | None] | None) -> tuple[dict[str, int | None], str]:
    if usage is None or all(value is None for value in usage.values()):
        return (
            {
                "prompt_tokens": None,
                "completion_tokens": None,
                "reasoning_tokens": None,
                "cached_input_tokens": None,
                "total_tokens": None,
            },
            "unknown",
        )
    return usage, "provider"


def probe_fanout(
    *,
    store: LedgerStore,
    transport: Transport,
    request: Request,
    sessions: Sequence[str],
    root_session: str = "fanout-root",
    max_workers: int | None = None,
    served_from: str = "live",
    priced_by: PriceTable | None = None,
    at: dt.datetime | None = None,
) -> FanoutResult:
    """Issue one call per session, simultaneously, and aggregate the root.

    The probe sessions are registered as **children of a root session**, not as
    root-level sessions, and that is not cosmetic. The aggregate decides "root
    exclusive" from whether a row's session has a parent, so registering six workers
    with no parent puts all of their spend in the root-exclusive bucket -- which is
    the incident shape this whole package exists to prevent, reproduced inside the
    instrument meant to detect it. It was reproduced here in fact, and a test caught
    it: six workers, 231 tokens, all filed as root-exclusive.

    Fails rather than degrades: the aggregate is the strict one, so a call that
    terminated ``cancelled`` or ``incomplete`` makes this raise instead of returning a
    total that quietly excludes it. A probe whose whole purpose is to prove nothing
    went missing is the last place to accept a lower bound.
    """
    if not sessions:
        raise ValueError("the concurrency probe needs at least one session")
    if len(set(sessions)) != len(sessions):
        raise ValueError("each concurrent call needs its own session; got a duplicate")
    if root_session in sessions:
        raise ValueError("the root session cannot also be a worker session")
    if (priced_by is None) != (at is None):
        # A cost is a function of the peak window, so a table without a moment cannot price
        # anything, and a moment without a table has nothing to price against.
        raise ValueError(
            "pricing needs both a table and the timestamp the calls happened at; the "
            "window is half the rate"
        )

    registry = LineageRegistry(store)
    root_id = registry.open_root()
    registry.register_session(root_session)
    for session_id in sessions:
        registry.register_session(session_id, parent_session_id=root_session)

    def run_one(session_id: str) -> CallOutcome:
        return _run_one(
            store=store,
            root_id=root_id,
            transport=transport,
            request=request,
            session_id=session_id,
            served_from=served_from,
            priced_by=priced_by,
            at=at,
        )

    with ThreadPoolExecutor(max_workers=max_workers or len(sessions)) as pool:
        outcomes = list(pool.map(run_one, sessions))

    registry.detach_root()
    return FanoutResult(
        root_id=root_id,
        root_session=root_session,
        outcomes=tuple(outcomes),
        aggregate=aggregate(store, root_id),
    )


def _run_one(
    *,
    store: LedgerStore,
    root_id: str,
    transport: Transport,
    request: Request,
    session_id: str,
    served_from: str,
    priced_by: PriceTable | None = None,
    at: dt.datetime | None = None,
) -> CallOutcome:
    registry = LineageRegistry(store)
    # contextvars do not cross a thread boundary, so the root the parent opened is
    # invisible here until it is attached. Without this the call raises rather than
    # being attributed to the wrong place, which is the behaviour the suite pins.
    registry.attach_root(root_id)
    handle = registry.open_call(session_id)

    status, usage, category = "ok", None, None
    try:
        # A buffered transport yields exactly one terminal event; asserting that
        # rather than taking the first item keeps this honest if the contract ever
        # changes, and gives mypy the narrowing it needs.
        terminals = [
            event
            for event in BufferedTransport(transport).stream(request)
            if isinstance(event, Terminal)
        ]
        if len(terminals) != 1:
            raise AssertionError(
                f"a buffered transport must yield exactly one terminal event, got {len(terminals)}"
            )
        terminal = terminals[0]
        if terminal.finish_reason is None:
            # A turn with no finish reason is never a success, on any path.
            status = "incomplete"
        usage = terminal.envelope.get("usage")
    except IncompleteStream as err:
        status, usage = "incomplete", err.partial_usage
    except TransportError as err:
        status, usage, category = "failed", err.partial_usage, err.category

    block, source = _usage_source(usage)
    cost = (
        priced_by.estimate_usd(block, model=request.model, at=at)
        if priced_by is not None and at is not None
        else None
    )
    # The window is recorded beside the figure. Without it a stored cost carries a
    # factor-of-two ambiguity -- off-peak is exactly half of peak -- that nothing on the row
    # could resolve later, and a reader could not tell a cheap call from a mispriced one.
    window = window_for(priced_by.raw, at) if priced_by is not None and at is not None else None
    registry.close_call(
        handle,
        status=status,
        served_from=served_from,
        usage=block,
        usage_source=source,
        price_table_id=priced_by.table_id if priced_by is not None else UNPRICED,
        price_window=window,
        estimated_usd=float(cost) if cost is not None else None,
    )
    registry.detach_root()
    return CallOutcome(
        session_id=session_id,
        call_id=handle.call_id,
        status=status,
        usage=block,
        usage_source=source,
        error_category=category,
        price_table_id=priced_by.table_id if priced_by is not None else UNPRICED,
        price_window=window,
        estimated_usd=float(cost) if cost is not None else None,
    )
