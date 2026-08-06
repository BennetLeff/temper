"""Tests for firmware/tools/check_board_derivation_coverage.py (plan 2026-08-02-027, U4).

Synthetic registry / config.yaml / pll_control.h fixtures under
``tmp_path``; the drift guard's pure functions are tested directly, and
``main()`` is exercised through a fixture tree by monkeypatching the
module-level paths (the real files are covered by running the guard
itself).
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_board_derivation_coverage as guard  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def _registry(path: Path, constants: list[str]) -> Path:
    derivations = "\n".join(
        f"  - constant: {c}\n    firmware_file: firmware/config.yaml\n"
        f"    formula: max31865_low_threshold_word\n    compare: \"==\"\n    inputs: []"
        for c in constants
    )
    return _write(path, f"version: 1\nderivations:\n{derivations}\n")


def _config_yaml(path: Path, annotated: list[str]) -> Path:
    entries = "\n".join(
        f"  - c_symbol: {c}\n    field: f\n    value: 1\n    c_type: uint16_t\n"
        f"    board_derivation: true"
        for c in annotated
    )
    return _write(path, f"thresholds:\n{entries}\n")


def _pll_header(path: Path, marked_defines: list[str]) -> Path:
    defines = "\n".join(
        f"#define {name} 100   /**< ... @board-derived ... */" for name in marked_defines
    )
    return _write(
        path,
        "#ifndef PLL_CONTROL_H\n#define PLL_CONTROL_H\n"
        "#define UNMARKED_DECOY 5\n" + defines + "\n#endif\n",
    )


class TestRegistryConstants:
    def test_collects_all_constants_in_order(self, tmp_path: Path) -> None:
        reg = _registry(tmp_path / "r.yaml", ["A", "B", "C"])
        assert guard.registry_constants(reg) == ["A", "B", "C"]

    def test_empty_registry_fails_closed(self, tmp_path: Path) -> None:
        reg = _write(tmp_path / "r.yaml", "version: 1\nderivations: []\n")
        with pytest.raises(guard.CoverageGateError, match="zero derivations"):
            guard.registry_constants(reg)


class TestAnnotatedConfigConstants:
    def test_collects_board_derivation_marked_entries(self, tmp_path: Path) -> None:
        cfg = _config_yaml(tmp_path / "c.yaml", ["A", "B"])
        assert guard.annotated_config_constants(cfg) == ["A", "B"]

    def test_unmarked_entries_are_ignored(self, tmp_path: Path) -> None:
        cfg = _write(
            tmp_path / "c.yaml",
            """\
            thresholds:
              - c_symbol: A
                field: f
                value: 1
                c_type: uint16_t
                board_derivation: true
              - c_symbol: B
                field: f
                value: 1
                c_type: uint16_t
            """,
        )
        assert guard.annotated_config_constants(cfg) == ["A"]


class TestAnnotatedHeaderConstants:
    def test_collects_marked_defines(self, tmp_path: Path) -> None:
        header = _pll_header(tmp_path / "pll.h", ["PLL_MIN_FREQ_HZ"])
        assert guard.annotated_header_constants(header) == ["PLL_MIN_FREQ_HZ"]

    def test_unmarked_defines_are_ignored(self, tmp_path: Path) -> None:
        header = _write(
            tmp_path / "pll.h",
            """\
            #define PLL_MIN_FREQ_HZ 44000 /**< @board-derived */
            #define PLL_MAX_FREQ_HZ 50000 /**< no marker */
            """,
        )
        assert guard.annotated_header_constants(header) == ["PLL_MIN_FREQ_HZ"]

    def test_marker_on_a_different_line_is_not_an_annotation(self, tmp_path: Path) -> None:
        """The @board-derived marker must be on the SAME line as the
        #define -- a comment elsewhere in the file (describing the block)
        must not register the constant."""
        header = _write(
            tmp_path / "pll.h",
            """\
            /* This whole block is board-derived. */
            #define PLL_MIN_FREQ_HZ 44000
            """,
        )
        assert guard.annotated_header_constants(header) == []


class TestMain:
    def _fixture_tree(self, tmp_path: Path) -> Path:
        """registry with A+B; config.yaml marks A+B; header marks A."""
        _registry(tmp_path / "firmware" / "tools" / "board_derivations.yaml", ["A", "B"])
        _config_yaml(tmp_path / "firmware" / "config.yaml", ["A", "B"])
        _pll_header(tmp_path / "firmware" / "components" / "control" / "pll_control.h", ["A"])
        return tmp_path

    def test_happy_path_all_annotated_constants_registered(self, tmp_path: Path, monkeypatch) -> None:
        """U4 test scenario 1: the registry covers all annotated constants
        and the guard passes."""
        self._fixture_tree(tmp_path)
        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        assert guard.main() == guard.EXIT_OK

    def test_unregistered_annotated_constant_fails_naming_it(self, tmp_path: Path, monkeypatch) -> None:
        """U4 test scenario 2: a constant newly annotated with the marker
        but missing from the registry fails the guard naming the constant."""
        self._fixture_tree(tmp_path)
        # Annotate C in config.yaml but do NOT register it.
        (tmp_path / "firmware" / "config.yaml").write_text(
            (tmp_path / "firmware" / "config.yaml").read_text() + "\nthresholds:\n"
            "  - c_symbol: C\n    field: f\n    value: 1\n    c_type: uint16_t\n"
            "    board_derivation: true\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        assert guard.main() == guard.EXIT_VIOLATION

    def test_missing_registry_is_gate_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        assert guard.main() == guard.EXIT_GATE_ERROR
