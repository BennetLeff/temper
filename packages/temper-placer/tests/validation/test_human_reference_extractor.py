"""Tests for the canonical human_reference_extractor.

Validates every link in the extraction chain: parse, PlacementState
construction, HPWL, overlap loss, boundary loss, and the YAML I/O round-trip.
"""

from pathlib import Path

import pytest
import yaml

from temper_placer.validation.human_reference_extractor import (
    HumanReference,
    MetricValue,
    extract_human_reference,
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _corpus_board_path(board_id: str, filename: str | None = None) -> Path:
    """Return a path inside ``power_pcb_dataset/corpus/{board_id}/``."""
    repo = Path(__file__).resolve().parents[4]  # repo root
    board_dir = repo / "power_pcb_dataset" / "corpus" / board_id
    if filename is None:
        return board_dir
    return board_dir / filename


# ---------------------------------------------------------------------------
# Real-board tests (piantor_right)
# ---------------------------------------------------------------------------

@pytest.mark.l4_regression
class TestExtractPiantorRight:
    """End-to-end extraction from a real, placed-and-routed board."""

    @pytest.fixture(scope="class")
    def pcb_path(self) -> Path:
        path = _corpus_board_path("piantor_right", "keyboard_pcb.kicad_pcb")
        if not path.exists():
            pytest.skip("piantor_right PCB not available")
        return path

    def test_extract_returns_valid_reference(self, pcb_path: Path):
        ref = extract_human_reference(pcb_path, validate=True)
        assert isinstance(ref, HumanReference)
        assert ref.board_id == "piantor_right"
        assert "hpwl" in ref.metrics
        assert "overlap_loss" in ref.metrics
        assert "boundary_loss" in ref.metrics

        hpwl = ref.metrics["hpwl"].value
        assert hpwl > 0.0, f"HPWL is {hpwl}, expected > 0"
        assert ref.metrics["overlap_loss"].value >= 0
        assert ref.metrics["boundary_loss"].value >= 0

    def test_save_round_trips(self, pcb_path: Path, tmp_path: Path):
        ref = extract_human_reference(pcb_path, validate=True)
        yml = tmp_path / "human_reference.yaml"
        ref.save(yml)

        with open(yml) as f:
            data = yaml.safe_load(f)

        assert data["board_id"] == ref.board_id
        assert data["extraction_source"] == ref.extraction_source
        for key in ("hpwl", "overlap_loss", "boundary_loss"):
            assert key in data["metrics"]
            assert "value" in data["metrics"][key]
            assert "extracted_at" in data["metrics"][key]
            assert "pcb_git_hash" in data["metrics"][key]

    def test_traces_resolve_to_named_nets(self, pcb_path: Path):
        """Every extracted trace has a net that matches a parsed net name."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        result = parse_kicad_pcb(pcb_path)
        net_names = {n.name for n in result.netlist.nets}

        assert len(result.traces) > 0, "Expected traces on a routed board"
        for t in result.traces:
            assert t.net is not None, "Trace has no net assigned"
            assert t.net in net_names, (
                f"Trace net '{t.net}' not found in parsed netlist"
            )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            extract_human_reference("/nonexistent/pcb.kicad_pcb")

    def test_validate_false_skips_assertions(self):
        """validate=False should still produce output (debugging flow)."""
        pcb_path = _corpus_board_path("piantor_right", "keyboard_pcb.kicad_pcb")
        if not pcb_path.exists():
            pytest.skip("piantor_right PCB not available")
        ref = extract_human_reference(pcb_path, validate=False)
        assert isinstance(ref, HumanReference)
        # Metrics should still be computed, just assertions skipped.
        assert "hpwl" in ref.metrics
