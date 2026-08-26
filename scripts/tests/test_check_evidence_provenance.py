"""Tests for the evidence-provenance gate's stamp parsing.

The gate requires every evidence file to declare how its numbers were made:

    provenance: commit=<sha-or-UNKNOWN> dirty=<true|false|UNKNOWN>

The strict form demands `dirty=` immediately after `commit=`. Authors in
practice annotate inside the comment -- "commit=<sha> (repointed to <branch>
@ <sha>) dirty=UNKNOWN" -- and under the strict form the whole stamp then
reads as *absent*, which is a worse and more confusing failure than the prose
it objects to. Five files arriving from main hit exactly this.

Tolerating annotation must not become tolerating an incomplete stamp, so the
cases below pin both directions: annotated stamps are accepted, and stamps
missing either field are still rejected.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_evidence_provenance as gate  # noqa: E402
from check_evidence_provenance import (  # noqa: E402
    REPO_ROOT,
    _is_shallow_repo,
    check_text_file,
    verify_commits_exist,
)

SHA = "a" * 40
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_evidence_provenance.py"


def _real_head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.strip()


def _run_gate(evidence_dir: Path, allowlist: Path) -> subprocess.CompletedProcess:
    """Invoke the real CLI end-to-end (not just check_text_file/check_json_file)
    against a fixture evidence directory."""
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--evidence-dir",
            str(evidence_dir),
            "--allowlist",
            str(allowlist),
        ],
        capture_output=True,
        text=True,
    )


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "evidence.md"
    p.write_text(body, encoding="utf-8")
    return p


class TestAcceptsWellFormedStamps:
    def test_canonical_single_line(self, tmp_path: Path) -> None:
        p = _write(tmp_path, f"# T\n\n<!-- provenance: commit={SHA} dirty=false -->\n")
        assert check_text_file(p).ok

    def test_unknown_commit_is_a_valid_token(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "# T\n\n<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->\n")
        assert check_text_file(p).ok


class TestAcceptsAnnotatedStamps:
    """The real-world forms that previously read as 'no provenance line'."""

    def test_prose_between_the_two_fields(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            f"# T\n\n<!-- provenance: commit={SHA} (repointed to some-branch) "
            "dirty=UNKNOWN -->\n",
        )
        r = check_text_file(p)
        assert r.ok, r.reason

    def test_stamp_wrapped_across_lines(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            f"# T\n\n<!-- provenance: commit={SHA}\n     (measured on branch X)\n"
            "     dirty=true -->\n",
        )
        r = check_text_file(p)
        assert r.ok, r.reason

    def test_commit_is_still_reported_correctly(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path, f"# T\n\n<!-- provenance: commit={SHA} (note) dirty=false -->\n"
        )
        assert check_text_file(p).commit == SHA


class TestStillRejectsIncompleteStamps:
    """Tolerating annotation must not tolerate a missing field."""

    def test_missing_dirty_field_is_rejected(self, tmp_path: Path) -> None:
        p = _write(tmp_path, f"# T\n\n<!-- provenance: commit={SHA} -->\n")
        assert not check_text_file(p).ok

    def test_missing_commit_field_is_rejected(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "# T\n\n<!-- provenance: dirty=false -->\n")
        assert not check_text_file(p).ok

    def test_no_stamp_at_all_is_rejected(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "# T\n\nSome prose with no stamp.\n")
        assert not check_text_file(p).ok

    def test_malformed_sha_is_rejected(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "# T\n\n<!-- provenance: commit=deadbeef dirty=false -->\n")
        assert not check_text_file(p).ok

    def test_fields_from_two_separate_stamps_do_not_pair(self, tmp_path: Path) -> None:
        """A commit in one block must not be satisfied by a dirty in another."""
        p = _write(
            tmp_path,
            f"# T\n\n<!-- provenance: commit={SHA} -->\n\nprose\n\n"
            "<!-- provenance: dirty=false -->\n",
        )
        assert not check_text_file(p).ok


class TestDiagnosticDistinguishesMalformedFromMissing:
    """A present-but-unparseable stamp must not be reported as a missing one.

    These assert on the REASON, not just on rejection -- the outcomes above
    already cover rejection. An abbreviated SHA was being reported as "no
    provenance line found", which sends the reader hunting for a line that is
    sitting in the file, and cost real investigation time on
    docs/evidence/2026-07-28-netclass-defect-reconciliation.md.
    """

    def test_abbreviated_sha_says_abbreviated_not_missing(self, tmp_path: Path) -> None:
        p = _write(tmp_path, f"# T\n\n<!-- provenance: commit={SHA[:8]} dirty=false -->\n")
        r = check_text_file(p)
        assert not r.ok
        assert "abbreviated SHA" in r.reason
        assert "no 'provenance" not in r.reason

    def test_non_hex_commit_says_not_a_sha(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "# T\n\n<!-- provenance: commit=not-a-sha dirty=true -->\n")
        r = check_text_file(p)
        assert not r.ok
        assert "could not be parsed" in r.reason
        assert "not-a-sha" in r.reason

    def test_genuinely_missing_stamp_keeps_the_original_message(self, tmp_path: Path) -> None:
        """The missing-stamp path must be unchanged -- that message is correct."""
        p = _write(tmp_path, "# T\n\nSome prose with no stamp.\n")
        r = check_text_file(p)
        assert not r.ok
        assert "no 'provenance" in r.reason
        assert "could not be parsed" not in r.reason

    def test_diagnostic_reports_the_missing_field_by_name(self, tmp_path: Path) -> None:
        p = _write(tmp_path, f"# T\n\n<!-- provenance: commit={SHA[:8]} -->\n")
        r = check_text_file(p)
        assert not r.ok
        assert "dirty=<absent>" in r.reason

    def test_valid_stamp_is_unaffected(self, tmp_path: Path) -> None:
        p = _write(tmp_path, f"# T\n\n<!-- provenance: commit={SHA} dirty=false -->\n")
        assert check_text_file(p).ok


class TestVerifyCommitsExist:
    """A well-formed SHA (40 lowercase hex chars) is not enough -- it must
    also resolve to a real commit object. SHA_RE alone cannot catch a
    fabricated tail on a real prefix (the exact shape of the two provenance
    stamps this gate was found to be missing on main); verify_commits_exist
    is the layer that does, via a single `git cat-file --batch-check`.
    """

    def test_real_head_commit_resolves(self) -> None:
        head = _real_head_sha()
        resolved = verify_commits_exist({head}, REPO_ROOT)
        assert resolved[head] is True

    def test_fabricated_well_formed_sha_does_not_resolve(self) -> None:
        fake = "d" * 40
        resolved = verify_commits_exist({fake}, REPO_ROOT)
        assert resolved[fake] is False

    def test_mixed_set_resolves_each_independently(self) -> None:
        head = _real_head_sha()
        fake = "e" * 40
        resolved = verify_commits_exist({head, fake}, REPO_ROOT)
        assert resolved[head] is True
        assert resolved[fake] is False

    def test_empty_set_short_circuits_without_invoking_git(self) -> None:
        assert verify_commits_exist(set(), REPO_ROOT) == {}


class TestShallowCloneFailsClosedNotSilently:
    """A shallow clone (fetch-depth: 1) has almost none of a repo's
    historical commit objects, so 'does not resolve' would be true of
    nearly every legitimate SHA there -- indistinguishable from a fabricated
    one. verify_commits_exist must refuse outright (RuntimeError, which
    main() turns into exit 5, a TOOL ERROR) rather than either silently
    pass (defeats the gate) or report every historical SHA as a fabricated
    one (a failure this gate cannot substantiate).
    """

    def test_full_worktree_checkout_is_not_shallow(self) -> None:
        # Sanity check on the environment these tests actually run in --
        # if this ever flips to True unexpectedly, every test in this class
        # would be validating the wrong branch of the code.
        assert _is_shallow_repo(REPO_ROOT) is False

    def test_shallow_clone_is_detected(self, tmp_path: Path) -> None:
        shallow = tmp_path / "shallow-clone"
        subprocess.run(
            ["git", "clone", "--depth", "1", f"file://{REPO_ROOT}", str(shallow)],
            capture_output=True,
            text=True,
            check=True,
        )
        assert _is_shallow_repo(shallow) is True

    def test_verify_commits_exist_refuses_on_shallow_clone(self, tmp_path: Path) -> None:
        shallow = tmp_path / "shallow-clone"
        subprocess.run(
            ["git", "clone", "--depth", "1", f"file://{REPO_ROOT}", str(shallow)],
            capture_output=True,
            text=True,
            check=True,
        )
        with pytest.raises(RuntimeError, match="shallow"):
            verify_commits_exist({"a" * 40}, shallow)


class TestCommitExistenceGateEndToEnd:
    """Full CLI invocations (not just the format-check functions) proving
    the gate actually rejects a fabricated-but-well-formed SHA and actually
    passes a real one, through both provenance schema paths -- the .md
    'provenance: commit=... dirty=...' line and the .json
    provenance.commit field.
    """

    def test_fabricated_well_formed_sha_is_rejected_in_markdown(
        self, tmp_path: Path
    ) -> None:
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "fabricated.md").write_text(
            f"# T\n\n<!-- provenance: commit={'d' * 40} dirty=false -->\n"
        )
        result = _run_gate(evidence_dir, tmp_path / ".allowlist")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "does not resolve" in result.stdout
        # Must read as its own diagnosis, not as either of the two existing
        # (and separately tested/pinned) failure messages.
        assert "no 'provenance" not in result.stdout
        assert "could not be parsed" not in result.stdout

    def test_real_commit_sha_passes_in_markdown(self, tmp_path: Path) -> None:
        head = _real_head_sha()
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "real.md").write_text(
            f"# T\n\n<!-- provenance: commit={head} dirty=false -->\n"
        )
        result = _run_gate(evidence_dir, tmp_path / ".allowlist")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout

    def test_fabricated_well_formed_sha_is_rejected_in_json(
        self, tmp_path: Path
    ) -> None:
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "fabricated.json").write_text(
            json.dumps({"provenance": {"commit": "d" * 40, "dirty": False}})
        )
        result = _run_gate(evidence_dir, tmp_path / ".allowlist")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "does not resolve" in result.stdout

    def test_real_commit_sha_passes_in_json(self, tmp_path: Path) -> None:
        head = _real_head_sha()
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "real.json").write_text(
            json.dumps({"provenance": {"commit": head, "dirty": False}})
        )
        result = _run_gate(evidence_dir, tmp_path / ".allowlist")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout


class TestAntiVacuity:
    """The legacy-backlog allowlist (commit=UNKNOWN + a ticketed
    .evidence-provenance-allowlist entry) exists so genuinely-unrecoverable
    historical docs can be marked rather than fabricated a SHA -- see the
    module docstring and the 2026-08-07 backlog paydown recorded in
    .evidence-provenance-allowlist. That mechanism must not become a way for
    a brand-new doc to dodge the gate: an allowlist entry only tolerates the
    *specific file* it names, and only when that file actually carries a
    valid commit=UNKNOWN stamp -- it must never make the *directory* pass
    regardless of what else is in it. These pin that boundary directly,
    mirroring TestAntiVacuity in test_check_isolation_keepout.py.
    """

    def test_legacy_unknown_doc_alone_passes(self, tmp_path: Path) -> None:
        """Sanity baseline: a properly-stamped, properly-allowlisted legacy
        doc passes by itself -- establishes that the fixture setup below is
        exercising the allowlist path, not accidentally failing for some
        other reason."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "legacy.md").write_text(
            "# Legacy\n\n<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->\n"
        )
        allowlist = tmp_path / ".allowlist"
        allowlist.write_text("legacy.md  # TODO: temper-xxx\n")
        result = _run_gate(evidence_dir, allowlist)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout

    def test_new_unstamped_doc_still_fails_alongside_allowlisted_legacy_doc(
        self, tmp_path: Path
    ) -> None:
        """The case this test exists for: the legacy doc is present, valid,
        and allowlisted (passes on its own, per the test above) -- and a
        second, brand-new file with NO provenance stamp at all is dropped
        into the same directory, not allowlisted. The gate must still fail
        overall: the allowlist covers exactly the one named legacy file, not
        the directory as a whole."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "legacy.md").write_text(
            "# Legacy\n\n<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->\n"
        )
        (evidence_dir / "new-unprovenanced.md").write_text(
            "# Brand new doc\n\nSome prose with no provenance stamp at all.\n"
        )
        allowlist = tmp_path / ".allowlist"
        allowlist.write_text("legacy.md  # TODO: temper-xxx\n")
        result = _run_gate(evidence_dir, allowlist)
        assert result.returncode == 3, result.stdout + result.stderr
        assert "new-unprovenanced.md" in result.stdout
        assert "no 'provenance" in result.stdout
        # The legacy doc itself must not be reported as a violation -- only
        # the new, genuinely-unstamped file should be.
        assert "legacy.md:" not in result.stdout

    def test_new_doc_declaring_unknown_without_an_allowlist_entry_fails(
        self, tmp_path: Path
    ) -> None:
        """A second way to try to dodge the gate: self-declare
        commit=UNKNOWN without ever adding the ticketed allowlist entry. The
        allowlist entry is not optional bookkeeping -- an unlisted UNKNOWN is
        exactly as much a violation as a missing stamp."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "legacy.md").write_text(
            "# Legacy\n\n<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->\n"
        )
        (evidence_dir / "sneaky-unknown.md").write_text(
            "# Sneaky\n\n<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->\n"
        )
        allowlist = tmp_path / ".allowlist"
        allowlist.write_text("legacy.md  # TODO: temper-xxx\n")
        result = _run_gate(evidence_dir, allowlist)
        assert result.returncode == 3, result.stdout + result.stderr
        assert "sneaky-unknown.md" in result.stdout
        assert "not on" in result.stdout


