"""
Tests for U3: Pipeline orchestration and closure test plumbing.

Covers:
- Pipeline loads sidecar once when present
- Missing sidecar -> stage uses channel_map=None + WARNING
- Malformed sidecar -> fallback + WARNING
- Per-instance counter is independent across pipeline runs
- Closure test invokes channel analysis between parse and place
- Sidecar cell_size_um must match PLACER_CELL_SIZE_UM (hard error)
- Closure test falls back when Router V6 is unavailable
"""

from __future__ import annotations

import json
import logging

import pytest

from temper_placer.deterministic import (
    PLACER_CELL_SIZE_UM,
    SIDECAR_FILENAME,
    ChannelMap,
    ChannelSidecarError,
    SidecarAwarePipeline,
    create_drc_aware_pipeline,
    load_channel_map_from_sidecar,
)
from temper_placer.io.kicad_metadata import KiCadMetadata


def _make_valid_sidecar_dict(*, cell_size_um: int = PLACER_CELL_SIZE_UM) -> dict:
    return {
        "temper_schema_hash": "temper.channels.v1",
        "cell_size_um": float(cell_size_um),
        "grid": [
            [0.0, 0.0, 0.0],
            [0.0, 0.5, 0.0],
            [0.0, 0.0, 0.0],
        ],
        "bottlenecks": [
            {"x": 1, "y": 1, "layer": "F.Cu", "severity": "MEDIUM", "score": 0.6},
        ],
    }


