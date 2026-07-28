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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_evidence_provenance import check_text_file  # noqa: E402

SHA = "a" * 40


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