class TestFailBeforePassAfter:
    """Explicit before/after demonstration that adding a real, correct
    provenance stamp to a NEW (non-legacy) doc is what actually turns the
    gate green -- not just the presence of an allowlist. Mirrors
    TestFailBeforePassAfter in test_check_isolation_keepout.py: two synthetic
    fixtures standing in for a single file's before/after edit, since there
    is no git history to diff against here."""

    def test_before_no_stamp_fails(self, tmp_path: Path) -> None:
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "before.md").write_text(
            "# T\n\nSome prose with no provenance stamp.\n"
        )
        result = _run_gate(evidence_dir, tmp_path / ".allowlist")
        assert result.returncode == 3, result.stdout + result.stderr

    def test_after_real_commit_stamp_passes(self, tmp_path: Path) -> None:
        head = _real_head_sha()
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "after.md").write_text(
            f"# T\n\n<!-- provenance: commit={head} dirty=false -->\n"
        )
        result = _run_gate(evidence_dir, tmp_path / ".allowlist")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout


# ---------------------------------------------------------------------------
# Derived-default contract (2026-08-25)
#
# docs/evidence/2026-08-25-provenance-stamp-contract-decision.md: an explicit
# commit=DERIVED is COMPUTED as the commit that introduced the file, because the
# contract previously asked authors for a value that does not exist when they
# write the file (45% land-failure; 68% of repairs transcribed this exact
# value and a further 23% pointed at the bulk-repair commit that stamped
# them). The author must still supply dirty state. These tests exist so the
# change cannot quietly become "the gate always passes": each one fails if its
# specific guard is removed.
# ---------------------------------------------------------------------------


