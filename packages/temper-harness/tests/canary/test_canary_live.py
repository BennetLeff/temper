"""The live canary against the official API. Opt-in; see the package conftest.

This is the run that turns Tier A from a reproducibility instrument into an anchored
observation (R12). It asserts shapes, not content, and writes hashed evidence that can
be committed without a body or a credential in it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from temper_harness.canary import run_canary, write_evidence
from temper_harness.provider.deepseek import API_KEY_ENV
from tests import corpus

EVIDENCE = Path(__file__).resolve().parent / "evidence" / "canary.json"
WRITE_ENV = "TEMPER_HARNESS_WRITE_CANARY_EVIDENCE"


def _harness_state() -> tuple[str, bool]:
    """HEAD, and whether the tree was clean.

    Both, because a commit alone is not provenance: a run from a dirty tree cannot be
    reproduced from the commit it names, and the first canary run in this branch was
    exactly that -- the canary code was uncommitted at the HEAD it recorded. Recording
    the dirt is what keeps the evidence an observation rather than an anecdote.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - environment
        return "UNKNOWN", True
    return (commit or "UNKNOWN"), bool(status.strip())


@pytest.fixture(scope="module")
def report():
    """One live run, shared by the tests below.

    Module-scoped deliberately: each probe is a real request and a real cost, so a
    second test must not re-issue the set to make its own point.
    """
    return run_canary(
        api_key=os.environ.get(API_KEY_ENV),
        recorded_dir=Path(corpus.CAPTURED),
        harness_state=_harness_state(),
    )


def test_the_live_canary_matches_the_recorded_shapes(report) -> None:
    """The probe set, re-issued live, against the shapes the corpus recorded.

    A shape difference fails this test and the failure names the difference, because
    a canary that only says "something changed" sends the reader back to the corpus to
    find out what.
    """
    if os.environ.get(WRITE_ENV):
        write_evidence(report, EVIDENCE)

    assert report.ok, "\n".join(
        f"{item.name}: {list(item.differences)}" for item in report.comparisons if not item.matched
    )


def test_the_live_run_produced_a_shape_for_every_probe(report) -> None:
    """Coverage, asserted on the live side too: a probe that answered nothing would
    otherwise be counted as matching by omission."""
    assert len(report.comparisons) == len(corpus.ENTRIES)
    assert all(item.live_response_bytes > 0 for item in report.comparisons)
    assert report.account_models, "the account's model list is part of the evidence"
    if report.harness_dirty:  # pragma: no cover - only when run from a dirty tree
        pytest.fail(
            "this run was from a dirty tree, so its evidence cannot be reproduced from "
            "the commit it names; commit first, then re-run the canary"
        )
