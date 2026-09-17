"""Shared fixtures for the harness test suite."""

from __future__ import annotations

import pytest

from temper_harness.ledger.lineage import ROOT_ENV_VAR, LineageRegistry
from temper_harness.ledger.store import LedgerStore


@pytest.fixture(autouse=True)
def _clean_lineage_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the active-root contextvar and the ambient root out of every test.

    The active root is process context by design (R1), so a test that leaks it
    would make the next test's ``open_root`` fail for an unrelated reason.
    """
    monkeypatch.delenv(ROOT_ENV_VAR, raising=False)
    from temper_harness.ledger.lineage import _ACTIVE_ROOT

    token = _ACTIVE_ROOT.set(None)
    yield
    _ACTIVE_ROOT.reset(token)


@pytest.fixture
def store(tmp_path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger")


@pytest.fixture
def registry(store: LedgerStore) -> LineageRegistry:
    return LineageRegistry(store)
