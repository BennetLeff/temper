"""Tests for quarantine dead-letter pipeline — U7."""

import json

from temper_placer.testing.quarantine import (
    QuarantineEntry,
    classify_error,
    compute_fingerprint,
    compute_stack_hash,
    load_manifest,
    quarantine_error,
    quarantine_summary,
)


class TestClassifyError:
    """Test error taxonomy classification."""

    def test_classify_parse_version_mismatch(self):
        err = ValueError("version mismatch in format_version")
        taxonomy = classify_error("parse", err)
        assert taxonomy == "PARSE_KICAD_VERSION_MISMATCH"

    def test_classify_parse_missing_footprint_lib(self):
        err = RuntimeError("footprint library not found")
        taxonomy = classify_error("parse", err)
        assert taxonomy == "PARSE_MISSING_FOOTPRINT_LIB"

    def test_classify_parse_decode_error(self):
        err = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
        taxonomy = classify_error("parse", err)
        assert taxonomy == "PARSE_DECODE_ERROR"

    def test_classify_parse_empty_board(self):
        err = ValueError("zero components and zero nets found")
        taxonomy = classify_error("parse", err)
        assert taxonomy == "PARSE_EMPTY_BOARD"

    def test_classify_parse_unsupported_syntax_syntaxerror(self):
        err = SyntaxError("unexpected token")
        taxonomy = classify_error("parse", err)
        assert taxonomy == "PARSE_UNSUPPORTED_SYNTAX"

    def test_classify_parse_unknown(self):
        err = Exception("some unexpected parse error")
        taxonomy = classify_error("parse", err)
        assert taxonomy == "PARSE_UNKNOWN"

    def test_classify_preflight_failed(self):
        err = Exception("preflight check failed")
        taxonomy = classify_error("preflight", err)
        assert taxonomy == "STAGE_PREFLIGHT_FAILED"

    def test_classify_geometric_diverged(self):
        err = Exception("optimizer diverged")
        taxonomy = classify_error("geometric", err)
        assert taxonomy == "STAGE_GEOMETRIC_DIVERGED"

    def test_classify_routing_failed(self):
        err = Exception("routing incomplete")
        taxonomy = classify_error("routing", err)
        assert taxonomy == "STAGE_ROUTING_FAILED"

    def test_classify_output_failed(self):
        err = Exception("output serialization error")
        taxonomy = classify_error("output", err)
        assert taxonomy == "STAGE_OUTPUT_FAILED"

    def test_classify_unknown_stage(self):
        err = Exception("something went wrong")
        taxonomy = classify_error("unknown_stage", err)
        assert taxonomy == "UNKNOWN"


class TestComputeStackHash:
    """Test stack-hash computation for error clustering."""

    def test_stack_hash_returns_string(self):
        try:
            raise ValueError("test error")
        except ValueError as exc:
            h = compute_stack_hash(exc)
            assert isinstance(h, str)
            assert len(h) == 12  # SHA256[:12]

    def test_stack_hash_different_errors_different_hashes(self):
        try:
            raise ValueError("error one")
        except ValueError as exc1:
            h1 = compute_stack_hash(exc1)

        try:
            raise KeyError("error two")
        except KeyError as exc2:
            h2 = compute_stack_hash(exc2)

        # Different exception types should produce different hashes
        assert h1 != h2, "Different errors should produce different stack hashes"

    def test_stack_hash_same_error_same_location(self):
        def _raise_and_hash():
            try:
                raise RuntimeError("same error")
            except RuntimeError as exc:
                return compute_stack_hash(exc)

        h1 = _raise_and_hash()
        h2 = _raise_and_hash()

        # Same function, same error, same line => same hash
        assert h1 == h2