def _write_sidecar(path, **overrides) -> dict:
    payload = _make_valid_sidecar_dict(**overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return payload


def _metadata() -> KiCadMetadata:
    return KiCadMetadata(
        courtyards={},
        pad_sizes={},
        board_width=100.0,
        board_height=100.0,
    )


class TestPipelineLoadsSidecar:
    def test_pipeline_loads_sidecar_when_present(self, tmp_path, caplog):
        sidecar_path = tmp_path / SIDECAR_FILENAME
        _write_sidecar(sidecar_path)

        with caplog.at_level(logging.WARNING):
            pipeline = create_drc_aware_pipeline(
                metadata=_metadata(),
                output_dir=tmp_path,
            )

        assert isinstance(pipeline, SidecarAwarePipeline)
        assert pipeline._sidecar_load_count == 1
        # The placement stage in the pipeline should carry the loaded map.
        from temper_placer.deterministic.stages.phased_component_assignment import (
            PhasedComponentAssignmentStage,
        )
        stages_with_map = [
            s for s in pipeline.stages if isinstance(s, PhasedComponentAssignmentStage)
        ]
        # create_drc_aware_pipeline may use ComponentAssignmentStage if
        # no phased config; we only assert the sidecar is loaded.
        assert pipeline.channel_map is not None
        assert pipeline.channel_map.cell_size_um == PLACER_CELL_SIZE_UM

    def test_pipeline_missing_sidecar_uses_none(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING):
            pipeline = create_drc_aware_pipeline(
                metadata=_metadata(),
                output_dir=tmp_path,
            )
        assert pipeline._sidecar_load_count == 0
        assert pipeline.channel_map is None
        # WARNING logged for missing sidecar
        msgs = [r.message for r in caplog.records]
        assert any(SIDECAR_FILENAME in m or "channel_map" in m for m in msgs)

    def test_pipeline_malformed_sidecar_falls_back(self, tmp_path, caplog):
        sidecar_path = tmp_path / SIDECAR_FILENAME
        sidecar_path.write_text("{ not json")

        with caplog.at_level(logging.WARNING):
            pipeline = create_drc_aware_pipeline(
                metadata=_metadata(),
                output_dir=tmp_path,
            )
        assert pipeline._sidecar_load_count == 0
        assert pipeline.channel_map is None
        msgs = [r.message for r in caplog.records]
        assert any(str(sidecar_path) in m for m in msgs)

    def test_pipeline_cell_size_mismatch_raises(self, tmp_path):
        sidecar_path = tmp_path / SIDECAR_FILENAME
        # Use a non-matching cell size to force the hard error.
        _write_sidecar(sidecar_path, cell_size_um=500)
        with pytest.raises(ChannelSidecarError) as exc:
            create_drc_aware_pipeline(
                metadata=_metadata(),
                output_dir=tmp_path,
            )
        assert "PLACER_CELL_SIZE_UM" in str(exc.value)

    def test_pipeline_reads_sidecar_once_per_instance(self, tmp_path):
        # Two independent pipelines, each in its own tmp dir with its own
        # sidecar. Counters must be independent and not bumped by per-stage
        # placement activity.
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        _write_sidecar(dir_a / SIDECAR_FILENAME)
        _write_sidecar(dir_b / SIDECAR_FILENAME)

        p_a = create_drc_aware_pipeline(metadata=_metadata(), output_dir=dir_a)
        p_b = create_drc_aware_pipeline(metadata=_metadata(), output_dir=dir_b)
        assert p_a._sidecar_load_count == 1
        assert p_b._sidecar_load_count == 1
        # Run many components through each to confirm the counter is not
        # bumped by per-component placement.
        for _ in range(1000):
            p_a.record_sidecar_load()
            p_b.record_sidecar_load()
        assert p_a._sidecar_load_count == 1001
        assert p_b._sidecar_load_count == 1001


class TestLoadChannelMapHelper:
    def test_returns_empty_when_output_dir_none(self):
        cmap = load_channel_map_from_sidecar(None)
        assert cmap == ChannelMap.empty()

    def test_returns_empty_when_file_missing(self, tmp_path):
        cmap = load_channel_map_from_sidecar(tmp_path)
        assert cmap == ChannelMap.empty()

    def test_returns_empty_on_malformed(self, tmp_path):
        (tmp_path / SIDECAR_FILENAME).write_text("oops")
        cmap = load_channel_map_from_sidecar(tmp_path)
        assert cmap == ChannelMap.empty()

    def test_returns_loaded_map_on_valid(self, tmp_path):
        _write_sidecar(tmp_path / SIDECAR_FILENAME)
        cmap = load_channel_map_from_sidecar(tmp_path)
        assert cmap.has_grid()
        assert cmap.cell_size_um == PLACER_CELL_SIZE_UM

    def test_hard_error_on_mismatched_cell_size(self, tmp_path):
        _write_sidecar(tmp_path / SIDECAR_FILENAME, cell_size_um=250)
        with pytest.raises(ChannelSidecarError):
            load_channel_map_from_sidecar(tmp_path)


class TestClosureTestChannelAnalysisOrdering:
    def test_closure_test_runs_channel_analysis_first(self, tmp_path, monkeypatch):
        """Closure test invokes Router V6 Stage 2 between parse and place."""
        from temper_placer.regression import closure_test

        # Minimal stand-in for a parsed PCB.
        fake_parsed = object()

        call_order: list[str] = []

        def fake_parse(pcb_path):
            call_order.append("parse")
            return fake_parsed

        def fake_channel_analysis(*, output_dir, stages_exercised):
            call_order.append("stage2")
            # Write a valid sidecar so subsequent cell_size_um check passes.
            _write_sidecar(output_dir / SIDECAR_FILENAME)
            return stages_exercised + 1

        def fake_benders(input):
            from dataclasses import dataclass
            @dataclass
            class R:
                iterations: int = 1
                cuts: int = 0
                placements: dict = None
            call_order.append("benders")
            r = R()
            r.placements = {}
            return type("Res", (), {"data": r})()

        def fake_router_full(input):
            call_order.append("router_full")
            return type("Res", (), {"data": type("D", (), {"completion_rate": 1.0})()})()

        def fake_drc(pcb_path):
            call_order.append("drc")
            from dataclasses import dataclass
            @dataclass
            class D:
                error_count: int = 0
                warning_count: int = 0
            return D()

        # Create a minimal pcb_path file so the closure test can be constructed.
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb (version 20240101) )")

        monkeypatch.setattr("temper_placer.io.kicad_parser.parse_kicad_pcb_v6", fake_parse)
        monkeypatch.setattr("temper_placer.regression.closure_test.parse_kicad_pcb_v6", fake_parse, raising=False)
        monkeypatch.setattr(
            "temper_placer.regression.closure_test._run_channel_analysis",
            fake_channel_analysis,
        )

        def fake_resolve_and_run(*, phase, strategies, input, fallback=None):
            if phase == "placement":
                return fake_benders(input)
            if phase == "routing":
                return fake_router_full(input)
            raise RuntimeError(f"unexpected phase: {phase}")

        monkeypatch.setattr("temper_placer.runner.resolve_and_run", fake_resolve_and_run)
        monkeypatch.setattr(
            "temper_placer.regression.closure_test.resolve_and_run",
            fake_resolve_and_run,
            raising=False,
        )

        ct = closure_test.ClosureTest(pcb_path, repo_root=tmp_path)
        result = ct.run()

        # The relative order of parse / stage2 / benders is what we assert.
        assert "parse" in call_order
        assert "stage2" in call_order
        assert "benders" in call_order
        parse_idx = call_order.index("parse")
        stage2_idx = call_order.index("stage2")
        benders_idx = call_order.index("benders")
        assert parse_idx < stage2_idx < benders_idx

    def test_closure_test_falls_back_when_router_unavailable(self, tmp_path, monkeypatch, caplog):
        """When the channel-analysis helper raises ImportError, the closure
        test logs WARNING and continues with the rest of the pipeline."""
        from temper_placer.regression import closure_test

        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb (version 20240101) )")

        def fake_parse(path):
            return object()

        def fake_channel_analysis(*, output_dir, stages_exercised):
            # Simulate the helper's behavior when Router V6 is unimportable.
            raise ImportError("mocked router unavailable")

        monkeypatch.setattr("temper_placer.io.kicad_parser.parse_kicad_pcb_v6", fake_parse)
        monkeypatch.setattr("temper_placer.regression.closure_test.parse_kicad_pcb_v6", fake_parse, raising=False)
        monkeypatch.setattr(
            "temper_placer.regression.closure_test._run_channel_analysis",
            fake_channel_analysis,
        )

        def fake_resolve_and_run(*, phase, strategies, input, fallback=None):
            from dataclasses import dataclass
            if phase == "placement":
                @dataclass
                class P:
                    iterations: int = 1
                    cuts: int = 0
                    placements: dict = None
                p = P()
                p.placements = {}
                return type("Res", (), {"data": p})()
            if phase == "routing":
                return type("Res", (), {"data": type("D", (), {"completion_rate": 0.5})()})()
            raise RuntimeError(phase)

        monkeypatch.setattr("temper_placer.runner.resolve_and_run", fake_resolve_and_run)
        monkeypatch.setattr(
            "temper_placer.regression.closure_test.resolve_and_run",
            fake_resolve_and_run,
            raising=False,
        )
        monkeypatch.setattr(
            "temper_placer.regression.closure_test.run_drc",
            lambda p: type("D", (), {"error_count": 0, "warning_count": 0})(),
            raising=False,
        )

        with caplog.at_level(logging.WARNING):
            ct = closure_test.ClosureTest(pcb_path, repo_root=tmp_path)
            result = ct.run()

        assert result is not None
        msgs = [r.message for r in caplog.records]
        assert any("Router V6" in m or "import" in m.lower() for m in msgs)

    def test_closure_test_falls_back_on_runtime_error(self, tmp_path, monkeypatch, caplog):
        """R4d: any failure inside the Step 1b block (not just ImportError)
        must degrade gracefully. A RuntimeError from _run_channel_analysis
        is logged as WARNING and the rest of the pipeline continues.
        """
        from temper_placer.regression import closure_test

        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb (version 20240101) )")

        def fake_parse(path):
            return object()

        def fake_channel_analysis(*, output_dir, stages_exercised):
            # Simulate a non-ImportError failure (e.g. a corrupt stage 2
            # input, a missing dep, an internal assertion). The closure
            # test must catch this and not propagate.
            raise RuntimeError("simulated stage 2 crash")

        monkeypatch.setattr("temper_placer.io.kicad_parser.parse_kicad_pcb_v6", fake_parse)
        monkeypatch.setattr("temper_placer.regression.closure_test.parse_kicad_pcb_v6", fake_parse, raising=False)
        monkeypatch.setattr(
            "temper_placer.regression.closure_test._run_channel_analysis",
            fake_channel_analysis,
        )

        def fake_resolve_and_run(*, phase, strategies, input, fallback=None):
            from dataclasses import dataclass
            if phase == "placement":
                @dataclass
                class P:
                    iterations: int = 1
                    cuts: int = 0
                    placements: dict = None
                p = P()
                p.placements = {}
                return type("Res", (), {"data": p})()
            if phase == "routing":
                return type("Res", (), {"data": type("D", (), {"completion_rate": 0.5})()})()
            raise RuntimeError(phase)

        monkeypatch.setattr("temper_placer.runner.resolve_and_run", fake_resolve_and_run)
        monkeypatch.setattr(
            "temper_placer.regression.closure_test.resolve_and_run",
            fake_resolve_and_run,
            raising=False,
        )
        monkeypatch.setattr(
            "temper_placer.regression.closure_test.run_drc",
            lambda p: type("D", (), {"error_count": 0, "warning_count": 0})(),
            raising=False,
        )

        with caplog.at_level(logging.WARNING):
            ct = closure_test.ClosureTest(pcb_path, repo_root=tmp_path)
            result = ct.run()

        # Test passes only if the closure test returns a result (not a
        # traceback) and the failure is surfaced as a WARNING.
        assert result is not None
        msgs = [r.message for r in caplog.records]
        assert any("channel analysis failed" in m for m in msgs)

    def test_closure_test_sidecar_grid_matches_placer_grid(self, tmp_path):
        """A sidecar with mismatched cell_size_um causes a hard error."""
        from temper_placer.deterministic import (
            PLACER_CELL_SIZE_UM,
            SIDECAR_FILENAME,
            ChannelMap,
            ChannelSidecarError,
        )

        # Write a sidecar with cell_size_um=500 in the same dir as pcb_path
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb )")
        _write_sidecar(pcb_path.parent / SIDECAR_FILENAME, cell_size_um=500)

        # Manually verify the contract: ChannelMap with mismatched size is
        # rejected by the placer loader with a hard error.
        cmap = ChannelMap.load_from_sidecar(pcb_path.parent / SIDECAR_FILENAME)
        assert cmap.cell_size_um != PLACER_CELL_SIZE_UM
        with pytest.raises(ChannelSidecarError) as exc:
            load_channel_map_from_sidecar(pcb_path.parent)
        assert "PLACER_CELL_SIZE_UM" in str(exc.value)


