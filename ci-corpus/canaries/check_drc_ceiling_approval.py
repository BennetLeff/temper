"""Canary fixtures for check_drc_ceiling_approval.py (R42) -- the DRC
ratchet's approval gate (R27 monotone contract).

Builds a real, throwaway git repository per call (condensed from the
git-repo pattern already established in
``scripts/tests/test_check_drc_ceiling_approval.py``) and calls
``run_gate(repo_root)`` directly -- this gate's own logic is fundamentally
git-history-shaped (merge-base diff, commit-message trailer scan), so a
canary that never touches git would not exercise it at all.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# DrcRatchet lives in packages/temper-placer/src -- run_gate() only adds
# <repo_root>/packages/temper-placer/src to sys.path (repo_root being the
# throwaway canary git repo, which has no packages/ dir at all), so this
# mirrors what scripts/tests/test_check_drc_ceiling_approval.py does at
# import time: point sys.path at the REAL repo's package before run_gate
# is ever called, so the import resolves regardless of which repo_root a
# given call is exercising.
_REAL_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLACER_SRC = _REAL_REPO_ROOT / "packages" / "temper-placer" / "src"
if str(_PLACER_SRC) not in sys.path:
    sys.path.insert(0, str(_PLACER_SRC))

BASE_CEILING = {
    "boards": [
        {
            "board_id": "temper",
            "path": "pcb/temper.kicad_pcb",
            "error_ceiling": 1017,
            "warning_ceiling": 762,
            "violations_by_type": {"clearance": 502, "hole_clearance": 120},
            "warnings_by_type": {"silk_overlap": 119},
        }
    ]
}


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _git_output(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _head_sha(repo: Path) -> str:
    """The real, resolvable commit SHA at HEAD of *repo* -- used by seed
    fixtures that need a ``measured_at_commit`` provenance value the real
    gate's git-cat-file resolvability check (``DrcRatchet.
    validate_raise_evidence`` via ``_verify_commits_exist``) will actually
    accept, as opposed to a syntactically-valid-but-dangling placeholder
    like ``"a" * 40``."""
    return _git_output(["rev-parse", "HEAD"], repo)


def _init_repo(root: Path) -> Path:
    _git(["init", "-q", "-b", "work"], root)
    _git(["config", "user.email", "canary@example.com"], root)
    _git(["config", "user.name", "Canary"], root)
    _git(["config", "commit.gpgsign", "false"], root)
    return root


def _write_ceiling(repo: Path, ceiling: dict) -> None:
    d = repo / "power_pcb_dataset"
    d.mkdir(parents=True, exist_ok=True)
    (d / "drc_ceiling.json").write_text(json.dumps(ceiling, indent=2) + "\n")


def _commit(repo: Path, message: str) -> None:
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", message], repo)


def _base_repo(root: Path) -> Path:
    repo = _init_repo(root)
    _write_ceiling(repo, BASE_CEILING)
    (repo / "README.md").write_text("base\n")
    _commit(repo, "base: initial ceiling")
    _git(["branch", "origin/main"], repo)
    return repo


def _state(gate_module, repo: Path) -> str:
    exit_code, _message = gate_module.run_gate(repo)
    if exit_code == gate_module.EXIT_OK:
        return "clean"
    if exit_code == gate_module.EXIT_UNAPPROVED_RAISE:
        return "violation"
    return "error"


def pristine_no_raise(gate_module) -> str:
    """PR branch with an unrelated commit; the ceiling itself never
    changes -- no trailer required, must PASS."""
    with tempfile.TemporaryDirectory() as td:
        repo = _base_repo(Path(td))
        (repo / "README.md").write_text("base + unrelated change\n")
        _commit(repo, "docs: unrelated change")
        return _state(gate_module, repo)


def seed_unapproved_raise(gate_module) -> str:
    """The core defect this gate exists to catch: the aggregate error
    ceiling goes up with no `Ceiling-Approval:` trailer anywhere in the
    PR's commits."""
    with tempfile.TemporaryDirectory() as td:
        repo = _base_repo(Path(td))
        raised = json.loads(json.dumps(BASE_CEILING))
        raised["boards"][0]["error_ceiling"] += 50  # silent regression
        _write_ceiling(repo, raised)
        _commit(repo, "chore: bump ceiling (no trailer, no justification)")
        return _state(gate_module, repo)


def seed_unapproved_raise_with_valid_evidence(gate_module) -> str:
    """A raise that WOULD satisfy the measurement-evidence contract (a
    real board hash, a fresh measured-live provenance record, a non-empty
    `_march` entry) if it ever reached that check -- but still carries no
    `Ceiling-Approval:` trailer anywhere in the PR's commits.

    This isolates the trailer check specifically: `seed_unapproved_raise`
    above also has NO valid evidence, so a mutant that inverts
    `"Ceiling-Approval:" in commit_messages` still gets caught by
    `validate_raise_evidence` immediately afterward for an unrelated
    reason (missing provenance) -- both baseline and mutant land on
    EXIT_UNAPPROVED_RAISE, and the trailer inversion survives invisibly.
    With good evidence already in place, EXIT_OK vs EXIT_UNAPPROVED_RAISE
    depends on the trailer check alone.

    ``measured_at_commit`` must be a REAL, resolvable commit SHA in *this*
    throwaway repo, not merely 40 well-formed hex characters: re-located
    2026-08-11 after `DrcRatchet.validate_raise_evidence` gained its own
    `git cat-file --batch-check` resolvability check (previously that
    verification lived only in `check_measurement_provenance.py` -- see
    that gate's own `verify_commits_exist`, and the dangling-commit
    incident AGENTS.md records). The placeholder `"a" * 40` this fixture
    used before that landed satisfied the old shape-only check but is not
    an object in ANY repo, so once resolvability started being enforced
    here too, this seed started failing `validate_raise_evidence` for an
    unrelated reason (an unresolvable commit) regardless of the trailer
    mutation -- silently reopening exactly the "coarse oracle" blind spot
    this fixture was written to close (see this module's own history:
    `docs/evidence/2026-08-07-gate-mutation-sweep.md` finding 3). Using
    the base commit's real HEAD sha restores the isolation.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        repo = _base_repo(repo)
        real_commit_sha = _head_sha(repo)
        board_content = b"canary-board-content"
        board_path = repo / "pcb" / "temper.kicad_pcb"
        board_path.parent.mkdir(parents=True, exist_ok=True)
        board_path.write_bytes(board_content)
        board_sha = hashlib.sha256(board_content).hexdigest()

        raised = json.loads(json.dumps(BASE_CEILING))
        entry = raised["boards"][0]
        entry["error_ceiling"] += 3
        entry["nondeterministic_error_types"] = {
            "clearance": {"observed": [499, 500, 501], "samples": 120, "note": "only nondeterministic category"}
        }
        entry["provenance"] = {
            "measured_at_commit": real_commit_sha,
            "dirty": False,
            "inputs": [{"path": "pcb/temper.kicad_pcb", "sha256": board_sha}],
            "tool_versions": {"kicad-cli": "10.0.4"},
            "source": "measured-live",
            "measured_via": "canary fixture (120 samples)",
        }
        raised["_march"] = {"2026-08-07": "attributed cause: canary fixture"}
        _write_ceiling(repo, raised)
        _commit(repo, "chore: bump ceiling with full evidence, no trailer")
        return _state(gate_module, repo)
