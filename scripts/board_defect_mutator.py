#!/usr/bin/env python3
"""Deterministic board-defect mutations on run-time copies of the committed
board -- the mutation half of the board-defect mutation corpus (plan
2026-08-02-024, R38).

The committed ``pcb/temper.kicad_pcb`` is NEVER modified by anything in this
module. Every mutation function reads ``board_path``, applies one named
defect transform to a parsed copy, and writes a NEW board file to
``out_path``. The corpus runner (``check_board_defect_corpus.py``) re-derives
every mutated board from the committed board on every run, so no mutated
board is ever committed (KTD3) and the DRC-ceiling re-measurement convention
(which fires only when the committed board's content hash changes) stays
inert (KTD1).

The three defect classes (R38): component off-board, pad short, creepage
crossing. The real defect instances are ALREADY on the committed board (the
tank cap staged off-outline at ``(at 20.0 272.75)``, the C1 pad2<->R7 pad2
short, the DC_BUS<->LV_CONTROL creepage crossings), so "re-create the
defect" would be a no-op. Each seed is therefore taken from a DEFECT-FREE
starting point and asserted with a count-delta in the runner: move an
in-board footprint off-board, short a not-yet-shorted pad pair, compress a
currently-compliant creepage pair.

Determinism contract (U1 test 4): a mutation is a pure function of (board
bytes, params). Two runs with the same seed (i.e. the same params, keyed by
seed in ``scripts/board_defect_corpus.yaml``) produce byte-identical mutated
boards -- verified over kiutils' S-expression serializer. ``seed`` is
recorded alongside the mutated board's content hash so any run is
reproducible from its manifest entry.

Usage:
    python scripts/board_defect_mutator.py --mutation off-board --ref C26 \\
        --position 59.38 256.0 --seed 1 --out /tmp/m.kicad_pcb
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kiutils.board import Board
from kiutils.items.common import Position

REPO_ROOT = Path(__file__).resolve().parent.parent

# The committed board's Edge.Cuts outline (20,20)-(172,254) -- used only for
# documentation/validation messages; mutations take explicit positions.
BOARD_OUTLINE = ((20.0, 20.0), (172.0, 254.0))

# The three defect classes this corpus seeds (R38). Keys are the
# ``mutation`` names used by scripts/board_defect_corpus.yaml.
MUTATIONS = ("off-board", "pad-short", "creepage")


class MutationError(RuntimeError):
    """Raised when a mutation's parameters do not resolve against the board
    (missing footprint, missing pad, pad-less footprint). Fail-closed: a
    mutation that cannot find its target must never silently write an
    unmutated board."""


@dataclass
class MutationResult:
    """Everything a caller needs to audit one applied mutation.

    ``board_sha256`` is the source (committed) board's content hash;
    ``mutated_sha256`` is the derived board's content hash; and
    ``seed_board_sha256`` is ``sha256(f"{seed}:{mutated_bytes}")`` -- the
    plan's "content hash of seed and mutated board", the exact value that
    must reproduce for a rerun to be byte-identical (KTD3).
    """

    mutation: str
    seed: int
    board_sha256: str
    mutated_sha256: str
    seed_board_sha256: str
    summary: dict[str, Any]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def board_content_hash(path: Path) -> str:
    """Content hash of a board file's exact bytes (provenance convention:
    same as scripts/_lib/measurement_provenance.py hashes the board)."""
    return sha256_bytes(Path(path).read_bytes())


def find_footprint(board: Board, ref: str):
    """Return the footprint whose ``Reference`` property is *ref*."""
    for fp in board.footprints:
        if (fp.properties or {}).get("Reference") == ref:
            return fp
    raise MutationError(f"no footprint with Reference {ref!r} on the board")


def footprint_positions(board: Board) -> dict[str, tuple[float, float]]:
    """{Reference: (x, y)} for every footprint -- used to prove a mutation
    moved exactly one footprint (U1 test scenarios 1/3)."""
    out: dict[str, tuple[float, float]] = {}
    for fp in board.footprints:
        ref = (fp.properties or {}).get("Reference")
        if ref is not None:
            out[ref] = (fp.position.X, fp.position.Y)
    return out


def _write_and_hash(board: Board, out_path: Path) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    board.to_file(str(out_path))
    return board_content_hash(out_path)


def mutate_off_board(
    board_path: Path,
    out_path: Path,
    ref: str,
    position: tuple[float, float],
    seed: int,
) -> MutationResult:
    """Move footprint *ref* to an absolute board position (the caller names
    a position outside the Edge.Cuts outline -- the off-board defect class).

    Deterministic: ``(x, y)`` is applied verbatim; nothing else on the board
    is touched.
    """
    source_hash = board_content_hash(board_path)
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    old_pos = (fp.position.X, fp.position.Y)
    fp.position = Position(position[0], position[1], fp.position.angle)
    mutated_hash = _write_and_hash(board, out_path)
    return MutationResult(
        mutation="off-board",
        seed=seed,
        board_sha256=source_hash,
        mutated_sha256=mutated_hash,
        seed_board_sha256=sha256_bytes(f"{seed}:{mutated_hash}".encode()),
        summary={
            "ref": ref,
            "from_mm": list(old_pos),
            "to_mm": list(position),
            "moved_footprints": [ref],
            "footprints_total": len(board.footprints),
        },
    )


def mutate_pad_short(
    board_path: Path,
    out_path: Path,
    ref: str,
    pad_a: str,
    pad_b: str,
    seed: int,
) -> MutationResult:
    """Short a not-yet-shorted pad pair: move pad *pad_b*'s copper onto pad
    *pad_a*'s position inside footprint *ref*.

    Why position, not net, joining (review fix on the plan's
    ``rewrite a pad's net ordinal`` approach): on a static board, rewriting
    one pad's net to another's can only REMOVE a short (a ``shorting_items``
    violation requires physically overlapping copper on *different* nets;
    two pads of one net touching are not a violation). To CREATE a
    shorting_item deterministically the copper must physically overlap while
    the nets stay distinct -- exactly what moving pad *pad_b* onto pad
    *pad_a* does. No net is rewritten anywhere on the board.
    """
    source_hash = board_content_hash(board_path)
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    pad_a_obj = next((p for p in fp.pads if p.number == pad_a), None)
    pad_b_obj = next((p for p in fp.pads if p.number == pad_b), None)
    if pad_a_obj is None or pad_b_obj is None:
        raise MutationError(
            f"footprint {ref!r} has no pads named {pad_a!r}/{pad_b!r} "
            f"(pads: {sorted(p.number for p in fp.pads)})"
        )
    if pad_a == pad_b:
        raise MutationError("pad_a and pad_b must be distinct pads")
    net_a = pad_a_obj.net.name if pad_a_obj.net else None
    net_b = pad_b_obj.net.name if pad_b_obj.net else None
    if net_a is None or net_b is None:
        raise MutationError(
            f"footprint {ref!r} pads {pad_a!r}/{pad_b!r} have no nets "
            "(unconnected copper cannot be shorted)"
        )
    if net_a == net_b:
        raise MutationError(
            f"footprint {ref!r} pads {pad_a!r}/{pad_b!r} are already on the "
            f"same net {net_a!r} -- joining them is not a defect"
        )
    old_pos_b = (pad_b_obj.position.X, pad_b_obj.position.Y)
    pad_b_obj.position = Position(
        pad_a_obj.position.X, pad_a_obj.position.Y, pad_a_obj.position.angle
    )
    mutated_hash = _write_and_hash(board, out_path)
    return MutationResult(
        mutation="pad-short",
        seed=seed,
        board_sha256=source_hash,
        mutated_sha256=mutated_hash,
        seed_board_sha256=sha256_bytes(f"{seed}:{mutated_hash}".encode()),
        summary={
            "ref": ref,
            "pad_a": pad_a,
            "pad_b": pad_b,
            "net_a": net_a,
            "net_b": net_b,
            "pad_b_from_mm": list(old_pos_b),
            "pad_b_to_mm": [pad_a_obj.position.X, pad_a_obj.position.Y],
            "nets_changed": 0,
            "footprints_total": len(board.footprints),
        },
    )


def mutate_creepage(
    board_path: Path,
    out_path: Path,
    ref: str,
    position: tuple[float, float],
    seed: int,
) -> MutationResult:
    """Move footprint *ref* to an absolute board position chosen to compress
    a currently-compliant HV<->SELV pair below the enforced creepage margin
    (the creepage-crossing defect class).

    Same mechanism as :func:`mutate_off_board` -- a single-footprint move --
    with a different contract: the runner asserts the DC_BUS<->LV_CONTROL
    creepage count rises (per-class count-delta against the documented
    known-finding baseline), not that the footprint leaves the outline.
    """
    source_hash = board_content_hash(board_path)
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    old_pos = (fp.position.X, fp.position.Y)
    fp.position = Position(position[0], position[1], fp.position.angle)
    mutated_hash = _write_and_hash(board, out_path)
    return MutationResult(
        mutation="creepage",
        seed=seed,
        board_sha256=source_hash,
        mutated_sha256=mutated_hash,
        seed_board_sha256=sha256_bytes(f"{seed}:{mutated_hash}".encode()),
        summary={
            "ref": ref,
            "from_mm": list(old_pos),
            "to_mm": list(position),
            "moved_footprints": [ref],
            "footprints_total": len(board.footprints),
        },
    )


# mutation name -> (callable, required params). Used by the corpus runner to
# dispatch the manifest's seed entries, and by the CLI.
_MUTATION_FUNCS: dict[str, Any] = {
    "off-board": mutate_off_board,
    "pad-short": mutate_pad_short,
    "creepage": mutate_creepage,
}


def apply_mutation(
    board_path: Path,
    mutation: str,
    params: dict[str, Any],
    seed: int,
    out_path: Path,
) -> MutationResult:
    """Dispatch a named mutation with its manifest ``params`` dict."""
    if mutation not in _MUTATION_FUNCS:
        raise MutationError(
            f"unknown mutation {mutation!r} (known: {sorted(_MUTATION_FUNCS)})"
        )
    if mutation == "off-board":
        return mutate_off_board(
            board_path, out_path, params["ref"], tuple(params["position_mm"]), seed
        )
    if mutation == "pad-short":
        return mutate_pad_short(
            board_path, out_path, params["ref"], params["pad_a"], params["pad_b"], seed
        )
    if mutation == "creepage":
        return mutate_creepage(
            board_path, out_path, params["ref"], tuple(params["position_mm"]), seed
        )
    raise AssertionError("unreachable")


def copy_board(board_path: Path, out_path: Path) -> str:
    """Byte-exact copy of the committed board -- the runner's unmutated
    control, byte-identical to the committed file by construction (U1 test
    scenario 5). Returns the source content hash."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(board_path, out_path)
    return board_content_hash(board_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=REPO_ROOT / "pcb/temper.kicad_pcb")
    parser.add_argument("--mutation", choices=sorted(_MUTATION_FUNCS), required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--position", nargs=2, type=float, metavar=("X", "Y"))
    parser.add_argument("--pad-a")
    parser.add_argument("--pad-b")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.mutation in ("off-board", "creepage"):
        if args.position is None:
            parser.error(f"--mutation {args.mutation} requires --position X Y")
        params: dict[str, Any] = {"ref": args.ref, "position_mm": list(args.position)}
    else:
        if args.pad_a is None or args.pad_b is None:
            parser.error("--mutation pad-short requires --pad-a and --pad-b")
        params = {"ref": args.ref, "pad_a": args.pad_a, "pad_b": args.pad_b}

    try:
        result = apply_mutation(args.board, args.mutation, params, args.seed, args.out)
    except MutationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    import json

    print(json.dumps(result.__dict__, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
