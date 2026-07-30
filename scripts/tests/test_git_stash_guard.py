"""Behavioural tests for the git-stash-guard reference-transaction hook.

The hook lives in `scripts/git-hooks/reference-transaction` and is installed
into the shared `.git/hooks` by `scripts/install_git_stash_guard.py`.

These run the REAL hook against a throwaway repo and assert on git's exit
status, because the thing under test is an interaction between git's ref
transaction machinery and a shell script -- unit-testing the script's logic in
isolation would not have caught the bug these tests exist to pin.

The bug: `git pack-refs` emits two refs/stash transactions whose old/new OIDs
are shape-identical to a stash create and a `git stash clear`:

    git pack-refs --all   0000000 -> 96a68b4    (looks like a create)
    git pack-refs --all   96a68b4 -> 0000000    (looks like a clear)

so the hook aborted git's auto-gc. No OID-based rule can separate those cases;
the hook discriminates on the invoking subcommand instead. If someone
"simplifies" that back to an OID check, `test_pack_refs_is_allowed` fails.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SOURCE = REPO_ROOT / "scripts" / "git-hooks" / "reference-transaction"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not HOOK_SOURCE.is_file(),
    reason="needs git and the hook source",
)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> int:
    """Run git in `repo`, returning the exit status (never raising)."""
    full_env = None
    if env is not None:
        import os

        full_env = {**os.environ, **env}
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=full_env,
    ).returncode


@pytest.fixture
def guarded_repo(tmp_path: Path) -> Path:
    """A repo with one commit, the real hook installed, and one stash seeded."""
    repo = tmp_path / "r"
    repo.mkdir()
    assert _git(repo, "init", "-q", ".") == 0
    assert _git(repo, "config", "user.email", "t@example.invalid") == 0
    assert _git(repo, "config", "user.name", "t") == 0

    hook = repo / ".git" / "hooks" / "reference-transaction"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK_SOURCE.read_text())
    hook.chmod(0o755)

    (repo / "f").write_text("a\n")
    assert _git(repo, "add", "f") == 0
    assert _git(repo, "commit", "-qm", "init") == 0

    # Seed a stash through the documented bypass so the deletion-shaped cases
    # below have something real to act on.
    (repo / "f").write_text("b\n")
    assert _git(repo, "stash", "-q", env={"ALLOW_GIT_STASH": "1"}) == 0
    return repo


class TestBlocksRealStashOperations:
    def test_stash_push_is_blocked(self, guarded_repo: Path) -> None:
        (guarded_repo / "f").write_text("c\n")
        assert _git(guarded_repo, "stash") != 0

    def test_stash_clear_is_blocked(self, guarded_repo: Path) -> None:
        assert _git(guarded_repo, "stash", "clear") != 0

    def test_blocked_clear_leaves_the_stack_intact(self, guarded_repo: Path) -> None:
        """A blocked clear must not have destroyed the shared stack."""
        _git(guarded_repo, "stash", "clear")
        out = subprocess.run(
            ["git", "stash", "list"], cwd=guarded_repo, capture_output=True, text=True
        )
        assert out.stdout.strip(), "the seeded stash entry was destroyed by a blocked clear"


class TestAllowsRoutineMaintenance:
    """The false positive this carve-out fixes: git's own auto-gc was aborted."""

    def test_pack_refs_is_allowed(self, guarded_repo: Path) -> None:
        assert _git(guarded_repo, "pack-refs", "--all") == 0

    def test_gc_is_allowed(self, guarded_repo: Path) -> None:
        assert _git(guarded_repo, "gc", "--quiet") == 0

    def test_pack_refs_preserves_the_stash(self, guarded_repo: Path) -> None:
        """Allowing pack-refs must not lose the entry it repacks."""
        assert _git(guarded_repo, "pack-refs", "--all") == 0
        out = subprocess.run(
            ["git", "stash", "list"], cwd=guarded_repo, capture_output=True, text=True
        )
        assert out.stdout.strip(), "pack-refs dropped the stash entry"


class TestBypass:
    def test_allow_git_stash_env_var_permits_a_push(self, guarded_repo: Path) -> None:
        (guarded_repo / "f").write_text("d\n")
        assert _git(guarded_repo, "stash", "-q", env={"ALLOW_GIT_STASH": "1"}) == 0


class TestHookSourceIntegrity:
    def test_marker_comment_present(self) -> None:
        """install_git_stash_guard.py refuses to install without this marker."""
        assert "git-stash-guard: reference-transaction hook" in HOOK_SOURCE.read_text()

    def test_carve_out_fails_closed_without_ps(self) -> None:
        """The maintenance carve-out must require a non-empty parent command.

        If `ps` is unavailable the hook must fall through to blocking, not
        silently allow everything.
        """
        text = HOOK_SOURCE.read_text()
        assert '[ -n "$_parent_cmd" ]' in text, "carve-out must require a non-empty ps result"