def _git(tmp, *args):
    subprocess.run(["git", *args], cwd=tmp, check=True,
                   capture_output=True, text=True)


def _repo_with(tmp_path, name, body):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    d = tmp_path / "docs" / "evidence"
    d.mkdir(parents=True)
    (d / name).write_text(body)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "add")
    return d / name


def test_explicit_derived_stamp_is_resolved_and_marked(tmp_path):
    """DERIVED plus author-supplied dirty state resolves and stays distinct."""
    f = _repo_with(
        tmp_path,
        "a.md",
        "<!-- provenance: commit=DERIVED dirty=false -->\n# x\n",
    )
    r = gate.check_file(f)
    assert r.ok, r.reason
    assert r.derived is True
    assert gate.SHA_RE.match(r.commit or ""), r.commit


def test_missing_stamp_still_fails_even_when_derivation_is_enabled(tmp_path):
    """Git cannot recover dirty state, so a completely absent stamp is red."""
    f = _repo_with(tmp_path, "missing.md", "# no stamp here\n")
    r = gate.check_file(f)
    assert not r.ok
    assert r.derived is False
    assert "no 'provenance:" in r.reason


def test_derived_without_dirty_still_fails(tmp_path):
    """DERIVED only replaces commit; it never manufactures dirty state."""
    f = _repo_with(
        tmp_path,
        "missing-dirty.md",
        "<!-- provenance: commit=DERIVED -->\n# x\n",
    )
    r = gate.check_file(f)
    assert not r.ok
    assert "dirty=<absent>" in r.reason


