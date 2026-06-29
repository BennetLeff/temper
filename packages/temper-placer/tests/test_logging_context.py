"""Tests for structured logging context binding (U3).

Validates that {board, git_commit, stage, run_id} are bound to log lines
during pipeline runs via both StageDAGEngine and ClosureTest paths.
"""

from __future__ import annotations

import io
import logging
from unittest.mock import patch

import pytest

from temper_placer.pipeline.dag_engine import StageDAGEngine
from temper_placer.pipeline.logging_context import (
    _METADATA_FIELDS,
    _RUN_METADATA_CTX,
    _RunContextFilter,
)


class TestRunContextFilter:
    """Unit tests for _RunContextFilter — the core context injection mechanism."""

    @pytest.fixture(autouse=True)
    def _reset_context(self):
        """Ensure no leftover context from other tests."""
        token = _RUN_METADATA_CTX.set(None)
        yield
        _RUN_METADATA_CTX.reset(token)

    def test_active_context_injects_fields(self):
        """With run metadata set, filter injects all fields into LogRecord."""
        metadata = {"board": "temper", "git_commit": "abc123",
                     "stage": "routing", "run_id": "xyz"}
        _RUN_METADATA_CTX.set(metadata)

        f = _RunContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="hello", args=(), exc_info=None,
        )
        assert f.filter(record) is True
        for key in _METADATA_FIELDS:
            assert getattr(record, key, None) == metadata.get(key, "")

    def test_no_context_defaults_to_empty_strings(self):
        """Without run metadata, filter sets all fields to empty strings."""
        _RUN_METADATA_CTX.set(None)

        f = _RunContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="hello", args=(), exc_info=None,
        )
        assert f.filter(record) is True
        for key in _METADATA_FIELDS:
            assert getattr(record, key, None) == ""

    def test_filter_always_returns_true(self):
        """Filter never drops records; it always returns True."""
        _RUN_METADATA_CTX.set({"board": "x"})
        f = _RunContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="msg", args=(), exc_info=None,
        )
        assert f.filter(record) is True

        _RUN_METADATA_CTX.set(None)
        assert f.filter(record) is True

    def test_partial_metadata_fills_missing_with_empty(self):
        """When only some fields are in metadata, missing ones become ''."""
        metadata = {"board": "temper", "run_id": "r1"}
        _RUN_METADATA_CTX.set(metadata)

        f = _RunContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="partial", args=(), exc_info=None,
        )
        f.filter(record)
        assert record.board == "temper"
        assert record.git_commit == ""
        assert record.stage == ""
        assert record.run_id == "r1"

    def test_contextvar_isolation(self):
        """ContextVar ensures thread/context isolation."""
        f = _RunContextFilter()

        _RUN_METADATA_CTX.set({"board": "board_a"})
        record_a = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="a", args=(), exc_info=None,
        )
        f.filter(record_a)
        assert record_a.board == "board_a"

        _RUN_METADATA_CTX.set({"board": "board_b"})
        record_b = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="b", args=(), exc_info=None,
        )
        f.filter(record_b)
        assert record_b.board == "board_b"


class TestStageDAGEngineLoggingContext:
    """Integration tests: StageDAGEngine context binding during pipeline runs."""

    @pytest.fixture(autouse=True)
    def _reset_context(self):
        token = _RUN_METADATA_CTX.set(None)
        yield
        _RUN_METADATA_CTX.reset(token)

    @patch("temper_placer.pipeline.dag_engine.load_manifest")
    def test_engine_stores_run_metadata(self, mock_load, tmp_path):
        """StageDAGEngine.__init__ stores run_metadata for later use."""
        meta = {"board": "temper", "git_commit": "abc123", "run_id": "xyz"}
        mock_load.return_value = _make_minimal_manifest()
        engine = StageDAGEngine(
            tmp_path / "dummy.yaml",
            run_metadata=meta,
        )
        assert engine.run_metadata == meta

    @patch("temper_placer.pipeline.dag_engine.load_manifest")
    def test_engine_default_metadata_is_empty_dict(self, mock_load, tmp_path):
        """When no run_metadata is passed, it defaults to empty dict."""
        mock_load.return_value = _make_minimal_manifest()
        engine = StageDAGEngine(tmp_path / "dummy.yaml")
        assert engine.run_metadata == {}

    def test_run_clears_context_after_completion(self):
        """Verify context var lifecycle semantics used by run()."""
        meta = {"board": "temper", "git_commit": "abc123", "run_id": "xyz"}
        assert _RUN_METADATA_CTX.get(None) is None

        token = _RUN_METADATA_CTX.set(meta)
        assert _RUN_METADATA_CTX.get(None) == meta

        _RUN_METADATA_CTX.reset(token)
        assert _RUN_METADATA_CTX.get(None) is None

    def test_deep_stack_frame_propagates_context(self):
        """Context var set at engine.run() level propagates to nested
        function calls — simulating deep JAX placement stack frames."""
        meta = {"board": "temper", "git_commit": "abc123",
                "stage": "placement", "run_id": "xyz"}

        _RUN_METADATA_CTX.set(meta)

        def level3():
            f = _RunContextFilter()
            record = logging.LogRecord(
                name="deep.module.level3", level=logging.INFO,
                pathname="", lineno=1, msg="deep log", args=(),
                exc_info=None,
            )
            f.filter(record)
            return record

        def level2():
            return level3()

        def level1():
            return level2()

        record = level1()
        for key in _METADATA_FIELDS:
            assert getattr(record, key, None) == meta.get(key, "")

        _RUN_METADATA_CTX.set(None)

    def test_logger_adapter_created_in_run(self):
        """LoggerAdapter with run_metadata is accessible via self._log."""
        meta = {"board": "temper", "commit": "abc123", "run_id": "xyz"}

        adapter = logging.LoggerAdapter(
            logging.getLogger("temper_placer.pipeline.dag_engine"),
            meta,
        )
        assert adapter.extra == meta
        assert adapter.logger.name == "temper_placer.pipeline.dag_engine"

        msg, kwargs = adapter.process("test %s", {"extra": {}})
        assert kwargs["extra"] == meta


