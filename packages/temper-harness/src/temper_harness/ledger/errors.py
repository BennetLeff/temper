"""Typed failures for the ledger and its lineage registry."""

from __future__ import annotations


class LineageError(Exception):
    """Base class for lineage registration failures."""


class NestedRootError(LineageError):
    """A new root was requested while a root was already in scope.

    Opening a second root inside an existing one is how spend escapes a
    root-scoped aggregate: the child's rows stay well-formed and its own root
    resolves, so nothing downstream can tell the total is short. R1 makes root
    identity inherited for exactly this reason, so a nested root is refused
    rather than recorded.
    """


class AmbientRootError(LineageError):
    """A new root was requested in a context that already inherits one.

    A child process inherits ``TEMPER_HARNESS_ROOT``. It must attach to that
    root rather than mint a sibling, otherwise a fan-out silently fragments
    accounting across roots that each look legitimate in isolation.
    """


class UnregisteredRootError(LineageError):
    """A root id was referenced that the ledger never recorded being opened."""


class UnresolvedLineageError(LineageError):
    """A session's parent chain does not reach a registered root.

    Raised rather than treated as an orphan the aggregate could quietly skip:
    an unattributable row is evidence the accounting is incomplete, not a row
    without a home.
    """
