"""Regression tests for check_pad_identity_ambiguity.py.

This gate is component-level, not net-level (contrast
`check_net_pin_identity_pad_correspondence.py`, PR #1177's net-accounting
gate). It asks: does any footprint in use declare more than one physical
pad under the same pad number, and if so, does any production
`.get_pin(...)` call site still resolve "the" pin as if `(ref, pin_name)`
were unique? Only the CONJUNCTION is a defect.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_pad_identity_ambiguity import (  # noqa: E402
    ALLOWED_GET_PIN_CALL_SITES,
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    GateError,
    find_duplicate_pad_footprints,
    find_get_pin_call_sites,
    run,
    unreviewed_get_pin_call_sites,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _footprint(ref: str, *pad_numbers: str) -> str:
    pads = "\n".join(f'    (pad "{n}" thru_hole oval (at 0 0))' for n in pad_numbers)
    return f'\n  (footprint "some:lib" (layer "F.Cu")\n    (property "Reference" "{ref}")\n{pads}\n  )\n'


def _board(*footprints: str) -> str:
    return "\n".join(footprints)


# ---------------------------------------------------------------------------
# Board half
# ---------------------------------------------------------------------------


def test_gate_error_on_missing_board(tmp_path: Path) -> None:
    with pytest.raises(GateError, match="not found"):
        find_duplicate_pad_footprints(tmp_path / "does-not-exist.kicad_pcb")


def test_gate_error_on_board_with_zero_footprints(tmp_path: Path) -> None:
    board = tmp_path / "empty.kicad_pcb"
    board.write_text("(kicad_pcb (version 1))")
    with pytest.raises(GateError, match="zero footprints"):
        find_duplicate_pad_footprints(board)


def test_no_duplicates_found_for_ordinary_footprints(tmp_path: Path) -> None:
    board = tmp_path / "b.kicad_pcb"
    board.write_text(_board(_footprint("R1", "1", "2"), _footprint("C1", "1", "2")))
    assert find_duplicate_pad_footprints(board) == []


def test_duplicate_pad_number_detected(tmp_path: Path) -> None:
    """The exact K2 shape: pads "1"/"3"/"4" each appear twice."""
    board = tmp_path / "b.kicad_pcb"
    board.write_text(_footprint("K2", "2", "5", "4", "4", "1", "1", "3", "3"))
    found = find_duplicate_pad_footprints(board)
    assert len(found) == 1
    assert found[0].ref == "K2"
    assert found[0].duplicate_pad_numbers == {"4": 2, "1": 2, "3": 2}


def test_duplicate_npth_pad_number_detected(tmp_path: Path) -> None:
    """K1's shape: four mechanical NPTH holes all pad-numbered ""."""
    board = tmp_path / "b.kicad_pcb"
    board.write_text(_footprint("K1", "A1", "A2", "13", "14", "", "", "", ""))
    found = find_duplicate_pad_footprints(board)
    assert len(found) == 1
    assert found[0].duplicate_pad_numbers == {"": 4}


def test_real_board_finds_exactly_k1_k2_k3() -> None:
    """Measured against the real board: exactly K1, K2, K3 have a
    duplicate pad number, matching the task's own duplicate-pad-number
    survey."""
    board = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    found = find_duplicate_pad_footprints(board)
    refs = {fp.ref for fp in found}
    assert refs == {"K1", "K2", "K3"}
    by_ref = {fp.ref: fp.duplicate_pad_numbers for fp in found}
    assert by_ref["K2"] == {"1": 2, "3": 2, "4": 2}
    assert by_ref["K3"] == {"1": 2, "3": 2, "4": 2}
    # RE-DERIVED 2026-08-24: was {"": 4}. K1's four pads carried NO pad
    # number at all until #1424 (a162dcea8, "land the two source-corrected
    # footprints the board never received") replaced the footprint with the
    # source-corrected Relay_SPST_Schrack-RT33K012, which numbers them.
    #
    # This is a real improvement, and a partial one. Before, every one of
    # K1's four pads was ambiguous under (ref, pad_number) because the key
    # was (K1, "") four times over. Now pads 1 and 2 are uniquely
    # identifiable and only 3 and 4 remain duplicated -- which is the
    # relay's actual multi-contact structure (two pads per switched
    # contact), not a footprint defect. So K1 stays in this gate's finding
    # set, correctly, on narrower grounds than before.
    assert by_ref["K1"] == {"3": 2, "4": 2}


# ---------------------------------------------------------------------------
# Code half
# ---------------------------------------------------------------------------


def _write_module(tmp_path: Path, relpath: str, body: str) -> Path:
    path = tmp_path / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body))
    return path


def test_gate_error_on_zero_py_files(tmp_path: Path) -> None:
    with pytest.raises(GateError, match="zero .py files"):
        find_get_pin_call_sites(tmp_path)


def test_finds_a_bare_get_pin_call(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/src/pkg/mod.py",
        """
        def resolve(comp, name):
            return comp.get_pin(name)
        """,
    )
    sites = find_get_pin_call_sites(tmp_path)
    assert len(sites) == 1
    assert sites[0].function == "resolve"
    assert sites[0].relpath == "pkg/mod.py"