class TestComputeFingerprint:
    """Test board fingerprint computation."""

    def test_fingerprint_existing_file(self, tmp_path):
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20240108)\n  (net 0 \"\")\n)\n")

        fp = compute_fingerprint(pcb)
        assert fp["path"] == str(pcb)
        assert fp["exists"] is True
        assert fp["lines"] >= 3
        assert fp["has_kicad_header"] is True

    def test_fingerprint_nonexistent_file(self, tmp_path):
        pcb = tmp_path / "nonexistent.kicad_pcb"
        fp = compute_fingerprint(pcb)
        assert fp["exists"] is False
        assert "size_bytes" not in fp


class TestQuarantineEntry:
    """Test QuarantineEntry dataclass."""

    def test_to_dict(self):
        entry = QuarantineEntry(
            board_id="test_board",
            board_path="/tmp/test.kicad_pcb",
            stage="parse",
            error_class="ValueError",
            error_message="test error",
            stack_hash="abc123def456",
            taxonomy="PARSE_UNSUPPORTED_SYNTAX",
        )
        d = entry.to_dict()
        assert d["board_id"] == "test_board"
        assert d["stage"] == "parse"
        assert d["taxonomy"] == "PARSE_UNSUPPORTED_SYNTAX"
        assert "taxonomy_label" in d
        assert d["taxonomy_label"] != ""

    def test_to_json(self):
        entry = QuarantineEntry(
            board_id="test_board",
            board_path="/tmp/test.kicad_pcb",
            stage="routing",
            error_class="RuntimeError",
            error_message="route failed",
            stack_hash="deadbeef0000",
            taxonomy="STAGE_ROUTING_FAILED",
        )
        j = entry.to_json()
        data = json.loads(j)
        assert data["board_id"] == "test_board"
        assert data["taxonomy"] == "STAGE_ROUTING_FAILED"


class TestQuarantineError:
    """Test quarantine_error pipeline."""

    def test_quarantine_error_creates_entry(self, tmp_path):
        qdir = tmp_path / "quarantine"
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)\n")

        err = ValueError("parse error: version")
        entry = quarantine_error(qdir, "board_1", pcb, "parse", err)

        assert isinstance(entry, QuarantineEntry)
        assert entry.board_id == "board_1"
        assert entry.taxonomy == "PARSE_KICAD_VERSION_MISMATCH"

        # Check manifest was created
        manifest_path = qdir / "manifest.json"
        assert manifest_path.exists()

    def test_quarantine_error_writes_entry_file(self, tmp_path):
        qdir = tmp_path / "quarantine"
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)\n")

        err = RuntimeError("routing error")
        quarantine_error(qdir, "board_2", pcb, "routing", err)

        # Find the written JSON file
        json_files = list(qdir.rglob("*.json"))
        # Exclude manifest
        entry_files = [f for f in json_files if f.name != "manifest.json"]
        assert len(entry_files) >= 1, "quarantine_error should write an entry JSON file"


class TestLoadManifest:
    """Test load_manifest reading."""

    def test_load_manifest_empty_dir(self, tmp_path):
        qdir = tmp_path / "quarantine"
        qdir.mkdir()
        manifest = load_manifest(qdir)
        assert manifest == {"entries": [], "taxonomy_counts": {}}

    def test_load_manifest_after_quarantine(self, tmp_path):
        qdir = tmp_path / "quarantine"
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)\n")

        err = ValueError("test")
        quarantine_error(qdir, "board_3", pcb, "parse", err)

        manifest = load_manifest(qdir)
        assert len(manifest["entries"]) >= 1
        assert "taxonomy_counts" in manifest


class TestQuarantineSummary:
    """Test quarantine_summary formatting."""

    def test_summary_empty(self, tmp_path):
        qdir = tmp_path / "quarantine"
        qdir.mkdir()
        s = quarantine_summary(qdir)
        assert "0 total entries" in s

    def test_summary_after_quarantine(self, tmp_path):
        qdir = tmp_path / "quarantine"
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)\n")

        err = ValueError("version mismatch")
        quarantine_error(qdir, "board_4", pcb, "parse", err)

        s = quarantine_summary(qdir)
        assert "1 total entries" in s
        assert "PARSE_KICAD_VERSION_MISMATCH" in s
