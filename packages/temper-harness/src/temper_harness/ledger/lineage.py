"""Session lineage registration.

Root identity is *inherited from process context*, never supplied by the
caller (R1). That is the whole point of this module: an aggregator that takes a
root id only partitions rows by a field, so a child that names its own root
still satisfies the schema and still returns a smaller total with no warning.
Inheritance plus :meth:`LineageRegistry.attach_root` makes the honest path the
only path, and the two refusal errors below are what the tests assert on.

A child process receives ``TEMPER_HARNESS_ROOT`` and must call
:meth:`LineageRegistry.attach_root`; :meth:`open_root` refuses while that
variable is set, so a fan-out cannot silently mint sibling roots.
"""

from __future__ import annotations

import contextvars
import os
import uuid
from dataclasses import dataclass
from typing import Any

from temper_harness.ledger.errors import (
    AmbientRootError,
    NestedRootError,
    UnregisteredRootError,
    UnresolvedLineageError,
)
from temper_harness.ledger.store import LedgerStore

ROOT_ENV_VAR = "TEMPER_HARNESS_ROOT"

_ACTIVE_ROOT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "temper_harness_active_root", default=None
)


def active_root() -> str | None:
    """The root id in scope for this context, or ``None``."""
    return _ACTIVE_ROOT.get()


def ambient_root() -> str | None:
    """The root id this process inherited from its parent, if any."""
    value = os.environ.get(ROOT_ENV_VAR)
    return value or None


@dataclass(frozen=True, slots=True)
class CallHandle:
    """A registered call, opened but not yet closed."""

    call_id: str
    root_id: str
    session_id: str
    parent_session_id: str | None
    attempt: int


class LineageRegistry:
    """Registers roots, sessions, and calls against one ledger store."""

    def __init__(self, store: LedgerStore) -> None:
        self.store = store

    # -- roots -----------------------------------------------------------

    def open_root(self) -> str:
        """Mint and register a new root, and make it active for this context."""
        if active_root() is not None:
            raise NestedRootError(
                "a root is already active in this context; only the outermost "
                "process may open a root"
            )
        inherited = ambient_root()
        if inherited is not None:
            raise AmbientRootError(
                f"{ROOT_ENV_VAR}={inherited!r} is inherited; attach to it with "
                "attach_root() instead of opening a sibling root"
            )
        root_id = f"root-{uuid.uuid4().hex}"
        self.store.append_ledger({"kind": "root_opened", "root_id": root_id})
        _ACTIVE_ROOT.set(root_id)
        return root_id

    def attach_root(self, root_id: str) -> str:
        """Adopt a root this process inherited rather than minting one."""
        if root_id not in self.store.root_ids():
            raise UnregisteredRootError(f"root {root_id!r} is not registered in this ledger")
        _ACTIVE_ROOT.set(root_id)
        return root_id

    def detach_root(self) -> None:
        """Clear the active root. For tests and for process teardown."""
        _ACTIVE_ROOT.set(None)

    # -- sessions --------------------------------------------------------

    def register_session(self, session_id: str, parent_session_id: str | None = None) -> str:
        """Register a session under the active root.

        There is deliberately no ``root_id`` parameter. A child session inherits
        the active root; supplying a parent that resolves to a different root is
        an error rather than a re-parenting.
        """
        root_id = active_root()
        if root_id is None:
            raise NestedRootError("no active root; call open_root() or attach_root() first")
        if parent_session_id is not None:
            if parent_session_id not in self.store.parent_of():
                raise UnresolvedLineageError(
                    f"parent session {parent_session_id!r} is not registered"
                )
            parent_root = self.store.resolve_root(parent_session_id)
            if parent_root != root_id:
                raise UnresolvedLineageError(
                    f"parent session {parent_session_id!r} belongs to root "
                    f"{parent_root!r}, not the active root {root_id!r}"
                )
        self.store.append_ledger(
            {
                "kind": "session_registered",
                "root_id": root_id,
                "session_id": session_id,
                "parent_session_id": parent_session_id,
            }
        )
        return session_id

    # -- calls -----------------------------------------------------------

    def open_call(self, session_id: str, attempt: int = 0) -> CallHandle:
        """Open a call and append its in-flight record before any request."""
        root_id = active_root()
        if root_id is None:
            raise NestedRootError("no active root; call open_root() or attach_root() first")
        resolved = self.store.resolve_root(session_id)
        if resolved != root_id:
            raise UnresolvedLineageError(
                f"session {session_id!r} resolves to root {resolved!r}, not {root_id!r}"
            )
        handle = CallHandle(
            call_id=f"call-{uuid.uuid4().hex}",
            root_id=root_id,
            session_id=session_id,
            parent_session_id=self.store.parent_of().get(session_id),
            attempt=attempt,
        )
        self.store.append_inflight(
            {
                "kind": "call_opened",
                "call_id": handle.call_id,
                "root_id": handle.root_id,
                "session_id": handle.session_id,
                "parent_session_id": handle.parent_session_id,
                "attempt": handle.attempt,
            }
        )
        return handle

    def close_call(
        self,
        handle: CallHandle,
        *,
        status: str,
        served_from: str,
        usage: dict[str, int | None] | None = None,
        usage_source: str = "unknown",
        price_table_id: str = "unpriced",
        provider_reported_usd: float | None = None,
        estimated_usd: float | None = None,
    ) -> dict[str, Any]:
        """Append the single terminal row for ``handle`` (R3)."""
        usage_block: dict[str, int | None] = usage or {
            "prompt_tokens": None,
            "completion_tokens": None,
            "reasoning_tokens": None,
            "cached_input_tokens": None,
        }
        record: dict[str, Any] = {
            "kind": "call_terminal",
            "lineage": {
                "root_id": handle.root_id,
                "session_id": handle.session_id,
                "parent_session_id": handle.parent_session_id,
                "call_id": handle.call_id,
                "attempt": handle.attempt,
            },
            "status": status,
            "served_from": served_from,
            "usage": usage_block,
            "usage_source": usage_source,
            "price_table_id": price_table_id,
            "provider_reported_usd": provider_reported_usd,
            "estimated_usd": estimated_usd,
        }
        return self.store.append_ledger(record)
