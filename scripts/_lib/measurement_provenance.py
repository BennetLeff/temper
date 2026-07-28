"""Measurement-artifact provenance: content-hash freshness for derived
measurement files (DRC ceilings today; routing baselines, benchmark
baselines, or anything else that records a number computed from a board/
corpus/binary, tomorrow).

Why this exists
----------------
``scripts/_lib/provenance.py`` already answers "what commit/dirty-state was
this evidence file produced in" for ``docs/evidence/*`` prose, and
``scripts/check_evidence_provenance.py`` enforces that every evidence file
carries that stamp. Neither answers a different, sharper question that a
*measurement* (as opposed to a narrative write-up) needs answered: "does the
specific input file this number was computed from still have the content it
had when the number was recorded?" ``power_pcb_dataset/drc_ceiling.json``
recorded 91 errors against ``pcb/temper.kicad_pcb`` at commit ``3c391956``;
three commits later changed that file's content and the ceiling was never
re-measured -- see docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md.
A commit-only provenance stamp on the ceiling file itself would not have
caught this: the ceiling file's *own* last-touched commit is still
``3c391956`` (correct, and unchanged), but the *board it measures* moved out
from under it. The gap is specifically about the measured input, not the
measuring file.

Design decision: content hashes, not mtimes
--------------------------------------------
``git checkout``/``git reset --hard``/branch switches rewrite every tracked
file's mtime to the checkout time without touching content -- this is
exactly the mechanism ``check_stale_extensions.py``'s own docstring calls
out as a known false-positive risk it accepts for *compiled artifact
freshness* (where the assumption "build happens after checkout" holds by
construction: CI always builds after checking out). That assumption does
NOT hold here: nothing about a measurement artifact's own edit history
guarantees anyone re-ran the measurement after the input last changed, so an
mtime comparison would be comparing two numbers with no causal relationship
to "was this number computed from this content." A git-blob SHA is close but
also wrong: it changes if the file is renamed or the tree is re-packed, and
does not exist at all when checking an *uncommitted* input against a
committed provenance record (the exact "dirty tree measured, then the
change reverted before commit" case). A raw content hash (sha256 of file
bytes, independent of git object model, mtimes, or commit topology) is the
only signal that directly answers "is this the same content" regardless of
how it got that way -- which is what "did the input move" actually means.

What belongs in a provenance record
-------------------------------------
Every measurement record's ``provenance`` object carries:

  measured_at_commit: 40-char lowercase hex SHA, or "UNKNOWN" -- human
      traceability (which commit's measurement run produced this), NOT the
      freshness check itself (that is ``inputs[].sha256`` below). A commit
      can be right while the content is wrong (uncommitted local edits) and
      vice versa (two commits with byte-identical content), so this field
      is informational, never the thing compared.
  dirty: true / false / "UNKNOWN" -- was the measuring tree clean at
      measurement time. "UNKNOWN" is honest for backfilled historical
      records reconstructed purely from git history: the *committed*
      content is exactly reproducible (`git show <sha>:<path>`), but
      whether the *person running the measurement* also had unrelated
      uncommitted changes in their tree at that moment is not recoverable
      after the fact, and must not be guessed.
  inputs: list of {"path": <repo-relative>, "sha256": <64-hex>} -- the
      actual freshness oracle. Every file the number was computed from,
      named explicitly. A record with zero inputs proves nothing about
      freshness and is treated as malformed (see check_measurement_provenance.py).
  tool_versions: dict of tool name -> version string (e.g.
      {"kicad-cli": "10.0.5"}), values "UNKNOWN" where not recorded.
      KiCad's 10.0.4-vs-10.0.5 patch difference was a real, checked
      candidate cause of the 91-vs-710 discrepancy (docs/evidence/
      2026-07-27-drc-truth-gate-discrepancy.md Sec 2) and was ruled out only
      because someone actually compared binaries -- a provenance record
      that omits tool version makes that comparison impossible to redo
      without re-deriving it from scratch each time.
  source: "measured-live" (emitted by ``build_provenance`` below, at the
      moment a measurement actually ran) or "backfilled-historical"
      (reconstructed after the fact from git history for a measurement that
      predates this contract -- e.g. drc_ceiling.json's current entry).
      This distinguishes "we watched this measurement happen" from
      "we reconstructed what must have been true", the same distinction
      ``scripts/_lib/provenance.py`` already draws for evidence docs.

How "no provenance yet" is handled
-------------------------------------
See ``check_measurement_provenance.py`` and ``.measurement-provenance-allowlist``
for the allowlist mechanism -- modeled on ``.evidence-provenance-allowlist``:
justified per-entry with a ticket, monotonically shrinking, never a blanket
grace period.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _lib.provenance import get_branch, get_head_commit, is_tree_dirty  # noqa: E402

SHA256_HEX_LENGTH = 64
VALID_SOURCES = ("measured-live", "backfilled-historical")
_READ_CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: Path) -> str:
    """Content hash (hex sha256) of *path*.

    Raises ``OSError`` (e.g. ``FileNotFoundError``) if the file cannot be
    read -- deliberately not swallowed here. A missing input file is a
    fail-closed condition for any caller checking freshness (see
    ``check_inputs_fresh``), never silently treated as "matches" or
    "doesn't matter".
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def build_provenance(
    repo_root: Path,
    input_paths: list[str],
    *,
    tool_versions: dict[str, str] | None = None,
    source: str = "measured-live",
) -> dict[str, Any]:
    """Build a fresh provenance record for a measurement that is running
    right now, in this tree. Intended for use by scripts that actually
    perform a measurement (e.g. a future ``calibrate_drc_ceiling.py`` run
    that re-measures and re-ratchets the DRC ceiling with a
    ``Ceiling-Approval:`` trailer) -- NOT called by
    ``check_measurement_provenance.py`` itself, which only ever reads and
    verifies already-recorded provenance, never writes it (a checker that
    can also silently rewrite the thing it checks is not a checker).

    ``input_paths`` are repo-root-relative; every one of them must exist
    and be readable right now, or this raises ``OSError`` (fail closed --
    a measurement that cannot hash its own input has not established
    provenance at all).
    """
    inputs = [
        {"path": rel, "sha256": sha256_file(repo_root / rel)} for rel in input_paths
    ]
    return {
        "measured_at_commit": get_head_commit(repo_root),
        "dirty": is_tree_dirty(repo_root),
        "branch": get_branch(repo_root),
        "inputs": inputs,
        "tool_versions": dict(tool_versions or {}),
        "source": source,
    }