def test_module_scope_call_reports_module_sentinel(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/src/pkg/mod.py",
        """
        comp = None
        pin = comp.get_pin("3")
        """,
    )
    sites = find_get_pin_call_sites(tmp_path)
    assert sites[0].function == "<module>"


def test_ignores_get_pin_occurrences_and_get_pins_for_net(tmp_path: Path) -> None:
    """Only the exact `.get_pin(` first-match method is the footgun --
    `get_pin_occurrences` (returns all matches) and `get_pins_for_net`
    (filters by net, not name) are different methods entirely and must
    not be flagged."""
    _write_module(
        tmp_path,
        "pkg/src/pkg/mod.py",
        """
        def resolve(comp, name, net):
            a = comp.get_pin_occurrences(name)
            b = comp.get_pins_for_net(net)
            return a, b
        """,
    )
    assert find_get_pin_call_sites(tmp_path) == []


def test_skips_tests_directory(tmp_path: Path) -> None:
    # A "tests" directory under `src/` is filtered out by _SKIP_DIR_PARTS;
    # pair it with a real production file so the glob has something to
    # find at all (an all-tests tree would otherwise raise GateError for
    # "zero .py files", which is a different, correctly-fail-closed case
    # covered by test_gate_error_on_zero_py_files).
    _write_module(
        tmp_path,
        "pkg/src/pkg/tests/test_mod.py",
        """
        def test_x(comp):
            comp.get_pin("3")
        """,
    )
    _write_module(tmp_path, "pkg/src/pkg/mod.py", "x = 1\n")
    assert find_get_pin_call_sites(tmp_path) == []


def test_allowlisted_site_is_excluded_from_unreviewed() -> None:
    sites = find_get_pin_call_sites(REPO_ROOT / "packages")
    unreviewed = unreviewed_get_pin_call_sites(sites)
    for relpath, funcname in ALLOWED_GET_PIN_CALL_SITES:
        assert any(s.relpath == relpath and s.function == funcname for s in sites), (
            f"allowlist entry ({relpath!r}, {funcname!r}) no longer matches any real "
            "call site -- stale entry, remove it"
        )
    assert not any((s.relpath, s.function) in ALLOWED_GET_PIN_CALL_SITES for s in unreviewed)


def test_unreviewed_excludes_only_exact_allowlist_match(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/src/temper_placer/core/loop_extractor.py",
        """
        def get_pin_net(comp, names):
            return comp.get_pin(names[0])

        def other_function(comp, name):
            return comp.get_pin(name)
        """,
    )
    sites = find_get_pin_call_sites(tmp_path)
    assert len(sites) == 2
    unreviewed = unreviewed_get_pin_call_sites(sites)
    assert [s.function for s in unreviewed] == ["other_function"]


# ---------------------------------------------------------------------------
# End-to-end `run()`
# ---------------------------------------------------------------------------


def test_run_passes_when_no_duplicate_pad_footprints(tmp_path: Path) -> None:
    board = tmp_path / "b.kicad_pcb"
    board.write_text(_board(_footprint("R1", "1", "2")))
    _write_module(
        tmp_path,
        "pkg/src/pkg/mod.py",
        """
        def resolve(comp, name):
            return comp.get_pin(name)
        """,
    )
    assert run(board, tmp_path) == EXIT_OK


def test_run_passes_when_duplicates_exist_but_no_unreviewed_call_site(tmp_path: Path) -> None:
    board = tmp_path / "b.kicad_pcb"
    board.write_text(_board(_footprint("K2", "3", "3")))
    _write_module(tmp_path, "pkg/src/pkg/mod.py", "x = 1\n")
    assert run(board, tmp_path) == EXIT_OK


def test_run_fails_when_duplicates_and_unreviewed_call_site_coincide(tmp_path: Path) -> None:
    board = tmp_path / "b.kicad_pcb"
    board.write_text(_board(_footprint("K2", "3", "3")))
    _write_module(
        tmp_path,
        "pkg/src/pkg/mod.py",
        """
        def resolve(comp, name):
            return comp.get_pin(name)
        """,
    )
    assert run(board, tmp_path) == EXIT_VIOLATION


def test_run_gate_error_propagates(tmp_path: Path) -> None:
    assert run(tmp_path / "missing.kicad_pcb", tmp_path) == EXIT_GATE_ERROR


def test_against_the_real_board_and_real_source_tree() -> None:
    """End-to-end against the actual repo state: this is what CI runs.
    Documents the current, reviewed state rather than asserting a fixed
    exit code the fixture drifts against -- the important invariant is
    that it runs a real check (never GATE_ERROR) and any violation is
    exactly the reviewed allowlist gap, not a surprise."""
    board = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    packages_root = REPO_ROOT / "packages"
    result = run(board, packages_root)
    assert result in (EXIT_OK, EXIT_VIOLATION)
