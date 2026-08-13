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

The seven defect classes (R38, extended 2026-08-07 for R9/R10 vacuity
closure -- clearance, courtyard -- and again 2026-08-07 for step 4 of
docs/STRATEGY.md's build order -- hole-to-hole, missing courtyard):
component off-board, pad short, creepage crossing, ordinary copper
clearance, courtyard overlap, drilled-hole-to-hole spacing, and a
footprint with no courtyard defined at all. The real off-board/pad-short/
creepage defect instances are ALREADY on the committed board (the tank cap
staged off-outline at ``(at 20.0 272.75)``, the C1 pad2<->R7 pad2 short, the
DC_BUS<->LV_CONTROL creepage crossings), so "re-create the defect" would be
a no-op. Each seed is therefore taken from a DEFECT-FREE starting point:
move an in-board footprint off-board, short a not-yet-shorted pad pair,
compress a currently-compliant creepage pair, close a currently-compliant
inter-footprint clearance gap, overlap two currently-clear courtyards, bring
two currently-compliant drilled holes too close together, or delete a
footprint's courtyard graphics outright.
Every class is asserted by IDENTITY in the runner (the owning gate must
name the exact seeded ref(s)/pad(s)), not a raw count-delta -- see
``check_board_defect_corpus.py``'s module docstring for why a count-delta
is not trustworthy for this corpus's DRC categories.

``missing-courtyard`` WAS a deliberate exception to "every class in this
module is caught" (2026-08-07 through 2026-08-13): self-verification
proved the injector genuinely deletes the courtyard graphics (independent
re-parse, Sec. "missing_courtyard" below), but the corpus's canonical DRC
measurement path (``temper_placer.validation._drc_api.run_drc``, used
unmodified so every class measures through the SAME path) never observed
it -- see ``check_board_defect_corpus.py``'s module docstring and
``docs/evidence/2026-08-07-missing-courtyard-and-hole-to-hole-classes.md``
for the two independently verified root causes (kicad-cli's compiled-in
default for the ``missing_courtyard`` rule is ``ignore`` without an
accompanying ``.kicad_pro``, which the corpus's mutated-board workdir
never HAD, until ``check_board_defect_corpus.run_corpus()`` was fixed
2026-08-13 to call ``copy_kicad_project_sidecar()`` on every scratch
copy; and even with one, ``run_drc()`` never passes
``--severity-warning``/``--severity-all``, so a ``warning``-severity
rule's output could still be dropped either way -- empirically it is
NOT dropped, so this second cause turned out not to gate the outcome).
With cause (1) closed, this class is now COVERED. Closing it exposed a
different, previously-hidden gap in the ``clearance`` class instead (the
seeded R64/R67 pad pair no longer registers under the corrected,
project-aware measurement) -- see that class's ``uncovered_finding`` note
in ``scripts/board_defect_corpus.yaml``, which is now the module's
DELIBERATE exception, reported per docs/METHODOLOGY.md Sec. 5 ("if a gate
turns out not to catch its own defect class, that is a finding -- report
it, do not weaken the class"), not silently fixed by reimplementing the
measurement path for one class only.

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

# The defect classes this corpus seeds (R38, extended 2026-08-07 for R9/R10
# vacuity closure -- clearance, courtyard -- and again 2026-08-07 for
# STRATEGY.md build-order step 4 -- hole-to-hole, missing-courtyard). Keys
# are the ``mutation`` names used by scripts/board_defect_corpus.yaml.
MUTATIONS = (
    "off-board",
    "pad-short",
    "creepage",
    "clearance",
    "courtyard",
    "hole-to-hole",
    "missing-courtyard",
)


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


def mutate_clearance(
    board_path: Path,
    out_path: Path,
    ref: str,
    position: tuple[float, float],
    seed: int,
) -> MutationResult:
    """Move footprint *ref* to an absolute board position chosen to compress
    a currently-compliant, ordinary (non-HV, non-same-footprint) pad pair on
    DIFFERENT nets below the board's plain copper-to-copper clearance
    requirement (net-class ``clearance``, e.g. Default 0.2mm) -- the generic
    ``clearance`` DRC-category defect class (R9/R10 vacuity closure,
    2026-08-07).

    This is deliberately distinct from the two DRC categories the corpus
    already exercises incidentally: it is not the ``pad-short`` class's
    same-footprint "Fine pitch IC pads" 0.1mm exception (RULE 1 in
    ``generate_kicad_dru.py`` -- that only reduces clearance between two
    pads of ONE footprint, and this mutation moves a whole SEPARATE
    footprint), and it is not the ``creepage`` class's HV<->SELV custom DRU
    boundary (this mutation's target ref/nets are plain LV signal nets, not
    ACMains/HighVoltage). The gap this mutation creates is small but
    strictly positive (no copper overlap) -- unlike ``pad-short``, which
    drives the gap to exactly 0.0mm.

    Same mechanism as :func:`mutate_off_board`/:func:`mutate_creepage` -- a
    single-footprint absolute-position move.
    """
    source_hash = board_content_hash(board_path)
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    old_pos = (fp.position.X, fp.position.Y)
    fp.position = Position(position[0], position[1], fp.position.angle)
    mutated_hash = _write_and_hash(board, out_path)
    return MutationResult(
        mutation="clearance",
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


def mutate_courtyard(
    board_path: Path,
    out_path: Path,
    ref: str,
    position: tuple[float, float],
    seed: int,
) -> MutationResult:
    """Move footprint *ref* to an absolute board position chosen so its
    ``F.CrtYd`` courtyard rectangle overlaps a fixed neighbor's courtyard,
    while the two footprints' copper stays clear (no clearance/short
    defect) -- the ``courtyards_overlap`` defect class (R9/R10 vacuity
    closure, 2026-08-07).

    This directly addresses the 2026-08-04 finding
    (docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md) that
    ``courtyards_overlap`` did not discriminate the ``off-board`` seed: that
    mutation only produced a courtyard collision BY COINCIDENCE of the
    pre-#517 board's geometry (a component's own rotation happened to lay
    its body across a populated region), and stopped working the moment the
    board was re-solved, because "move a component off the board" was never
    a mutation designed to overlap courtyards in the first place -- it is a
    containment defect, now correctly owned by
    ``scripts/check_board_containment.py``. This mutation is the opposite:
    it computes the target position FROM the two footprints' own courtyard
    geometry (an ``F.CrtYd`` ``FpRect``/``FpLine`` bounding box, read via
    kiutils, the same rotation convention as everywhere else in this module)
    so the courtyard overlap is a deterministic property of the seed, not an
    accident of an unrelated placement.

    Same mechanism as :func:`mutate_off_board`/:func:`mutate_creepage` -- a
    single-footprint absolute-position move.
    """
    source_hash = board_content_hash(board_path)
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    old_pos = (fp.position.X, fp.position.Y)
    fp.position = Position(position[0], position[1], fp.position.angle)
    mutated_hash = _write_and_hash(board, out_path)
    return MutationResult(
        mutation="courtyard",
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


def mutate_hole_to_hole(
    board_path: Path,
    out_path: Path,
    ref: str,
    position: tuple[float, float],
    seed: int,
) -> MutationResult:
    """Move footprint *ref* to an absolute board position chosen so one of
    its drilled (PTH) pads sits closer than the board's ``hole_to_hole``
    manufacturing minimum (0.5mm edge-to-edge, ``scripts/generate_kicad_dru.py``)
    to a FIXED anchor footprint's drilled pad, while keeping the two pads on
    the SAME net -- the drilled-hole-spacing defect class (STRATEGY.md build
    order step 4, 2026-08-07).

    Same net, deliberately: ``hole_to_hole`` is a pure manufacturing/
    mechanical constraint (two holes drilled too close together weaken the
    board irrespective of what nets they carry), so pairing same-net pads
    means the pads' own copper can overlap without ALSO tripping
    ``clearance``/``shorting_items`` (which only apply between different
    nets) -- isolating the hole-to-hole signal from the confounds the
    ``clearance``/``courtyard`` classes above were fixed to avoid.

    Same mechanism as :func:`mutate_off_board`/:func:`mutate_creepage` -- a
    single-footprint absolute-position move.
    """
    source_hash = board_content_hash(board_path)
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    old_pos = (fp.position.X, fp.position.Y)
    fp.position = Position(position[0], position[1], fp.position.angle)
    mutated_hash = _write_and_hash(board, out_path)
    return MutationResult(
        mutation="hole-to-hole",
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


def mutate_missing_courtyard(
    board_path: Path,
    out_path: Path,
    ref: str,
    seed: int,
) -> MutationResult:
    """Delete every ``F.CrtYd``/``B.CrtYd`` graphic item from footprint
    *ref* -- the missing-courtyard defect class (STRATEGY.md build order
    step 4, 2026-08-07).

    Unlike every other mutation in this module this is a graphic-item
    deletion, not a position move -- there is no ``position`` parameter.
    Fail-closed self-verification (METHODOLOGY.md Sec. 5, "an injector that
    cannot prove its own mutations took effect is not evidence"): if *ref*
    has zero ``F.CrtYd``/``B.CrtYd`` items to begin with, this raises
    :class:`MutationError` rather than silently writing an unmutated board
    -- exactly the class of no-op ``check_board_defect_corpus.py``'s own
    module docstring documents a real prior instance of (a seeded defect
    that moved a DRC count 11 -> 11 because the mutation never touched what
    it claimed to).
    """
    source_hash = board_content_hash(board_path)
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    removed = [
        item
        for item in fp.graphicItems
        if getattr(item, "layer", None) in ("F.CrtYd", "B.CrtYd")
    ]
    if not removed:
        raise MutationError(
            f"footprint {ref!r} has no F.CrtYd/B.CrtYd graphic items to remove "
            "-- it is already missing a courtyard on the CLEAN board, so "
            "deleting nothing would prove nothing (re-seed onto a ref that "
            "starts with real courtyard graphics)"
        )
    fp.graphicItems = [
        item
        for item in fp.graphicItems
        if getattr(item, "layer", None) not in ("F.CrtYd", "B.CrtYd")
    ]
    mutated_hash = _write_and_hash(board, out_path)
    return MutationResult(
        mutation="missing-courtyard",
        seed=seed,
        board_sha256=source_hash,
        mutated_sha256=mutated_hash,
        seed_board_sha256=sha256_bytes(f"{seed}:{mutated_hash}".encode()),
        summary={
            "ref": ref,
            "removed_courtyard_items": len(removed),
            "removed_item_types": [type(item).__name__ for item in removed],
            "footprints_total": len(board.footprints),
        },
    )


def courtyard_item_count(board_path: Path, ref: str) -> int:
    """Independent re-parse of *board_path* counting ``F.CrtYd``/``B.CrtYd``
    graphic items on footprint *ref* -- used by the corpus runner to verify
    the ``missing-courtyard`` injector's effect directly against the written
    file, separate from (and before) asking the DRC gate anything. This is
    the "injected artifact differs, structurally, independent of the gate
    under test" half of injector self-verification (METHODOLOGY.md Sec. 5);
    the DRC-gate half is a separate, and in this class's case negative,
    finding -- see :func:`mutate_missing_courtyard`'s docstring.
    """
    board = Board.from_file(str(board_path))
    fp = find_footprint(board, ref)
    return sum(
        1
        for item in fp.graphicItems
        if getattr(item, "layer", None) in ("F.CrtYd", "B.CrtYd")
    )


# mutation name -> (callable, required params). Used by the corpus runner to
# dispatch the manifest's seed entries, and by the CLI.
_MUTATION_FUNCS: dict[str, Any] = {
    "off-board": mutate_off_board,
    "pad-short": mutate_pad_short,
    "creepage": mutate_creepage,
    "clearance": mutate_clearance,
    "courtyard": mutate_courtyard,
    "hole-to-hole": mutate_hole_to_hole,
    "missing-courtyard": mutate_missing_courtyard,
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
    if mutation == "clearance":
        return mutate_clearance(
            board_path, out_path, params["ref"], tuple(params["position_mm"]), seed
        )
    if mutation == "courtyard":
        return mutate_courtyard(
            board_path, out_path, params["ref"], tuple(params["position_mm"]), seed
        )
    if mutation == "hole-to-hole":
        return mutate_hole_to_hole(
            board_path, out_path, params["ref"], tuple(params["position_mm"]), seed
        )
    if mutation == "missing-courtyard":
        return mutate_missing_courtyard(board_path, out_path, params["ref"], seed)
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

    if args.mutation in ("off-board", "creepage", "clearance", "courtyard", "hole-to-hole"):
        if args.position is None:
            parser.error(f"--mutation {args.mutation} requires --position X Y")
        params: dict[str, Any] = {"ref": args.ref, "position_mm": list(args.position)}
    elif args.mutation == "missing-courtyard":
        params = {"ref": args.ref}
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
