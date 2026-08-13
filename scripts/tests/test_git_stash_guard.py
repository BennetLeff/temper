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


def _stash_list(repo: Path) -> str:
    return subprocess.run(
        ["git", "stash", "list"], cwd=repo, capture_output=True, text=True
    ).stdout


class TestBlocksRealStashOperations:
    """Every ref-creating/destroying stash form the task requires coverage for.

    `git stash`, `push`, `-u`, and `save` all create a NEW refs/stash entry
    via git's transactional ref-update API, so the hook sees and blocks all
    four uniformly -- there is nothing form-specific about the blocking
    logic, but each is tested explicitly (rather than assumed from one) per
    "a guard that only catches the bare form is worse than none."
    """

    def test_bare_stash_is_blocked(self, guarded_repo: Path) -> None:
        (guarded_repo / "f").write_text("c\n")
        assert _git(guarded_repo, "stash") != 0

    def test_stash_push_is_blocked(self, guarded_repo: Path) -> None:
        (guarded_repo / "f").write_text("c\n")
        assert _git(guarded_repo, "stash", "push") != 0

    def test_stash_push_dash_u_is_blocked(self, guarded_repo: Path) -> None:
        """`-u` (include untracked) still routes through the same ref-create path."""
        (guarded_repo / "untracked.txt").write_text("u\n")
        assert _git(guarded_repo, "stash", "-u") != 0
        assert (guarded_repo / "untracked.txt").is_file(), (
            "a blocked `stash -u` must not have removed the untracked file it "
            "was about to stash"
        )

    def test_stash_save_is_blocked(self, guarded_repo: Path) -> None:
        """`stash save` is the deprecated pre-2.16 spelling of `stash push`."""
        (guarded_repo / "f").write_text("c\n")
        assert _git(guarded_repo, "stash", "save", "msg") != 0

    def test_stash_clear_is_blocked(self, guarded_repo: Path) -> None:
        assert _git(guarded_repo, "stash", "clear") != 0

    def test_stash_clear_is_blocked_with_multiple_entries(self, guarded_repo: Path) -> None:
        """The realistic production case: an 80+-deep stack, not a single entry."""
        for msg in ("two", "three"):
            (guarded_repo / "f").write_text(msg + "\n")
            assert _git(guarded_repo, "stash", "push", "-q", "-m", msg, env={"ALLOW_GIT_STASH": "1"}) == 0
        before = _stash_list(guarded_repo)
        assert before.count("stash@{") == 3
        assert _git(guarded_repo, "stash", "clear") != 0
        assert _stash_list(guarded_repo) == before, "a blocked clear must not touch the stack"

    def test_blocked_clear_leaves_the_stack_intact(self, guarded_repo: Path) -> None:
        """A blocked clear must not have destroyed the shared stack."""
        _git(guarded_repo, "stash", "clear")
        assert _stash_list(guarded_repo).strip(), "the seeded stash entry was destroyed by a blocked clear"

    def test_stash_drop_of_the_sole_entry_does_not_lose_the_commit(self, guarded_repo: Path) -> None:
        """Dropping the LAST entry requires deleting refs/stash outright, which
        IS a ref transaction, so the hook fires and the underlying commit
        survives (still resolvable), even though `git stash list` -- which
        reads the reflog, rewritten by git before the transaction is even
        attempted -- goes empty. See TestDocumentedGaps for the forms where
        no ref transaction happens at all and nothing survives."""
        before_sha = subprocess.run(
            ["git", "rev-parse", "refs/stash"], cwd=guarded_repo, capture_output=True, text=True
        ).stdout.strip()
        assert _git(guarded_repo, "stash", "drop") != 0
        after_sha = subprocess.run(
            ["git", "rev-parse", "refs/stash"], cwd=guarded_repo, capture_output=True, text=True
        ).stdout.strip()
        assert after_sha == before_sha, "refs/stash must be unchanged by a blocked drop"
        assert (
            subprocess.run(["git", "cat-file", "-t", before_sha], cwd=guarded_repo, capture_output=True).returncode
            == 0
        ), "the stash commit must still be a live, resolvable object"


class TestDocumentedGaps:
    """Pins the empirically-verified forms this hook CANNOT block.

    `apply` never performs a ref transaction at all -- no hook fires, ever.
    `pop`/`drop` of a non-terminal entry rewrite the reflog directly and
    only ref-update refs/stash to its already-second entry, which git's
    ref-transaction API treats the same as any ordinary ref move; the hook
    has no way to distinguish that from a legitimate branch-ref update. Both
    are asserted here (not just described in a comment) so that if a future
    git version changes this, the test suite -- not an incident -- is what
    notices. This is why `scripts/check_stash_stack_gate.py` exists as a
    detective (not preventive) control for exactly these two cases.
    """

    def test_stash_apply_is_not_blocked(self, guarded_repo: Path) -> None:
        assert _git(guarded_repo, "stash", "apply") == 0

    def test_stash_pop_of_a_non_terminal_entry_is_not_blocked(self, guarded_repo: Path) -> None:
        for msg in ("two", "three"):
            (guarded_repo / "f").write_text(msg + "\n")
            assert _git(guarded_repo, "stash", "push", "-q", "-m", msg, env={"ALLOW_GIT_STASH": "1"}) == 0
        assert _stash_list(guarded_repo).count("stash@{") == 3
        assert _git(guarded_repo, "stash", "pop") == 0
        assert _stash_list(guarded_repo).count("stash@{") == 2

    def test_stash_drop_of_a_non_terminal_entry_is_not_blocked(self, guarded_repo: Path) -> None:
        for msg in ("two", "three"):
            (guarded_repo / "f").write_text(msg + "\n")
            assert _git(guarded_repo, "stash", "push", "-q", "-m", msg, env={"ALLOW_GIT_STASH": "1"}) == 0
        assert _stash_list(guarded_repo).count("stash@{") == 3
        assert _git(guarded_repo, "stash", "drop", "stash@{0}") == 0
        assert _stash_list(guarded_repo).count("stash@{") == 2


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


