"""R27 ceiling-raise governance: enumerate raises, validate their evidence,
detect an unapproved raise.

Split out of ``drc_ratchet.py`` (LOC cap, R3): ``find_ceiling_raises``,
``validate_raise_evidence`` and ``detect_ceiling_raise`` are pure functions
of the two ceiling dicts they compare (plus ``repo_root`` for evidence
verification) -- none of them read or write ``DrcRatchet`` instance state
(``self.entries``, ``self.backend``, ...). That is what makes this an
honest seam rather than an arbitrary cut: the class-shaped part of
``DrcRatchet`` (loading the ceiling file, running DRC, checking a board
against its ceiling) stays in ``drc_ratchet.py``; the free-function-shaped
R27 governance layer (comparing two ceiling snapshots) moves here.

``DrcRatchet.find_ceiling_raises``/``validate_raise_evidence``/
``detect_ceiling_raise`` remain the public API -- kept as thin delegating
methods in ``drc_ratchet.py`` -- so every external caller
(``scripts/check_drc_ceiling_approval.py``,
``scripts/check_ceiling_raise_evidence_corpus.py``, and the test suites
that call them as ``DrcRatchet(...).find_ceiling_raises(...)``) is
unaffected. Each function here imports drc_ratchet.py's small module-level
helpers (``_marshal_ceiling_int``, ``_verify_commits_exist``,
``_sha256_file``, ``_provenance_sample_count``, ``_SHA256_HEX_RE``,
``DrcRatchetResult``, ``_tdrc``) LOCALLY, inside the function body, rather
than at module scope -- ``drc_ratchet.py`` imports these three functions at
module scope to build its wrapper methods, so a top-level import the other
way would be circular. By the time any function here actually runs (always
after both modules have finished importing), the lazy import resolves
against the already-initialized ``drc_ratchet`` module -- no cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.regression.drc_ratchet import DrcRatchetResult


def find_ceiling_raises(
    old_ceiling: dict, new_ceiling: dict
) -> list[tuple[str, list[str]]]:
    """Return ``(board_id, reasons)`` for every board whose ceiling was
    raised between *old_ceiling* and *new_ceiling*, regardless of
    approval. ``reasons`` is a list of human-readable per-dimension
    deltas ("error_ceiling 1017 -> 1020", "violations_by_type[clearance]
    502 -> 600", ...).

    A raise is any of: the aggregate ``error_ceiling`` increasing, the
    aggregate ``warning_ceiling`` increasing, or any single rule inside
    ``violations_by_type`` (errors) or ``warnings_by_type`` (warnings)
    increasing -- including a rule that didn't exist in the old record
    at all, which is a raise from its implicit ceiling of 0 (the same
    implicit-zero semantics ``_check_board`` enforces at runtime).
    Editing the ceiling *file* to grant a rule more room is exactly as
    much a raise as editing the aggregate number, and must require the
    same ``Ceiling-Approval:`` trailer -- otherwise the per-type
    ceiling could be silently inflated in the JSON itself, sidestepping
    the runtime check entirely. This applies symmetrically to
    ``violations_by_type`` and ``warnings_by_type``: an earlier version
    of this method checked only the warnings side, which meant a
    per-type *error* ceiling (e.g. ``clearance``) could be raised in
    the committed JSON with no trailer and this detector would not
    notice, even though ``_check_board`` enforces that exact ceiling at
    runtime.

    This is the single enumeration of "what raised" for R27's
    measurement-evidence validation -- ``validate_raise_evidence``
    consumes it, so a raise can never pass evidence validation while
    being invisible to this enumeration. Approval detection
    (``detect_ceiling_raise``) runs the SAME raise rules in the Rust
    kernel ``temper_drc_rs.detect_ceiling_raise`` (a verbatim port of
    the pre-migration raise detector, kept bit-identical by the
    differential suite in test_drc_ratchet_rust_differential.py), so a
    raise is visible to both checks across the Python/Rust boundary --
    the R27 "never invisible to one check" property holds.

    Pass 2 (P1-1): every ceiling value is int-VALIDATED here, the same
    fail-loudly ``CeilingMarshalError`` boundary ``detect_ceiling_raise``
    applies before the kernel. A float-valued ceiling in EITHER record
    is a data-model violation and fails loudly instead of being compared
    raw (``100.5 > 100`` detects a raise only in the oracle; the int-only
    kernels cannot represent it, and the old ``int()`` coercion silently
    truncated it -- the #575 fail-open class). R27's
    ``validate_raise_evidence`` inherits this marshal through its use of
    this enumeration.
    """
    from temper_placer.regression.drc_ratchet import _marshal_ceiling_int

    old_boards = {b["board_id"]: b for b in old_ceiling.get("boards", [])}
    new_boards = {b["board_id"]: b for b in new_ceiling.get("boards", [])}

    raises: list[tuple[str, list[str]]] = []
    for board_id, new_entry in new_boards.items():
        old_entry = old_boards.get(board_id)
        if old_entry is None:
            continue

        old_errors = _marshal_ceiling_int(
            old_entry.get("error_ceiling", 0), "error_ceiling", board_id
        )
        new_errors = _marshal_ceiling_int(
            new_entry.get("error_ceiling", 0), "error_ceiling", board_id
        )
        old_warnings = _marshal_ceiling_int(
            old_entry.get("warning_ceiling", 0), "warning_ceiling", board_id
        )
        new_warnings = _marshal_ceiling_int(
            new_entry.get("warning_ceiling", 0), "warning_ceiling", board_id
        )

        reasons: list[str] = []
        if new_errors > old_errors:
            reasons.append(f"error_ceiling {old_errors} -> {new_errors}")
        if new_warnings > old_warnings:
            reasons.append(f"warning_ceiling {old_warnings} -> {new_warnings}")

        old_violations_by_type = old_entry.get("violations_by_type") or {}
        new_violations_by_type = new_entry.get("violations_by_type") or {}
        for rule in sorted(new_violations_by_type):
            new_count = _marshal_ceiling_int(
                new_violations_by_type[rule], f"violations_by_type[{rule}]", board_id
            )
            old_count = _marshal_ceiling_int(
                old_violations_by_type.get(rule, 0),
                f"violations_by_type[{rule}]",
                board_id,
            )
            if new_count > old_count:
                reasons.append(f"violations_by_type[{rule}] {old_count} -> {new_count}")

        old_warnings_by_type = old_entry.get("warnings_by_type") or {}
        new_warnings_by_type = new_entry.get("warnings_by_type") or {}
        for rule in sorted(new_warnings_by_type):
            new_count = _marshal_ceiling_int(
                new_warnings_by_type[rule], f"warnings_by_type[{rule}]", board_id
            )
            old_count = _marshal_ceiling_int(
                old_warnings_by_type.get(rule, 0),
                f"warnings_by_type[{rule}]",
                board_id,
            )
            if new_count > old_count:
                reasons.append(f"warnings_by_type[{rule}] {old_count} -> {new_count}")

        if reasons:
            raises.append((board_id, reasons))

    return raises


def validate_raise_evidence(
    old_ceiling: dict, new_ceiling: dict, repo_root: Path
) -> list[str]:
    """Return every problem with the evidence a ceiling raise claims,
    or ``[]`` when every raise satisfies the contract.

    The R27 monotone contract (docs/plans/2026-08-02-023): a raise
    requires two checkable artifacts in the same PR --

      (a) an **attributed cause**: a NEW non-empty ``_march`` entry in
          the new ceiling file (a key absent from the old ``_march``,
          with a non-empty value naming the component/commit that drove
          the raise -- a prose string, the legacy format, or a structured
          entry ``{"date": ..., "cause": "...", "per_type_delta": {...}}``
          whose ``cause`` field is non-empty, the standardized format
          since 2026-08-19). This file's ``_march`` log is the single
          cause authority; there is deliberately no separate
          trailer-body grammar to parse.
      (b) a **measured sample**: the raised board's new ``provenance``
          block must be a measured-live record -- source
          ``"measured-live"``, a resolvable ``measured_at_commit``, a
          clean tree (``dirty`` false), a concrete recorded kicad-cli
          version, at least 120 samples whenever ANY category is
          declared nondeterministic (structured ``sample_count`` or
          ``measured_via`` prose) -- not only ``clearance``; see the
          2026-08-11 fix note inline below for why this is
          category-generic now -- and an input hash that still matches
          ``pcb/temper.kicad_pcb``'s current content.

    Each violation is reported as one problem string naming the failing
    dimension, so an unapproved raise fails with the *specific* reason
    (the anti-vacuity discipline: a raise cannot fail for a generic
    reason that hides which check actually bit).

    The ceiling values themselves are read through
    ``find_ceiling_raises``, which int-VALIDATES them with the same
    fail-loudly ``CeilingMarshalError`` marshal ``detect_ceiling_raise``
    applies -- a non-int ceiling in the raise comparison fails loudly
    here too, never silently truncated.
    """
    from temper_placer.regression.drc_ratchet import (
        _SHA256_HEX_RE,
        _provenance_sample_count,
        _sha256_file,
        _verify_commits_exist,
    )

    problems: list[str] = []

    raises = find_ceiling_raises(old_ceiling, new_ceiling)
    if not raises:
        return problems

    # (a) Cause authority: the _march log. One check over the whole
    # raise set -- a single new entry can attribute several per-type
    # deltas (every real remeasurement entry in this file does exactly
    # that), so the requirement is "at least one", not one per raise.
    old_march = old_ceiling.get("_march") or {}
    new_march = new_ceiling.get("_march") or {}

    def _has_cause(value: object) -> bool:
        """A ``_march`` entry counts as an attributed cause when it names
        one: a non-empty prose string (the legacy format every entry in
        this file used before the 2026-08-19 standardization), or a
        structured entry whose non-empty ``cause`` field names it (the
        standardized format: ``{"date": ..., "cause": ...,
        "per_type_delta": {...}}``). A structured entry with a missing or
        blank ``cause`` is NOT a cause -- the same semantic as a blank
        string, and just as much a contract failure; the format extension
        must not let a shape without a named cause through.
        """
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, dict):
            cause = value.get("cause")
            return isinstance(cause, str) and bool(cause.strip())
        return False

    new_cause_entries = [
        key
        for key, value in new_march.items()
        if key not in old_march and _has_cause(value)
    ]
    if not new_cause_entries:
        problems.append(
            "raise has no attributed cause: no NEW non-empty '_march' entry "
            "(drc_ceiling.json's _march log is the single cause authority -- "
            "a raise must name the component/commit that drove it)"
        )

    # (b) Measurement evidence, per raised board.
    board_by_id = {b.get("board_id"): b for b in new_ceiling.get("boards", [])}

    # Batch-verify every shape-valid measured_at_commit resolves to a
    # real commit object -- one `git cat-file --batch-check` subprocess
    # for the whole raise set (see _verify_commits_exist above). The
    # pre-fix check below only validated SHA *shape*
    # (_SHA256_HEX_RE.fullmatch) while its own error message claimed
    # the commit "does not resolve to a commit" -- it never asked git,
    # so a syntactically-valid but dangling/orphaned SHA (e.g. one
    # orphaned by a rebase) passed silently. This is exactly how
    # drc_ceiling.json carried an unresolvable measured_at_commit for
    # weeks.
    shas_to_verify: set[str] = set()
    for board_id, _reasons in raises:
        record = board_by_id.get(board_id)
        if record is None:
            continue
        prov = record.get("provenance")
        if not isinstance(prov, dict):
            continue
        commit = prov.get("measured_at_commit")
        if isinstance(commit, str) and _SHA256_HEX_RE.fullmatch(commit):
            shas_to_verify.add(commit)
    resolved_commits = _verify_commits_exist(shas_to_verify, repo_root)

    for board_id, _reasons in raises:
        record = board_by_id.get(board_id)
        if record is None:
            problems.append(
                f"{board_id}: raised board missing from the new ceiling record"
            )
            continue

        prov = record.get("provenance")
        if not isinstance(prov, dict):
            problems.append(
                f"{board_id}: raise has no measured sample: the board's new "
                "record carries no 'provenance' object"
            )
            continue

        source = prov.get("source")
        if source != "measured-live":
            problems.append(
                f"{board_id}: provenance source={source!r} is not "
                "'measured-live' -- a raise must cite a freshly measured "
                "record, not a backfilled one"
            )

        commit = prov.get("measured_at_commit")
        if not (
            isinstance(commit, str)
            and _SHA256_HEX_RE.fullmatch(commit)
            and resolved_commits.get(commit, False)
        ):
            problems.append(
                f"{board_id}: provenance measured_at_commit={commit!r} does not "
                "resolve to a commit -- a measured-live raise must name the "
                "commit it was measured at"
            )

        dirty = prov.get("dirty")
        if dirty is not False:
            problems.append(
                f"{board_id}: provenance dirty={dirty!r} -- a raise must be "
                "measured in a clean tree"
            )

        tool_versions = prov.get("tool_versions")
        kicad_cli_version = (
            tool_versions.get("kicad-cli") if isinstance(tool_versions, dict) else None
        )
        if not (
            isinstance(kicad_cli_version, str)
            and kicad_cli_version.strip()
            and kicad_cli_version != "UNKNOWN"
        ):
            problems.append(
                f"{board_id}: provenance does not record a concrete kicad-cli "
                "version in tool_versions -- a raise must be measured with the "
                "contract tool (run_drc with --all-track-errors)"
            )

        # Sample count: >= 120 whenever ANY category is declared
        # nondeterministic -- every such category's ceiling is an
        # observed-max-plus-headroom number, which is only meaningful
        # when the observation actually sampled the run-to-run spread.
        #
        # This used to check only ``"clearance" in nondet`` -- literally
        # true when clearance was this file's one chronically-scattering
        # category, but it silently stopped enforcing anything the
        # moment a DIFFERENT category (``creepage``, since the #602 K3
        # swap) became the one carrying real run-to-run noise: a
        # creepage-only raise sailed through this check with zero
        # samples required, because the string "clearance" just wasn't
        # in its ``nondeterministic_error_types`` keys. Found while
        # fixing the creepage noise-headroom guard (2026-08-11) -- the
        # same discipline this file's docstring already claims
        # ("at least 120 samples for the nondeterministic clearance
        # category") was never actually category-generic in code. Now
        # checked once per declared-nondeterministic category, not once
        # for a single hardcoded name.
        nondet = record.get("nondeterministic_error_types")
        if isinstance(nondet, dict) and nondet:
            sample_count = _provenance_sample_count(prov)
            if sample_count is None or sample_count < 120:
                categories = ", ".join(sorted(nondet))
                problems.append(
                    f"{board_id}: {categories} declared nondeterministic but the "
                    f"provenance records {sample_count!r} sample(s) -- the "
                    "measurement contract requires at least 120 samples "
                    "(provenance.sample_count, or measured_via prose on "
                    "legacy records)"
                )

        # Input freshness: the recorded board hash must still match the
        # board file's current content -- a raise measured against a
        # board that has since moved is a stale measurement.
        board_rel = record.get("path")
        # Bind once, then narrow: `prov.get(...)` called twice is two
        # separate expressions, so the isinstance does not narrow the
        # value that actually gets assigned.
        raw_inputs = prov.get("inputs")
        inputs = raw_inputs if isinstance(raw_inputs, list) else []
        matching_inputs = [
            inp for inp in inputs if isinstance(inp, dict) and inp.get("path") == board_rel
        ]
        if not matching_inputs:
            problems.append(
                f"{board_id}: provenance inputs do not name the board file "
                f"{board_rel!r} -- a raise must hash the exact input it measured"
            )
        else:
            try:
                current_hash = _sha256_file(repo_root / board_rel)
            except OSError as exc:
                problems.append(
                    f"{board_id}: cannot hash the board file {board_rel!r} "
                    f"({exc}) -- a raise must be backed by a board that exists"
                )
                continue
            for inp in matching_inputs:
                recorded_hash = inp.get("sha256")
                if not (
                    isinstance(recorded_hash, str)
                    and len(recorded_hash) == 64
                    and recorded_hash == current_hash
                ):
                    problems.append(
                        f"{board_id}: provenance input hash for {board_rel} does "
                        "not match the file's current content -- the raise cites "
                        "a STALE measurement (input moved since it was measured)"
                    )

    return problems


def detect_ceiling_raise(
    old_ceiling: dict, new_ceiling: dict, commit_message: str = ""
) -> DrcRatchetResult | None:
    """Detect if ceiling was raised without approval.

    A raise is any of: the aggregate ``error_ceiling`` increasing, the
    aggregate ``warning_ceiling`` increasing, or any single rule inside
    ``violations_by_type`` (errors) or ``warnings_by_type`` (warnings)
    increasing -- including a rule that didn't exist in the old record
    at all, which is a raise from its implicit ceiling of 0 (the same
    implicit-zero semantics ``_check_board`` enforces at runtime).
    Editing the ceiling *file* to grant a rule more room is exactly as
    much a raise as editing the aggregate number, and must require the
    same ``Ceiling-Approval:`` trailer -- otherwise the per-type
    ceiling could be silently inflated in the JSON itself, sidestepping
    the runtime check entirely. This applies symmetrically to
    ``violations_by_type`` and ``warnings_by_type``: an earlier version
    of this method checked only the warnings side, which meant a
    per-type *error* ceiling (e.g. ``clearance``) could be raised in
    the committed JSON with no trailer and this detector would not
    notice, even though ``_check_board`` enforces that exact ceiling at
    runtime.

    The ``Ceiling-Approval:`` check remains the substring marker (any
    commit in the PR containing it) -- it is the *raise detector*, not
    the cause authority. Whether an approved raise actually carries an
    attributed cause and a measured sample is the measurement-evidence
    contract, validated separately by ``validate_raise_evidence``.

    Wave 4 Phase 4: the raise-detection compute (the enumeration above
    plus the substring check) now runs in ``temper_drc_rs.detect_ceiling_raise``
    -- a verbatim port of the pre-migration raise detector, whose
    constants are unchanged -- so the #575 gate's behavior is preserved.
    R27's ``find_ceiling_raises`` implements the same raise rules as the
    Python contract layer (consumed by ``validate_raise_evidence``); the
    differential suite in test_drc_ratchet_rust_differential.py keeps the
    two bit-identical.
    """
    from temper_placer.regression.drc_ratchet import (
        DrcRatchetResult,
        _marshal_ceiling_int,
        _tdrc,
    )

    def _marshal(ceiling: dict) -> list[tuple]:
        # Pass 2 (P1-1): every value is int-VALIDATED at this marshal
        # boundary, not merely int()-coerced. The old coercion silently
        # truncated a float-valued ceiling (``100.5`` -> ``100``), making
        # a raise ``100 -> 100.5`` invisible to the kernel and failing
        # the #575 approval gate OPEN. ``CeilingMarshalError`` fires
        # before the kernel instead.
        boards: list[tuple] = []
        for board in ceiling.get("boards", []):
            board_id = board["board_id"]
            boards.append(
                (
                    board_id,
                    _marshal_ceiling_int(
                        board.get("error_ceiling", 0), "error_ceiling", board_id
                    ),
                    _marshal_ceiling_int(
                        board.get("warning_ceiling", 0), "warning_ceiling", board_id
                    ),
                    [
                        (
                            rule,
                            _marshal_ceiling_int(
                                count,
                                f"violations_by_type[{rule}]",
                                board_id,
                            ),
                        )
                        for rule, count in (board.get("violations_by_type") or {}).items()
                    ],
                    [
                        (
                            rule,
                            _marshal_ceiling_int(
                                count,
                                f"warnings_by_type[{rule}]",
                                board_id,
                            ),
                        )
                        for rule, count in (board.get("warnings_by_type") or {}).items()
                    ],
                )
            )
        return boards

    result = _tdrc().detect_ceiling_raise(
        _marshal(old_ceiling),
        _marshal(new_ceiling),
        commit_message,
    )
    if result is None:
        return None
    return DrcRatchetResult(
        passed=result["passed"],
        board_id=result["board_id"],
        message=result["message"],
        exit_code=result["exit_code"],
    )
