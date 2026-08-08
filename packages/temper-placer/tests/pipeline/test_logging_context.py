"""Tests for logging_context module."""

import contextvars

from temper_placer.pipeline import logging_context as lc


def test_set_clear_run_context():
    """set_run_context sets metadata and clear_run_context restores it."""
    metadata = {"board": "test_board", "git_commit": "abc123", "stage": "test_stage", "run_id": "1"}
    token = lc.set_run_context(metadata)
    assert token is not None
    assert isinstance(token, contextvars.Token)

    lc.clear_run_context(token)


def test_set_run_context_overwrites_previous():
    """Setting run context twice and restoring each token works."""
    first = {"board": "first"}
    second = {"board": "second"}

    t1 = lc.set_run_context(first)
    t2 = lc.set_run_context(second)

    lc.clear_run_context(t2)
    lc.clear_run_context(t1)