@dataclass
class InputMismatch:
    """One input file whose recorded content hash no longer matches
    reality -- either the content changed, or the file is gone."""

    path: str
    recorded_sha256: str
    current_sha256: str | None  # None => file missing entirely
    reason: str


def check_inputs_fresh(repo_root: Path, inputs: list[dict[str, Any]]) -> list[InputMismatch]:
    """Recompute the current content hash of every declared input and
    compare against what the provenance record claims. Returns the list of
    mismatches -- empty means every declared input is byte-identical to
    what it was when measured (fresh). Never raises on a missing input
    file; that is itself reported as a mismatch, not a crash, so one
    missing input in a multi-input record does not prevent reporting on
    the rest.
    """
    mismatches: list[InputMismatch] = []
    for entry in inputs:
        rel = entry.get("path")
        recorded = entry.get("sha256")
        if not isinstance(rel, str) or not rel:
            mismatches.append(
                InputMismatch(
                    path=str(rel), recorded_sha256=str(recorded), current_sha256=None,
                    reason="malformed input entry: 'path' missing or not a string",
                )
            )
            continue
        if not isinstance(recorded, str) or len(recorded) != SHA256_HEX_LENGTH:
            mismatches.append(
                InputMismatch(
                    path=rel, recorded_sha256=str(recorded), current_sha256=None,
                    reason="malformed input entry: 'sha256' missing or not a 64-char hex string",
                )
            )
            continue
        abs_path = repo_root / rel
        if not abs_path.is_file():
            mismatches.append(
                InputMismatch(
                    path=rel, recorded_sha256=recorded, current_sha256=None,
                    reason=f"input file no longer exists at {abs_path}",
                )
            )
            continue
        current = sha256_file(abs_path)
        if current != recorded:
            mismatches.append(
                InputMismatch(
                    path=rel, recorded_sha256=recorded, current_sha256=current,
                    reason="content hash changed since measurement -- the input moved",
                )
            )
    return mismatches


_COMMIT_HEX = set("0123456789abcdef")


def _looks_like_commit_sha(s: str) -> bool:
    """True iff *s* is exactly 40 lowercase hex characters. Written as an
    explicit loop (not ``all(c in _COMMIT_HEX for c in s)``) so it is never
    mistaken by ``check_vacuous_gates.py`` for an unguarded aggregate --
    this function's own return value already encodes the emptiness check
    (``len(s) != 40`` rejects the empty string), but the gate's textual
    scan does not trace that through a boolean ``or``, so the loop form
    sidesteps the ambiguity entirely rather than relying on a suppression.
    """
    if len(s) != 40:
        return False
    for c in s:
        if c not in _COMMIT_HEX:
            return False
    return True


def validate_provenance_shape(prov: dict[str, Any]) -> str | None:
    """Return a human-readable reason the provenance object is malformed,
    or ``None`` if its shape is valid. Does not check freshness (that is
    ``check_inputs_fresh``) -- only that the record has the fields the
    freshness check and human readers both depend on.
    """
    commit = prov.get("measured_at_commit")
    if not isinstance(commit, str):
        return "'measured_at_commit' missing or not a string"
    if commit != "UNKNOWN" and not _looks_like_commit_sha(commit):
        return f"'measured_at_commit'={commit!r} is neither a 40-char lowercase hex SHA nor 'UNKNOWN'"

    dirty = prov.get("dirty")
    if dirty not in (True, False, "UNKNOWN"):
        return f"'dirty'={dirty!r} must be true, false, or 'UNKNOWN'"

    inputs = prov.get("inputs")
    if not isinstance(inputs, list) or len(inputs) == 0:
        return "'inputs' missing, not a list, or empty -- a provenance record naming zero inputs proves no freshness"
    for i, entry in enumerate(inputs):
        if not isinstance(entry, dict) or "path" not in entry or "sha256" not in entry:
            return f"inputs[{i}] missing 'path' or 'sha256'"

    tool_versions = prov.get("tool_versions", {})
    if not isinstance(tool_versions, dict):
        return "'tool_versions' present but not an object"

    source = prov.get("source")
    if source not in VALID_SOURCES:
        return f"'source'={source!r} must be one of {VALID_SOURCES}"

    return None