def test_json_explicit_derived_has_parity_with_text(tmp_path):
    f = _repo_with(
        tmp_path,
        "derived.json",
        json.dumps({"provenance": {"commit": "DERIVED", "dirty": False}}),
    )
    r = gate.check_file(f)
    assert r.ok, r.reason
    assert r.derived is True
    assert gate.SHA_RE.match(r.commit or ""), r.commit


def test_json_missing_provenance_still_fails(tmp_path):
    f = _repo_with(tmp_path, "missing.json", json.dumps({"measurement": 1}))
    r = gate.check_file(f)
    assert not r.ok
    assert r.derived is False


def test_author_stamp_is_not_marked_derived(tmp_path):
    """An explicit stamp round-trips unchanged and is NOT marked derived --
    the 9% of files whose measurement tree differs from where they landed
    must stay distinguishable."""
    sha = "b" * 40
    f = _repo_with(tmp_path, "b.md",
                   f"<!-- provenance: commit={sha} dirty=false -->\n# x\n")
    r = gate.check_file(f)
    assert r.ok, r.reason
    assert r.derived is False
    assert r.commit == sha


def test_unparseable_stamp_still_fails_and_is_never_derived(tmp_path):
    """A malformed stamp is a DIFFERENT failure from a missing one and must
    not be rescued by derivation -- otherwise an abbreviated or fabricated
    SHA becomes green."""
    f = _repo_with(tmp_path, "c.md",
                   "<!-- provenance: commit=abc123 dirty=false -->\n# x\n")
    r = gate.check_file(f)
    assert not r.ok
    assert r.derived is False


def test_no_derive_restores_the_stricter_contract(tmp_path):
    """--no-derive rejects an explicit request to compute the commit."""
    f = _repo_with(
        tmp_path,
        "d.md",
        "<!-- provenance: commit=DERIVED dirty=false -->\n# x\n",
    )
    gate._DERIVE_DISABLED = True
    try:
        r = gate.check_file(f)
    finally:
        gate._DERIVE_DISABLED = False
    assert not r.ok
    assert "disabled by --no-derive" in r.reason


def test_underivable_file_fails_rather_than_passing(tmp_path):
    """If git cannot name an introducing commit -- untracked file, shallow
    clone -- the gate FAILS. A derivation that cannot be made must never
    silently pass; that is the vacuous shape this repo has shipped before."""
    _git(tmp_path, "init", "-q")
    d = tmp_path / "docs" / "evidence"
    d.mkdir(parents=True)
    f = d / "e.md"
    f.write_text("<!-- provenance: commit=DERIVED dirty=false -->\n")
    assert gate.derive_introducing_commit(f) is None
    r = gate.check_file(f)
    assert not r.ok
