#!/usr/bin/env python3
"""Measurement-provenance CI gate: fail closed when a measurement artifact's
recorded inputs have moved since it was measured.

Motivating incident
--------------------
``power_pcb_dataset/drc_ceiling.json`` recorded 91 errors for
``pcb/temper.kicad_pcb``. That number was correct -- for the board as it
existed at commit ``3c391956``. Three commits later
(``c6b1b463``, ``556ccf4f`` -- the first committed route, ``65bd0159``)
changed ``pcb/temper.kicad_pcb`` substantially; the ceiling file was never
re-measured and stayed byte-identical throughout. The real error count on
the board those three commits produced is ~710, roughly 8x the recorded
figure -- see docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md and
docs/evidence/2026-07-28-measurement-provenance.md. Nothing in the ceiling
file said which board it was measuring, so nothing could notice the board
underneath it had changed. This gate is that missing check, generalized:
any measurement artifact that declares which input files it was computed
from can be verified this way, not just the DRC ceiling.

This is a narrower, sharper claim than ``check_evidence_provenance.py``
enforces for ``docs/evidence/*``. That gate asks "does this file say what
commit it was written at" (a *commit* stamp on the *writing* file). This
gate asks "does the specific input file a number was computed *from* still
have the content it had when that number was computed" (a *content hash* on
the *measured* file) -- see ``scripts/_lib/measurement_provenance.py``'s
module docstring for why a commit-only stamp on the ceiling file itself
would NOT have caught this incident (the ceiling file's own last-edit
commit is correct and unchanged; the board it measures is what moved).

Design decision: an explicit artifact registry, not a repo-wide scan
------------------------------------------------------------------------
``MEASURED_ARTIFACTS`` below is a short, explicit, auditable list -- not a
scan of the whole tree for any JSON file containing a ``"provenance"`` key.
Measurement artifacts of this kind (a ceiling, a baseline, a benchmark
record) are few, named, and added deliberately; an unbounded content scan
would either sweep in unrelated files that happen to use the word
"provenance" for something else, or silently miss artifacts that don't
match whatever glob was guessed. This mirrors ``check_domain_partition.py``
hardcoding ``DEFAULT_NETLIST``/``DEFAULT_MANIFEST`` rather than searching
for "the netlist" and "the manifest": a small number of well-known files,
named explicitly, is the correct scope here. A future measurement artifact
(a routing baseline, a benchmark record) adopts this contract by adding
its own ``provenance`` object (schema in ``measurement_provenance.py``) and
adding its path to this list -- both steps are required; a provenance
block nobody points this gate at is exactly as unchecked as no provenance
at all.

Design decision: generic record extraction within a registered artifact
------------------------------------------------------------------------
An artifact may hold one measurement record (a top-level ``"provenance"``
key) or many (a list of records, each with its own ``"provenance"`` key --
``drc_ceiling.json``'s ``"boards"`` array is exactly this shape, keyed by
``board_id``). ``extract_records`` walks both shapes generically so a new
artifact with either layout is supported without bespoke per-artifact
parsing code.

Design decision: "no provenance yet" needs an allowlist, not a free pass
------------------------------------------------------------------------
Most measurement artifacts in this repo predate this contract and have no
provenance block at all. Modeled directly on
``.evidence-provenance-allowlist``/``check_evidence_provenance.py``: a
record with no ``"provenance"`` key is only tolerated if
``<artifact-relpath>#<record-id>`` is listed in
``.measurement-provenance-allowlist`` with a ``# TODO: temper-xxx`` ticket.
Entries may only be removed once the record gains real provenance or the
record/artifact is deleted -- enforced by ``--check-shrink`` against
``origin/main``, reusing ``scripts/_lib/gate_allowlist.py`` (the same
shared infrastructure ``check_physics_provenance.py`` and
``check_evidence_provenance.py`` already use). A record whose
``"provenance"`` key IS present but malformed is never allowlist-eligible
-- "unknown" and "wrong" are different failure modes, and only the first
is what the allowlist exists to tolerate.

Design decision: STALE is a GATE ERROR, not a violation
------------------------------------------------------------------------
This gate never recomputes the underlying measurement itself (it does not
re-run DRC) -- it only checks whether the declared inputs still match what
was hashed at measurement time. There is therefore no "violation" class
here distinct from "the gate could not certify this artifact is
trustworthy" -- exactly the netlist-freshness precedent in
``check_domain_partition.py``, ``check_copper_net_consistency.py``, and
``check_rust_drc_presence.py``: a stale netlist there is treated as
``GATE RESULT: ERROR -- not PASSED, not a violation``, one of several
distinct reasons bucketed under a single non-zero exit code, each named
individually in the failure output. This gate generalizes that exact
semantic: STALE inputs, missing/malformed provenance, a malformed artifact,
and a vacuous (zero-record) scan are all distinct, individually-labeled
reasons that collapse to the same ``EXIT_GATE_ERROR`` -- there is
deliberately no separate "violation" exit code, because this gate does not
independently verify correctness, only freshness of what's already
recorded.

Design decision: ``measured_at_commit`` is advisory, but a dangling one is
a hard problem, not a shrug
------------------------------------------------------------------------
Incident (2026-08-07): ``drc_ceiling.json``'s ``measured_at_commit`` was
``3410ee4e1fe8c3a5cce13b9262585016a06fce8d`` -- a commit that does not
exist anywhere in this repository's object store (``git cat-file -t``
fails on it). Root cause, confirmed by ``git log -p`` and the GitHub API:
PR #602 (branch ``feat/k3-swap-and-board-write``) recorded that SHA as the
"Run-B re-solve" commit mid-development; the branch was repeatedly rebased
before merge (its own commit trailers say "re-point wave-2 provenance to
post-rebase HEAD" twice), and squash/rebase machinery orphaned the original
object before the PR landed as merge commit ``de59c0458``. This is exactly
the class of history rewriting ``check_evidence_provenance.py``'s own
module docstring already names ("a squash-merged PR whose branch was
deleted leaves its pre-squash commits unreachable, and eventually ``git
gc`` prunes them") -- that gate solved this for ``docs/evidence/*`` before
this incident; this gate had not adopted the same fix for measurement
artifacts, which is precisely how the dangling SHA went undetected.

Neither existing check actually verified resolvability. ``validate_provenance_shape``
here only checks *shape* (40 lowercase hex characters, or ``UNKNOWN``) --
a syntactically well-formed but entirely fabricated or orphaned SHA passes
it outright. ``DrcRatchet.validate_raise_evidence`` (``drc_ratchet.py``,
the R27 raise-approval evidence contract) does the same: its check is
``_SHA256_HEX_RE.fullmatch(commit)``, a regex, despite the adjacent error
message claiming the commit "does not resolve to a commit" -- it never
calls git at all. And that check only runs when a ceiling *raise* is being
approved; a re-measurement PR that does not raise any ceiling value (as
#602's actually was not, for the aggregate at least) never reaches it. So
the dangling anchor could land on any PR that merely updates ``provenance``
-- not just a raise -- and nothing would notice until someone tried to
resolve it months later, which is exactly what happened.

The fix: this gate now batch-verifies every non-``UNKNOWN``
``measured_at_commit`` across every registered artifact actually resolves
to a real commit object, via ``check_evidence_provenance.verify_commits_exist``
(``git cat-file --batch-check``) -- reused rather than reimplemented, since
it already carries the shallow-clone guard (a shallow clone cannot be
distinguished from "every historical SHA is fake") and the "one subprocess
for the whole scan" batching this gate's own docstring already commits to
for input hashing. An unresolvable commit is a hard ``problems`` entry
(never allowlist-eligible -- "unknown" and "wrong" are different failure
modes, same rule ``validate_provenance_shape`` already applies to a
malformed ``provenance`` object), even when the record's content hash is
still fresh: a dangling SHA gives none of the human traceability an
explicit commit promises while looking exactly like it does, which is
worse than an honest ``UNKNOWN``.

This does NOT change what freshness is keyed on. The content hash
(``inputs[].sha256``) was already, and remains, the sole freshness oracle
-- see "Design decision: content hashes, not mtimes" in
``measurement_provenance.py``. Two alternatives were considered and
rejected: (1) re-anchoring freshness itself on the commit SHA (e.g.
comparing against ``git show <sha>:<path>``) was rejected because it is
the exact fragility this incident demonstrates -- a commit SHA is not
stable under history rewriting, while file content is; and (2) silently
downgrading an unresolvable commit to ``UNKNOWN`` and continuing was
rejected because that would erase the record's dishonesty instead of
surfacing it -- a record that claims a specific commit and is wrong about
it is a worse failure than one that admits it doesn't know, and the two
must not collapse to the same outcome. Making the content hash the
explicit, sole, primary identity and the commit SHA an explicitly
*verified* advisory field is therefore the shape of the fix, not a new
freshness mechanism.

Design decision: ``dirty: true`` is now also a hard problem, not just a
raise-time requirement
------------------------------------------------------------------------
Before this fix, ``dirty: true`` (or any non-``false`` value) was only
rejected by ``DrcRatchet.validate_raise_evidence`` for a ceiling *raise*.
A re-measurement that held or lowered every ceiling value -- most of them,
by volume -- could carry ``dirty: true`` and this gate would still call it
fresh, as long as the named input's content hash matched. That is too
narrow a promise: ``dirty: true`` means the tree had some other uncommitted
change when the measurement ran, and that unnamed change (a locally-edited
DRU file, an uncommitted script tweak) could have influenced the
measurement without ever appearing in ``inputs`` -- the content-hash check
cannot see what it was never told to hash. This gate now treats
``dirty: true`` on any provenanced record as a ``problems`` entry,
unconditionally, closing the same "only checked on a raise" gap that let
the dangling commit through undetected on a non-raising PR.

Do NOT re-measure or update any ceiling value
------------------------------------------------------------------------
This gate is read-only with respect to every artifact it checks. It never
writes to ``drc_ceiling.json`` or any other registered artifact. Adopting
this contract for ``drc_ceiling.json`` added a ``provenance`` object to its
existing board entry with no change to ``error_ceiling``,
``warning_ceiling``, or ``violations_by_type`` -- verified by ``git diff``
touching only the added keys (see docs/evidence/2026-07-28-measurement-provenance.md).

Exit codes
----------
  0 - OK: every registered artifact parsed, every record either has fresh,
      trustworthy provenance or is validly allowlisted as not-yet-provenanced.
  5 - GATE ERROR: any of -- STALE input(s) on a provenanced record,
      missing/malformed provenance on an unallowlisted record, a malformed
      provenance object, a ``measured_at_commit`` that does not resolve to
      a real commit object, ``dirty: true``, a missing/unparseable artifact
      file, zero registered artifacts, zero provenance-bearing records
      found across every registered artifact (vacuous scan -- never folded
      into "0 violations", see docs/METHODOLOGY.md Sec 4/5), or the commit-
      resolvability check itself being untrustworthy (git unavailable, or
      a shallow clone -- see ``verify_commits_exist``).

Usage
-----
  uv run python scripts/check_measurement_provenance.py
  uv run python scripts/check_measurement_provenance.py --check-shrink
  uv run python scripts/check_measurement_provenance.py --init   # populate allowlist
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.gate_allowlist import (  # noqa: E402
    TICKET_PATTERN,
    check_shrink_mode as _check_shrink_mode,
    git_show_main_allowlist as _git_show_main_allowlist,
    load_allowlist as _load_allowlist,
)
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.measurement_provenance import (  # noqa: E402
    check_inputs_fresh,
    validate_provenance_shape,
)
from _lib.repo import find_repo_root  # noqa: E402

# check_evidence_provenance is a sibling script (scripts/ is already on
# sys.path via the insert above, so this is a plain sibling import, not a
# package dependency) -- verify_commits_exist is reused, not reimplemented:
# it already solved "does this claimed commit actually resolve" for
# docs/evidence/* (see module docstring, "Design decision: measured_at_commit
# is advisory, but a dangling one is a hard problem, not a shrug"), carries
# its own shallow-clone guard, and batches every SHA into one `git cat-file
# --batch-check` subprocess -- the same batching discipline this gate
# already uses for input-hash freshness.
from check_evidence_provenance import verify_commits_exist  # noqa: E402

REPO_ROOT = find_repo_root()

# See module docstring "Design decision: an explicit artifact registry".
# A future routing baseline / benchmark baseline adopts this contract by
# adding a "provenance" object (schema: measurement_provenance.py) to its
# own JSON (or YAML -- see load_records) and adding its path here.
MEASURED_ARTIFACTS: list[Path] = [
    REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json",
    # The second anchored record (2026-08-07 backlog paydown): board-vs-source
    # reconciliation for the legacy placement config, consumed by
    # temper_placer.cli via reference_aliases.load_reference_alias_manifest.
    # It carried a resolvable measured_at_commit (authority.measured_at_commit)
    # but no content-hash inputs at all and was not covered by any gate --
    # exactly the "advisory commit, no verified freshness oracle" gap this
    # script's own module docstring exists to close.
    REPO_ROOT / "packages" / "temper-placer" / "configs" / "temper_constraints.references.yaml",
]

ALLOWLIST_DEFAULT = REPO_ROOT / ".measurement-provenance-allowlist"

EXIT_OK = 0
EXIT_GATE_ERROR = 5

_MISSING = object()  # sentinel: record has no "provenance" key at all


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass
class Record:
    artifact: Path
    record_id: str
    provenance: Any  # dict (present), or _MISSING, or a non-dict garbage value

    @property
    def key(self) -> str:
        """Allowlist/report key: ``<artifact-relpath>#<record-id>``.

        Falls back to the bare filename when *artifact* is not under
        ``REPO_ROOT`` (e.g. a tmp_path fixture in tests exercising
        ``evaluate()`` directly against a synthetic artifact) -- the real
        gate always runs with paths under ``REPO_ROOT``, so this fallback
        is exercised only by tests, never in production use.
        """
        try:
            rel = self.artifact.relative_to(REPO_ROOT)
        except ValueError:
            rel = self.artifact.name
        return f"{rel}#{self.record_id}"


def extract_records(data: object) -> list[tuple[str, Any]]:
    """Return (record_id, provenance_value) pairs found in *data*.

    Generic across two shapes (see module docstring):
      - a top-level ``"provenance"`` key -> one record, id ``"<root>"``.
      - any top-level list-valued key whose items are dicts -> one record
        per dict item, id ``"<key>.<board_id-or-id-or-index>"``, using that
        item's own ``"provenance"`` key.
    ``provenance`` is ``_MISSING`` if the key is entirely absent (allowlist
    territory), or whatever raw value is present otherwise (validated by
    the caller -- a non-dict value here is always malformed, never
    allowlist-eligible).
    """
    if not isinstance(data, dict):
        return []

    records: list[tuple[str, Any]] = []
    if "provenance" in data:
        records.append(("<root>", data.get("provenance", _MISSING)))

    for key, value in data.items():
        if key == "provenance" or not isinstance(value, list):
            continue
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                continue
            record_id = item.get("board_id") or item.get("id") or str(i)
            records.append((f"{key}.{record_id}", item.get("provenance", _MISSING)))

    return records


def load_records(artifact: Path) -> list[Record]:
    if not artifact.is_file():
        raise GateError(f"registered measurement artifact not found: {artifact}")
    # Dispatch on suffix: most registered artifacts are JSON (drc_ceiling.json),
    # but a measurement record legitimately lives in YAML too (e.g.
    # temper_constraints.references.yaml, hand-authored and consumed via
    # yaml.safe_load by temper_placer.cli) -- extract_records() below is
    # already format-agnostic (it walks a parsed dict/list structure, not
    # JSON syntax), so supporting both is a loader-only change, not a second
    # parallel checker.
    is_yaml = artifact.suffix in (".yaml", ".yml")
    try:
        if is_yaml:
            data = yaml.safe_load(artifact.read_text())
        else:
            data = json.loads(artifact.read_text())
    except json.JSONDecodeError as exc:
        raise GateError(f"{artifact}: malformed JSON, cannot verify provenance: {exc}") from exc
    except yaml.YAMLError as exc:
        raise GateError(f"{artifact}: malformed YAML, cannot verify provenance: {exc}") from exc
    return [Record(artifact, rid, prov) for rid, prov in extract_records(data)]


def load_allowlist(path: Path) -> dict[str, str]:
    """Parse .measurement-provenance-allowlist into {key: ticket_comment}."""
    entries: dict[str, str] = {}
    for line in _load_allowlist(path):
        if "#" in line:
            key_part, comment = line.split("#", 1)
            key_part = key_part.strip()
        else:
            key_part, comment = line.strip(), ""
        if key_part:
            entries[key_part] = comment.strip()
    return entries


@dataclass
class Outcome:
    fresh: list[str] = field(default_factory=list)
    stale: list[tuple[str, list]] = field(default_factory=list)  # (key, [InputMismatch,...])
    allowlisted: list[str] = field(default_factory=list)
    problems: list[tuple[str, str]] = field(default_factory=list)  # (key, reason)


def evaluate(
    repo_root: Path, artifacts: list[Path], allowlist: dict[str, str]
) -> Outcome:
    """Pure evaluation over already-resolved artifact paths -- separated
    from I/O/argv handling so it is directly unit-testable (mirrors
    ``check_stale_extensions.decide_exit_code`` being split from ``main``).
    """
    if not artifacts:
        raise GateError(
            "zero measurement artifacts registered in MEASURED_ARTIFACTS -- "
            "vacuous run, not a clean pass. Either the registry was emptied "
            "by mistake or every measurement artifact was deleted; either "
            "way this must not report success (see docs/METHODOLOGY.md Sec 4/5)."
        )

    outcome = Outcome()
    total_records = 0

    # Pass 1: load every record and settle everything that needs no git
    # I/O -- _MISSING (allowlist lookup), non-dict garbage, and shape
    # validity. This also collects every well-formed, non-UNKNOWN
    # measured_at_commit across every artifact so pass 2 can verify all of
    # them in a single batched git subprocess (mirrors
    # check_evidence_provenance.py's own two-pass structure, for the same
    # reason: never one git invocation per record).
    shape_valid: list[Record] = []
    shas_to_verify: set[str] = set()

    for artifact in artifacts:
        records = load_records(artifact)
        for rec in records:
            total_records += 1
            if rec.provenance is _MISSING:
                if rec.key in allowlist:
                    outcome.allowlisted.append(rec.key)
                else:
                    outcome.problems.append(
                        (
                            rec.key,
                            "no 'provenance' object recorded and not allowlisted -- "
                            f"add real provenance or add '{rec.key}' to "
                            f"{ALLOWLIST_DEFAULT.name} with a # TODO: temper-xxx ticket",
                        )
                    )
                continue
            if not isinstance(rec.provenance, dict):
                outcome.problems.append(
                    (rec.key, f"'provenance' present but not an object: {rec.provenance!r}")
                )
                continue
            shape_err = validate_provenance_shape(rec.provenance)
            if shape_err:
                outcome.problems.append((rec.key, f"malformed provenance: {shape_err}"))
                continue
            shape_valid.append(rec)
            commit = rec.provenance["measured_at_commit"]
            if commit != "UNKNOWN":
                shas_to_verify.add(commit)

    if total_records == 0:
        raise GateError(
            f"zero provenance-bearing records found across {len(artifacts)} "
            "registered artifact(s) -- 'no records therefore no violations' is "
            "the vacuous-pass shape this project's gates have died on before "
            "(docs/METHODOLOGY.md Sec 4/5); failing closed instead."
        )

    # Pass 2: batch-verify every claimed measured_at_commit resolves to a
    # real commit object -- one `git cat-file --batch-check` subprocess for
    # the whole scan, reusing check_evidence_provenance.verify_commits_exist
    # rather than reimplementing it (see module docstring, "Design decision:
    # measured_at_commit is advisory, but a dangling one is a hard problem").
    # A RuntimeError here (git missing, or a shallow clone where "does not
    # resolve" would be true of nearly every legitimate historical SHA) is a
    # GATE ERROR, not a silent skip: a check that cannot verify its own
    # claim must not report a meaningful verdict.
    try:
        resolved_commits = verify_commits_exist(shas_to_verify, repo_root)
    except RuntimeError as exc:
        raise GateError(f"cannot verify measured_at_commit provenance: {exc}")

    # Pass 3: for every shape-valid record, check the two integrity
    # dimensions that are orthogonal to (and checked before) content-hash
    # freshness: does the claimed commit anchor actually exist, and was the
    # tree clean when the measurement ran. Both are hard 'problems' --
    # never allowlist-eligible, exactly like a malformed provenance object
    # -- because a record that actively misrepresents its own measurement
    # conditions is a worse failure than one that honestly doesn't know.
    # Freshness (the content-hash check) remains the sole and unchanged
    # freshness oracle; it is not run at all when either integrity check
    # fails, so a record cannot be simultaneously STALE and a 'problem'.
    for rec in shape_valid:
        prov = rec.provenance
        integrity_problems: list[str] = []

        commit = prov["measured_at_commit"]
        if commit != "UNKNOWN" and not resolved_commits.get(commit, False):
            integrity_problems.append(
                f"measured_at_commit={commit!r} does not resolve to a commit object "
                "in this repository (git cat-file confirms no such object exists) -- "
                "whether mistyped, fabricated, or naming a commit that once existed "
                "on a branch that was squash-merged or rebased away and is no longer "
                "reachable, a dangling commit gives none of the traceability an "
                "explicit SHA promises while looking like it does; cite a commit "
                "that persists (this change's own merge commit into main, not a "
                "pre-squash/pre-rebase branch commit) or, if it is genuinely gone, "
                "record 'UNKNOWN' instead"
            )

        if prov.get("dirty") is True:
            integrity_problems.append(
                "dirty=true: measured in an unclean working tree -- an uncommitted, "
                "unnamed change could have influenced this measurement without ever "
                "appearing in 'inputs' (the content-hash check cannot see what it "
                "was never told to hash); re-measure in a clean tree"
            )

        if integrity_problems:
            outcome.problems.append((rec.key, "; ".join(integrity_problems)))
            continue

        mismatches = check_inputs_fresh(repo_root, prov["inputs"])
        if mismatches:
            outcome.stale.append((rec.key, mismatches))
        else:
            outcome.fresh.append(rec.key)

    # Every allowlist entry must carry a ticket, unconditionally (not just
    # under --check-shrink) -- mirrors check_evidence_provenance.py exactly,
    # so the allowlist cannot silently grow via an untracked addition.
    for key, comment in sorted(allowlist.items()):
        if not TICKET_PATTERN.search(comment):
            outcome.problems.append(
                (key, f"allowlist entry missing ticket reference (got: {comment!r})")
            )

    return outcome


def check_shrink_mode(current_allowlist: dict[str, str]) -> int:
    """Monotonic-shrink check against origin/main -- mirrors
    check_evidence_provenance.py's --check-shrink exactly. Soft-skips
    (returns 0) only when origin/main itself is unavailable (shallow
    clone); does not relax the primary gate above.
    """
    try:
        main_lines = _git_show_main_allowlist(ALLOWLIST_DEFAULT.name, REPO_ROOT)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"WARNING: origin/main allowlist unavailable, skipping shrink check: {exc}")
        return 0

    current_entries = [f"{k}  # {v}" for k, v in sorted(current_allowlist.items())]
    removed, added = _check_shrink_mode(main_lines, current_entries)

    failures = 0
    for entry in sorted(added):
        ticket = current_allowlist.get(entry, "")
        if not TICKET_PATTERN.search(ticket):
            print(f"FAIL: allowlist entry added without ticket reference: {entry}")
            failures += 1

    for entry in sorted(removed):
        # A removed entry is only valid if its record now has real,
        # fresh-or-stale (i.e. present-and-parseable) provenance, or the
        # underlying artifact/record no longer exists. Re-derive this from
        # the artifact set on disk right now.
        artifact_rel, _, record_id = entry.partition("#")
        artifact_path = REPO_ROOT / artifact_rel
        if not artifact_path.is_file():
            continue  # artifact deleted entirely -- valid removal
        try:
            records = {r.record_id: r for r in load_records(artifact_path)}
        except GateError:
            continue
        rec = records.get(record_id)
        if rec is None or rec.provenance is not _MISSING:
            continue  # record deleted, or now has a provenance object -- valid removal
        print(f"FAIL: allowlist entry removed but {entry} still has no provenance object")
        failures += 1

    if not failures:
        print("Measurement-provenance allowlist monotonic-shrink check passed")
    return failures


def _init_allowlist(artifacts: list[Path]) -> None:
    to_add: list[str] = []
    for artifact in artifacts:
        for rec in load_records(artifact):
            if rec.provenance is _MISSING:
                to_add.append(rec.key)
    lines = [
        "# Measurement-provenance allowlist -- monotonically-shrinking baseline",
        "# Format: <artifact-relpath>#<record-id>  # TODO: temper-xxx",
        "#",
        "# An entry represents a measurement record (see",
        "# scripts/_lib/measurement_provenance.py) with no 'provenance' object",
        "# yet -- it predates this contract, or its measurement history could",
        "# not be reconstructed without fabricating input hashes. Entries may",
        "# only be removed once the record gains a real 'provenance' object or",
        "# the record/artifact is deleted. Entries may only be added with a",
        "# # TODO: temper-xxx ticket reference.",
        "",
    ]
    for name in sorted(to_add):
        lines.append(f"{name}  # TODO: temper-xxx")
    lines.append("")
    ALLOWLIST_DEFAULT.write_text("\n".join(lines))
    print(f"Allowlist populated with {len(to_add)} entries: {ALLOWLIST_DEFAULT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST_DEFAULT)
    parser.add_argument(
        "--init", action="store_true", help="Populate the allowlist with every currently-unprovenanced record"
    )
    parser.add_argument(
        "--check-shrink", action="store_true", help="Enforce monotonic-shrink of the allowlist against origin/main"
    )
    args = parser.parse_args()

    if args.init:
        _init_allowlist(MEASURED_ARTIFACTS)
        return EXIT_OK

    allowlist = load_allowlist(args.allowlist)
    gh = get_github_summary_path()

    try:
        outcome = evaluate(REPO_ROOT, MEASURED_ARTIFACTS, allowlist)
    except GateError as exc:
        print("=== MEASUREMENT-PROVENANCE GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print("GATE RESULT: ERROR -- not PASSED, not a violation. 0 record(s) checked.", file=sys.stderr)
        if gh:
            with open(gh, "a") as f:
                f.write("### Measurement-Provenance Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    total = len(outcome.fresh) + len(outcome.stale) + len(outcome.allowlisted) + len(outcome.problems)
    print(
        f"Measurement-provenance gate -- {len(MEASURED_ARTIFACTS)} artifact(s) registered, "
        f"{total} record(s) found across them (the denominator is never a subset)."
    )
    print(
        f"  fresh={len(outcome.fresh)} stale={len(outcome.stale)} "
        f"allowlisted-unprovenanced={len(outcome.allowlisted)} problem(s)={len(outcome.problems)}"
    )
    for key in outcome.fresh:
        print(f"  [OK]    {key}: every declared input matches its recorded content hash")
    for key, mismatches in outcome.stale:
        print(f"  [STALE] {key}: {len(mismatches)} input(s) moved since measurement")
        for m in mismatches:
            print(f"          {m.path}: {m.reason}")
    for key in outcome.allowlisted:
        print(f"  [????]  {key}: allowlisted, no provenance recorded yet ({allowlist.get(key, '')})")
    for key, reason in outcome.problems:
        print(f"  [ERROR] {key}: {reason}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Measurement-Provenance Gate\n")
            f.write(
                f"- Artifacts registered: {len(MEASURED_ARTIFACTS)}\n"
                f"- Records found: {total}\n"
                f"- Fresh: {len(outcome.fresh)}\n"
                f"- Stale: {len(outcome.stale)}\n"
                f"- Allowlisted (unprovenanced): {len(outcome.allowlisted)}\n"
                f"- Problems: {len(outcome.problems)}\n"
            )

    exit_code = EXIT_OK
    if outcome.stale or outcome.problems:
        exit_code = EXIT_GATE_ERROR

    if args.check_shrink:
        shrink_failures = check_shrink_mode(allowlist)
        if shrink_failures:
            exit_code = EXIT_GATE_ERROR

    if exit_code == EXIT_GATE_ERROR:
        print(
            "\nGATE RESULT: ERROR -- not PASSED, not a violation. "
            f"{len(outcome.stale)} stale record(s), {len(outcome.problems)} problem(s).",
            file=sys.stderr,
        )
    else:
        print(f"\nPASSED -- {len(outcome.fresh)}/{total} record(s) fresh, {len(outcome.allowlisted)} allowlisted.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