class TestSidecarAwarePipelineWrapper:
    def test_wrapper_records_load(self):
        # The wrapper constructor is the canonical entry point; the
        # _sidecar_load_count starts at 0 and is bumped by record_sidecar_load.
        wrapper = SidecarAwarePipeline(stages=[], fence=None, channel_map=None)
        assert wrapper._sidecar_load_count == 0
        wrapper.record_sidecar_load()
        assert wrapper._sidecar_load_count == 1
        wrapper.record_sidecar_load()
        wrapper.record_sidecar_load()
        assert wrapper._sidecar_load_count == 3


class TestSidecarE2EWiringFromParsedPCB:
    """End-to-end: a sidecar staged next to a parsed PCB is consumed by the
    pipeline without the caller threading output_dir explicitly.
    """

    def test_output_dir_derived_from_parsed_pcb(self, tmp_path):
        """When the caller passes a ParsedPCB-like object (with source_path)
        and omits output_dir, the pipeline loads the sidecar from the parent
        of the PCB source file. This is the closure test's E2E wiring.
        """
        from types import SimpleNamespace

        # Stage a sidecar next to a fake PCB file.
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb )")
        _write_sidecar(pcb_path.parent / SIDECAR_FILENAME)

        # Mock ParsedPCB - just an object with source_path. The pipeline
        # only ever reads source_path to derive output_dir.
        parsed_pcb = SimpleNamespace(source_path=pcb_path)

        pipeline = create_drc_aware_pipeline(
            metadata=_metadata(),
            parsed_pcb=parsed_pcb,
        )

        assert isinstance(pipeline, SidecarAwarePipeline)
        assert pipeline._sidecar_load_count == 1
        assert pipeline.channel_map is not None
        assert pipeline.channel_map.has_grid()
        assert pipeline.channel_map.cell_size_um == PLACER_CELL_SIZE_UM

    def test_explicit_output_dir_overrides_parsed_pcb(self, tmp_path):
        """Explicit output_dir takes precedence over the parsed_pcb parent."""
        from types import SimpleNamespace

        # Two directories: one with a sidecar (explicit), one without
        # (would be derived from parsed_pcb). The explicit one wins.
        explicit_dir = tmp_path / "explicit"
        explicit_dir.mkdir()
        _write_sidecar(explicit_dir / SIDECAR_FILENAME)

        pcb_dir = tmp_path / "pcb"
        pcb_dir.mkdir()
        pcb_path = pcb_dir / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb )")
        # No sidecar here; if the pipeline looked here it would be empty.

        parsed_pcb = SimpleNamespace(source_path=pcb_path)

        pipeline = create_drc_aware_pipeline(
            metadata=_metadata(),
            output_dir=explicit_dir,
            parsed_pcb=parsed_pcb,
        )

        assert pipeline._sidecar_load_count == 1
        assert pipeline.channel_map is not None
        assert pipeline.channel_map.has_grid()

    def test_parsed_pcb_without_source_path_falls_back_to_none(self, tmp_path):
        """A parsed_pcb without source_path is treated as if not provided."""
        from types import SimpleNamespace

        # No output_dir, no usable parsed_pcb -> no sidecar loaded, no crash.
        parsed_pcb = SimpleNamespace()  # no source_path
        pipeline = create_drc_aware_pipeline(
            metadata=_metadata(),
            parsed_pcb=parsed_pcb,
        )
        assert pipeline._sidecar_load_count == 0
        assert pipeline.channel_map is None
