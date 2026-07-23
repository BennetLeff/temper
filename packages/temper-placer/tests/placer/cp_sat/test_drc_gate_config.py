"""Unit tests for the portable KiCad footprint-library directory resolution.

Covers plan 2026-07-23-001 U1: ``_resolve_kicad_footprint_dir()`` replaces
the macOS-hardcoded ``KICAD7_FOOTPRINT_DIR`` in ``DrcGate`` with a portable
env-var + search-path approach that works on Linux CI and macOS dev.
Fail-closed as ``UNMEASURED`` when no directory resolves (anti-false-zero
discipline per ``docs/solutions/logic-errors/
weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md``).
"""

from __future__ import annotations

from pathlib import Path

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    DrcGate,
    GateStatus,
    _resolve_kicad_footprint_dir,
)


# ---------------------------------------------------------------------------
# Unit: _resolve_kicad_footprint_dir
# ---------------------------------------------------------------------------


class TestResolveKicadFootprintDir:
    """Direct unit tests for ``_resolve_kicad_footprint_dir()``."""

    def test_env_var_precedence(self, monkeypatch):
        """``KICAD7_FOOTPRINT_DIR`` env var takes precedence over all search paths."""
        monkeypatch.setenv("KICAD7_FOOTPRINT_DIR", "/custom/path/to/footprints")
        result = _resolve_kicad_footprint_dir()
        assert result == Path("/custom/path/to/footprints")

    def test_env_var_precedence_over_existing_search_paths(self, monkeypatch):
        """Env var wins even when a candidate search path also exists on disk."""
        monkeypatch.setenv("KICAD7_FOOTPRINT_DIR", "/my/override")

        # Make several candidate paths appear to exist on disk.
        original_is_dir = Path.is_dir

        def _mock_is_dir(self: Path) -> bool:
            if str(self) in {
                "/usr/share/kicad/footprints",
                "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
            }:
                return True
            return original_is_dir(self)

        monkeypatch.setattr(Path, "is_dir", _mock_is_dir)

        result = _resolve_kicad_footprint_dir()
        assert result == Path("/my/override")

    def test_linux_path_resolved(self, monkeypatch):
        """First existing Linux search path wins when env var is unset."""
        monkeypatch.delenv("KICAD7_FOOTPRINT_DIR", raising=False)

        original_is_dir = Path.is_dir

        def _mock_is_dir(self: Path) -> bool:
            if str(self) == "/usr/share/kicad/footprints":
                return True
            return False

        monkeypatch.setattr(Path, "is_dir", _mock_is_dir)

        result = _resolve_kicad_footprint_dir()
        assert result == Path("/usr/share/kicad/footprints")

    def test_linux_fallback_path(self, monkeypatch):
        """Falls back to a later Linux candidate when earlier ones are missing."""
        monkeypatch.delenv("KICAD7_FOOTPRINT_DIR", raising=False)

        original_is_dir = Path.is_dir

        def _mock_is_dir(self: Path) -> bool:
            if str(self) == "/usr/share/kicad/7.0/footprints":
                return True
            return False

        monkeypatch.setattr(Path, "is_dir", _mock_is_dir)

        result = _resolve_kicad_footprint_dir()
        assert result == Path("/usr/share/kicad/7.0/footprints")

    def test_macos_fallback(self, monkeypatch):
        """macOS path is used when no Linux paths exist and env var is unset."""
        monkeypatch.delenv("KICAD7_FOOTPRINT_DIR", raising=False)

        original_is_dir = Path.is_dir

        def _mock_is_dir(self: Path) -> bool:
            if str(self) == "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints":
                return True
            return False

        monkeypatch.setattr(Path, "is_dir", _mock_is_dir)

        result = _resolve_kicad_footprint_dir()
        assert result == Path(
            "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
        )

    def test_nothing_found_returns_none(self, monkeypatch):
        """Returns ``None`` when no env var and no candidate path exists."""
        monkeypatch.delenv("KICAD7_FOOTPRINT_DIR", raising=False)

        original_is_dir = Path.is_dir

        def _mock_is_dir(self: Path) -> bool:
            return False  # Nothing exists.

        monkeypatch.setattr(Path, "is_dir", _mock_is_dir)

        result = _resolve_kicad_footprint_dir()
        assert result is None


# ---------------------------------------------------------------------------
# Integration: DrcGate returns UNMEASURED when no footprint dir is found
# ---------------------------------------------------------------------------


class TestDrcGateUnmeasuredWhenNoFootprintDir:
    """The DRC gate must return ``UNMEASURED``, not ``CLEAN`` or ``VIOLATIONS``,
    when ``_resolve_kicad_footprint_dir()`` returns ``None``.  This is the
    regression test for the project's anti-false-zero discipline.
    """

    def test_stub_pcb_but_no_footprint_dir(self, monkeypatch, tmp_path):
        """When footprint dir is unresolvable, gate fails closed as UNMEASURED."""
        # Force _resolve_kicad_footprint_dir to return None.
        monkeypatch.setattr(
            "temper_placer.placer.cp_sat.gates._resolve_kicad_footprint_dir",
            lambda: None,
        )

        # Create a minimal PCB file so the "no PCB" guard doesn't fire first.
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)\n")

        state = BoardState(routed_pcb_path=pcb)
        gate = DrcGate()
        result = gate.check(state)

        assert result.status == GateStatus.UNMEASURED, (
            "Gate must be UNMEASURED when footprint dir is missing — "
            "not CLEAN (false-zero regression)."
        )
        assert "footprint library directory not found" in result.error_message.lower()
