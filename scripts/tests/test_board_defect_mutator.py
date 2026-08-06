"""Unit tests for the board-defect mutation harness (plan 2026-08-02-024,
R38, U1).

These tests exercise the mutation transforms against the REAL committed
board (``pcb/temper.kicad_pcb``) via kiutils -- no kicad-cli is required,
and the committed board is never modified: every mutation writes a fresh
copy to a temp directory (the scratch-mutation-then-revert discipline of
``test_gen_repo_state.py``).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from board_defect_mutator import (  # noqa: E402
    MutationError,
    apply_mutation,
    board_content_hash,
    copy_board,
    footprint_positions,
    mutate_creepage,
    mutate_off_board,
    mutate_pad_short,
)
from kiutils.board import Board  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

# The committed board's Edge.Cuts outline (20,20)-(172,254).
OUTLINE_MAX_Y = 254.0


@pytest.fixture()
def tmpdir(tmp_path):
    return tmp_path


def _read_board(path: Path) -> Board:
    return Board.from_file(str(path))


def _ref_positions(board: Board) -> dict[str, tuple[float, float]]:
    return footprint_positions(board)


@pytest.mark.skipif(not BOARD.exists(), reason="committed board not available")
class TestMutateOffBoard:
    def test_moves_exactly_one_named_footprint_outside_outline(self, tmpdir):
        out = tmpdir / "offboard.kicad_pcb"
        mutate_off_board(BOARD, out, "C26", (59.38, 256.0), seed=1)

        before = _ref_positions(_read_board(BOARD))
        after = _ref_positions(_read_board(out))

        assert after["C26"] == (59.38, 256.0)
        # Outside the outline: y > 254.
        assert after["C26"][1] > OUTLINE_MAX_Y
        # No other footprint position changed.
        moved = {ref for ref in before if before[ref] != after.get(ref)}
        assert moved == {"C26"}

    def test_source_board_untouched(self, tmpdir):
        out = tmpdir / "offboard.kicad_pcb"
        before_hash = board_content_hash(BOARD)
        mutate_off_board(BOARD, out, "C26", (59.38, 256.0), seed=1)
        assert board_content_hash(BOARD) == before_hash

    def test_missing_footprint_fails_closed(self, tmpdir):
        with pytest.raises(MutationError):
            mutate_off_board(BOARD, tmpdir / "x.kicad_pcb", "ZZ_NOT_A_REF", (1.0, 1.0), seed=1)


@pytest.mark.skipif(not BOARD.exists(), reason="committed board not available")
class TestMutatePadShort:
    def test_places_exactly_two_named_pads_in_overlap(self, tmpdir):
        out = tmpdir / "padshort.kicad_pcb"
        result = mutate_pad_short(BOARD, out, "C28", "1", "2", seed=2)

        mutated = _read_board(out)
        fp = next(f for f in mutated.footprints if (f.properties or {}).get("Reference") == "C28")
        pad1 = next(p for p in fp.pads if p.number == "1")
        pad2 = next(p for p in fp.pads if p.number == "2")

        # pad 2's copper now sits exactly on pad 1's position (different
        # nets -> a real short), and NO pad's net was rewritten.
        assert (pad2.position.X, pad2.position.Y) == (pad1.position.X, pad1.position.Y)
        assert pad1.net.name != pad2.net.name
        assert result.summary["nets_changed"] == 0

    def test_no_other_pad_position_or_net_changed(self, tmpdir):
        out = tmpdir / "padshort.kicad_pcb"
        mutate_pad_short(BOARD, out, "C28", "1", "2", seed=2)

        before = _read_board(BOARD)
        after = _read_board(out)

        def pad_signature(board: Board):
            sig = {}
            for fp in board.footprints:
                ref = (fp.properties or {}).get("Reference")
                for pad in fp.pads:
                    sig[(ref, pad.number)] = (
                        pad.position.X, pad.position.Y,
                        pad.net.name if pad.net else None,
                    )
            return sig

        sig_before = pad_signature(before)
        sig_after = pad_signature(after)
        changed = {k for k in sig_before if sig_before[k] != sig_after.get(k)}
        assert changed == {("C28", "2")}

    def test_same_net_pair_rejected(self, tmpdir):
        # Find a footprint whose two pads are on the same net is unusual on
        # this board; instead assert the guard fires on equal pads.
        with pytest.raises(MutationError):
            mutate_pad_short(BOARD, tmpdir / "x.kicad_pcb", "C28", "1", "1", seed=2)

    def test_missing_pad_fails_closed(self, tmpdir):
        with pytest.raises(MutationError):
            mutate_pad_short(BOARD, tmpdir / "x.kicad_pcb", "C28", "1", "99", seed=2)


@pytest.mark.skipif(not BOARD.exists(), reason="committed board not available")
class TestMutateCreepage:
    def test_moves_exactly_one_component_preserves_others(self, tmpdir):
        out = tmpdir / "creepage.kicad_pcb"
        mutate_creepage(BOARD, out, "C8", (116.26, 138.72), seed=3)

        before = _ref_positions(_read_board(BOARD))
        after = _ref_positions(_read_board(out))
        assert after["C8"] == (116.26, 138.72)
        moved = {ref for ref in before if before[ref] != after.get(ref)}
        assert moved == {"C8"}


@pytest.mark.skipif(not BOARD.exists(), reason="committed board not available")
class TestDeterminism:
    def test_same_seed_produces_byte_identical_boards(self, tmpdir):
        out1 = tmpdir / "a.kicad_pcb"
        out2 = tmpdir / "b.kicad_pcb"
        mutate_off_board(BOARD, out1, "C26", (59.38, 256.0), seed=1)
        mutate_off_board(BOARD, out2, "C26", (59.38, 256.0), seed=1)
        assert out1.read_bytes() == out2.read_bytes()

        out3 = tmpdir / "c.kicad_pcb"
        out4 = tmpdir / "d.kicad_pcb"
        mutate_pad_short(BOARD, out3, "C28", "1", "2", seed=2)
        mutate_pad_short(BOARD, out4, "C28", "1", "2", seed=2)
        assert out3.read_bytes() == out4.read_bytes()

    def test_unmutated_copy_byte_identical_to_committed_board(self, tmpdir):
        out = tmpdir / "clean.kicad_pcb"
        copy_board(BOARD, out)
        assert out.read_bytes() == BOARD.read_bytes()

    def test_seed_content_hash_recorded(self, tmpdir):
        out = tmpdir / "m.kicad_pcb"
        result = mutate_off_board(BOARD, out, "C26", (59.38, 256.0), seed=7)
        expected = hashlib.sha256(
            f"7:{result.mutated_sha256}".encode()
        ).hexdigest()
        assert result.seed_board_sha256 == expected
        assert result.board_sha256 == board_content_hash(BOARD)
        assert result.mutated_sha256 == board_content_hash(out)


@pytest.mark.skipif(not BOARD.exists(), reason="committed board not available")
class TestApplyMutationDispatch:
    def test_dispatches_manifest_params(self, tmpdir):
        out = tmpdir / "m.kicad_pcb"
        result = apply_mutation(
            BOARD,
            "pad-short",
            {"ref": "C28", "pad_a": "1", "pad_b": "2"},
            seed=2,
            out_path=out,
        )
        assert result.mutation == "pad-short"
        assert out.exists()

    def test_unknown_mutation_fails_closed(self, tmpdir):
        with pytest.raises(MutationError):
            apply_mutation(BOARD, "no-such-defect", {}, seed=1, out_path=tmpdir / "x.kicad_pcb")