INSTALLER = REPO_ROOT / "scripts" / "install_git_stash_guard.py"

installer_pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not INSTALLER.is_file(),
    reason="needs git and the installer script",
)


def _load_installer_module():
    """Import install_git_stash_guard.py fresh, so each test gets its own
    module object to monkeypatch -- REPO_ROOT is computed once at import
    time from `Path(__file__)`, so redirecting it to a throwaway target repo
    requires patching the attribute post-import, not the process cwd (a
    subprocess invocation with a different `cwd` does NOT redirect it: the
    script always resolves REPO_ROOT from its own on-disk location, which is
    itself a good safety property -- it can't be tricked into installing
    into an unintended repo by whatever directory happened to invoke it --
    but it means testing against an isolated target repo has to patch the
    module in-process rather than shell out).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("install_git_stash_guard_under_test", INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bare_repo(tmp_path: Path) -> Path:
    """A repo with no hooks installed, so the installer has a clean slate.

    A real git repo (not just a bare `.git/hooks` dir) so `git rev-parse
    --git-common-dir`, which the installer shells out to, resolves.
    """
    repo = tmp_path / "target"
    repo.mkdir()
    assert _git(repo, "init", "-q", ".") == 0
    return repo


def _run_installer(monkeypatch: pytest.MonkeyPatch, repo: Path, argv: list[str]) -> tuple[int, object]:
    """Run the installer's main() against `repo`, in-process, returning
    (exit_code, module) so callers can also inspect module-level state."""
    import sys

    module = _load_installer_module()
    monkeypatch.setattr(module, "REPO_ROOT", repo)
    monkeypatch.setattr(sys, "argv", ["install_git_stash_guard.py", *argv])
    return module.main(), module


@installer_pytestmark
class TestInstallerSelfInstalls:
    """This is what makes the guard 'discoverable and self-installing': a
    fresh worktree (or a repo whose shared hooks/ never got the guard
    copied into it -- the state this repo itself was found in, see the PR
    this test was added in) gets protected by running this script, and
    `make worktree` runs it on every new worktree so the shared hook can
    never silently go missing again.
    """

    def test_check_reports_not_installed_on_a_clean_repo(self, monkeypatch: pytest.MonkeyPatch, bare_repo: Path) -> None:
        code, _ = _run_installer(monkeypatch, bare_repo, ["--check"])
        assert code == 1

    def test_install_writes_the_hook_and_check_then_passes(self, monkeypatch: pytest.MonkeyPatch, bare_repo: Path, capsys: pytest.CaptureFixture) -> None:
        code, _ = _run_installer(monkeypatch, bare_repo, [])
        assert code == 0
        hook = bare_repo / ".git" / "hooks" / "reference-transaction"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o111, "installed hook must be executable"
        assert hook.read_text() == HOOK_SOURCE.read_text()

        check_code, _ = _run_installer(monkeypatch, bare_repo, ["--check"])
        assert check_code == 0

    def test_install_is_idempotent(self, monkeypatch: pytest.MonkeyPatch, bare_repo: Path) -> None:
        first, _ = _run_installer(monkeypatch, bare_repo, [])
        assert first == 0
        second, _ = _run_installer(monkeypatch, bare_repo, [])
        assert second == 0

    def test_refuses_to_overwrite_a_foreign_hook_without_force(self, monkeypatch: pytest.MonkeyPatch, bare_repo: Path) -> None:
        hooks_dir = bare_repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        foreign = hooks_dir / "reference-transaction"
        foreign.write_text("#!/bin/sh\n# not ours\nexit 0\n")

        code, _ = _run_installer(monkeypatch, bare_repo, [])
        assert code != 0
        assert foreign.read_text() == "#!/bin/sh\n# not ours\nexit 0\n", "must not clobber a foreign hook"

        forced_code, _ = _run_installer(monkeypatch, bare_repo, ["--force"])
        assert forced_code == 0
        assert foreign.read_text() == HOOK_SOURCE.read_text()

    def test_installed_hook_actually_blocks_stash_in_the_target_repo(self, monkeypatch: pytest.MonkeyPatch, bare_repo: Path) -> None:
        """End-to-end: run the installer, then prove the repo it installed
        into really does reject `git stash`, closing the loop from
        'installer ran' to 'guard fires'."""
        code, _ = _run_installer(monkeypatch, bare_repo, [])
        assert code == 0
        _git(bare_repo, "config", "user.email", "t@example.invalid")
        _git(bare_repo, "config", "user.name", "t")
        (bare_repo / "f").write_text("a\n")
        assert _git(bare_repo, "add", "f") == 0
        assert _git(bare_repo, "commit", "-qm", "init") == 0
        (bare_repo / "f").write_text("b\n")
        assert _git(bare_repo, "stash") != 0


def test_make_worktree_target_installs_the_guard() -> None:
    """`make worktree` (the documented way new worktrees are created --
    docs/solutions/best-practices/per-workstream-worktree-2026-07-31.md) must
    invoke the installer, so a freshly created worktree -- or a shared hooks/
    directory that was never populated -- is self-healing rather than
    depending on someone remembering to run the installer by hand."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    worktree_target = makefile.split("\nworktree:", 1)[1].split("\n\n", 1)[0]
    assert "install_git_stash_guard.py" in worktree_target