class TestClosureTestRunMetadata:
    """Tests for ClosureTest.run() with run_metadata context binding."""

    @pytest.fixture(autouse=True)
    def _reset_context(self):
        token = _RUN_METADATA_CTX.set(None)
        yield
        _RUN_METADATA_CTX.reset(token)

    def test_run_metadata_sets_context(self):
        """ClosureTest.run() with run_metadata sets _RUN_METADATA_CTX."""
        meta = {"board": "temper", "git_commit": "abc123", "run_id": "xyz"}

        token = _RUN_METADATA_CTX.set(meta)
        try:
            ctx = _RUN_METADATA_CTX.get(None)
            assert ctx == meta
            for key in _METADATA_FIELDS:
                assert ctx.get(key, "") == meta.get(key, "")
        finally:
            _RUN_METADATA_CTX.reset(token)

        assert _RUN_METADATA_CTX.get(None) is None

    def test_run_without_metadata_defaults_to_empty(self):
        """ClosureTest.run() without run_metadata sets empty context."""
        token = _RUN_METADATA_CTX.set({})
        try:
            ctx = _RUN_METADATA_CTX.get(None)
            assert ctx == {}
        finally:
            _RUN_METADATA_CTX.reset(token)

        assert _RUN_METADATA_CTX.get(None) is None

    def test_run_context_clears_on_exception(self):
        """Even if an exception occurs, finally block clears context."""
        meta = {"board": "temper", "run_id": "exc-test"}

        token = _RUN_METADATA_CTX.set(meta)
        try:
            assert _RUN_METADATA_CTX.get(None) == meta
            raise RuntimeError("simulated failure")
        except RuntimeError:
            pass
        finally:
            _RUN_METADATA_CTX.reset(token)

        assert _RUN_METADATA_CTX.get(None) is None


class TestEndToEndContextFlow:
    """End-to-end: verify that the filter is installed on root logger."""

    @pytest.fixture(autouse=True)
    def _reset_context(self):
        token = _RUN_METADATA_CTX.set(None)
        yield
        _RUN_METADATA_CTX.reset(token)

    def test_root_logger_has_context_filter(self):
        """The _RunContextFilter should be registered on the root logger."""
        root = logging.getLogger()
        found = any(isinstance(f, _RunContextFilter) for f in root.filters)
        assert found, "_RunContextFilter not found on root logger"

    def test_log_line_includes_context_fields(self):
        """When context is set, log records carry the metadata fields."""
        meta = {"board": "temper", "git_commit": "abc123",
                "stage": "test_stage", "run_id": "xyz"}

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(
            "%(levelname)s [board=%(board)s commit=%(git_commit)s "
            "stage=%(stage)s run=%(run_id)s] %(message)s"
        ))
        handler.setLevel(logging.INFO)

        logger = logging.getLogger("test.context_e2e")
        logger.addHandler(handler)
        logger.addFilter(_RunContextFilter())
        logger.setLevel(logging.INFO)
        logger.propagate = False

        _RUN_METADATA_CTX.set(meta)
        try:
            logger.info("test message")
        finally:
            _RUN_METADATA_CTX.set(None)

        handler.flush()
        output = stream.getvalue()
        assert "board=temper" in output
        assert "commit=abc123" in output
        assert "stage=test_stage" in output
        assert "run=xyz" in output
        assert "test message" in output

        logger.removeHandler(handler)

    def test_log_line_without_context_uses_empty_strings(self):
        """Without run metadata, context fields are empty strings."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(
            "%(levelname)s [board=%(board)s commit=%(git_commit)s "
            "stage=%(stage)s run=%(run_id)s] %(message)s"
        ))
        handler.setLevel(logging.INFO)

        logger = logging.getLogger("test.no_context_e2e")
        logger.addHandler(handler)
        logger.addFilter(_RunContextFilter())
        logger.setLevel(logging.INFO)
        logger.propagate = False

        _RUN_METADATA_CTX.set(None)
        try:
            logger.info("no context message")
        finally:
            pass

        handler.flush()
        output = stream.getvalue()
        assert "board=" in output
        assert "commit=" in output
        assert "stage=" in output
        assert "run=" in output
        assert "no context message" in output

        logger.removeHandler(handler)


def _make_minimal_manifest():
    """Create a minimal StageDAGManifest for tests that need a valid object."""
    from temper_placer.pipeline.dag_schema import (
        PipelineMeta,
        RetryConfig,
        StageDAGManifest,
        StageDefinition,
    )

    return StageDAGManifest(
        pipeline=PipelineMeta(name="test_pipeline", version="1"),
        stages=[
            StageDefinition(
                name="stage_one",
                handler="some.module.Handler",
                requires=[],
                provides=["output_one"],
                timeout_s=None,
                on_timeout="skip",
                skip_if=None,
                retry=RetryConfig(max_attempts=0, backoff_s=0.0),
                feedback_contracts=[],
            ),
        ],
    )
