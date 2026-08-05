"""Tests for check_test_baseline_writes.py.

Four groups:

1. ``TestFalsifierOriginalDefect`` -- the task's own falsifier, reconstructed
   verbatim: the ``test_update_baseline_yaml`` body that shipped on ``main``
   until 2026-08-04 must FAIL the gate and name its file and line; the shape
   that replaced it (measure, emit to a caller-supplied scratch path) must
   PASS. This is what stops the gate rotting into something that cannot fail.
2. ``TestSpecificity`` -- correct code must not trip it. A gate that fires on
   correct code is itself a defect (docs/METHODOLOGY.md Sec 5), and the first
   revision of this scanner produced 65 findings against the real suite, every
   one a test writing into a pytest ``tmp_path``.
3. ``TestWriteForms`` -- the write idioms the scanner claims to recognise.
4. ``TestAntiVacuity`` -- the gate must fail closed rather than report success
   when it examined nothing.

Every case runs against a synthetic repo under ``tmp_path``; none touches the
real ``power_pcb_dataset/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_test_baseline_writes import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    main,
)

# The body of packages/temper-placer/tests/router_v6/
# test_temper_production_board_routing.py::test_update_baseline_yaml as it
# existed on main before 2026-08-04, reduced to the parts the scanner reasons
# about. `_REPO_ROOT` is three parents up from the test file, exactly as there.
ORIGINAL_DEFECT = """\
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BASELINE_PATH = _REPO_ROOT / "power_pcb_dataset" / "baselines" / "temper_production_baseline.yaml"

_ROUTING_RECORD: dict = {}


def test_update_baseline_yaml():
    with open(_BASELINE_PATH) as f:
        doc = yaml.safe_load(f) or {}
    doc["router_v6_routing"] = dict(_ROUTING_RECORD)
    with open(_BASELINE_PATH, "w") as f:
        yaml.safe_dump(doc, f, default_flow_style=False, sort_keys=False)
"""

# The shape that replaced it: measure, then emit to a caller-supplied path.
FIXED_SHAPE = """\
import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_ROUTING_RECORD: dict = {}


def _emit_routing_record() -> None:
    out_path = os.environ.get("TEMPER_ROUTING_RECORD_OUT")
    if not out_path:
        return
    Path(out_path).write_text(json.dumps(_ROUTING_RECORD))


def test_route_pcb_production_board():
    _ROUTING_RECORD.update({"routed_nets": 71})
    _emit_routing_record()
"""


def make_repo(tmp_path: Path, test_sources: dict[str, str] | None = None) -> Path:
    """Build a synthetic repo with a protected artifact and a tests/ tree."""
    repo = tmp_path / "repo"
    baselines = repo / "power_pcb_dataset" / "baselines"
    baselines.mkdir(parents=True)
    (baselines / "temper_production_baseline.yaml").write_text(
        "# rationale header\nrouter_v6_routing:\n  routed_nets: 71\n"
    )
    (repo / "power_pcb_dataset" / "drc_ceiling.json").write_text('{"boards": []}')

    tests_dir = repo / "packages" / "demo" / "tests"
    tests_dir.mkdir(parents=True)
    for name, source in (
        test_sources or {"test_placeholder.py": "def test_ok():\n    pass\n"}
    ).items():
        (tests_dir / name).write_text(source)
    return repo


def run_gate(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    exit_code = main(["--repo-root", str(repo)])
    captured = capsys.readouterr()
    return exit_code, captured.out + captured.err


class TestFalsifierOriginalDefect:
    """The 2026-08-04 defect, reconstructed. Must fail; its fix must pass."""

    def test_original_defect_is_caught(self, tmp_path, capsys):
        repo = make_repo(tmp_path, {"test_temper_production_board_routing.py": ORIGINAL_DEFECT})

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_VIOLATION
        assert "test_temper_production_board_routing.py" in output
        assert "power_pcb_dataset/baselines/temper_production_baseline.yaml" in output
        assert "open() for writing" in output

    def test_violation_names_the_line(self, tmp_path, capsys):
        repo = make_repo(tmp_path, {"test_temper_production_board_routing.py": ORIGINAL_DEFECT})

        _, output = run_gate(repo, capsys)

        write_line = (
            ORIGINAL_DEFECT.split("\n").index('    with open(_BASELINE_PATH, "w") as f:') + 1
        )
        assert f"test_temper_production_board_routing.py:{write_line}" in output

    def test_fixed_shape_passes(self, tmp_path, capsys):
        repo = make_repo(tmp_path, {"test_temper_production_board_routing.py": FIXED_SHAPE})

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_OK, output

    def test_reading_the_baseline_is_allowed(self, tmp_path, capsys):
        source = """\
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BASELINE_PATH = _REPO_ROOT / "power_pcb_dataset" / "baselines" / "temper_production_baseline.yaml"


def test_asserts_against_the_baseline():
    with open(_BASELINE_PATH) as f:
        doc = yaml.safe_load(f)
    assert doc["router_v6_routing"]["routed_nets"] == 71
"""
        repo = make_repo(tmp_path, {"test_reads.py": source})

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_OK, output


class TestSpecificity:
    """Correct code must not trip the gate."""

    def test_tmp_path_synthetic_repo_is_not_a_violation(self, tmp_path, capsys):
        source = """\
def test_builds_a_fake_repo(tmp_path):
    baselines_dir = tmp_path / "power_pcb_dataset" / "baselines"
    baselines_dir.mkdir(parents=True)
    (baselines_dir / "temper_production_baseline.yaml").write_text("routed_nets: 1\\n")
"""
        repo = make_repo(tmp_path, {"test_synthetic.py": source})

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_OK, output

    def test_relpath_constant_joined_onto_a_fixture_is_not_a_violation(self, tmp_path, capsys):
        """The idiom that produced this scanner's last false positive.

        ``CEILING_RELPATH`` is a path *fragment*: which root it lands on is
        decided by whatever it is joined to, and here that is a tmp_path repo.
        """
        source = """\
CEILING_RELPATH = "power_pcb_dataset/drc_ceiling.json"


def test_malformed_json_fails_closed(tmp_path):
    repo = tmp_path / "repo"
    (repo / CEILING_RELPATH).parent.mkdir(parents=True)
    (repo / CEILING_RELPATH).write_text("{ not: valid json ]")
"""
        repo = make_repo(tmp_path, {"test_fragment.py": source})

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_OK, output

    def test_writing_an_unprotected_repo_path_is_not_a_violation(self, tmp_path, capsys):
        source = """\
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_writes_somewhere_harmless():
    (_REPO_ROOT / "build" / "scratch.txt").write_text("fine")
"""
        repo = make_repo(tmp_path, {"test_harmless.py": source})

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_OK, output


class TestWriteForms:
    """Each write idiom the scanner advertises must actually be detected."""

    @pytest.mark.parametrize(
        "statement",
        [
            '_BASELINE_PATH.write_text("x")',
            '_BASELINE_PATH.write_bytes(b"x")',
            "_BASELINE_PATH.unlink()",
            '_BASELINE_PATH.open("w").write("x")',
            'open(_BASELINE_PATH, "a").write("x")',
            'open(_BASELINE_PATH, mode="w")',
            "shutil.copy(other, _BASELINE_PATH)",
            "os.remove(_BASELINE_PATH)",
        ],
    )
    def test_write_form_is_detected(self, tmp_path, capsys, statement):
        source = (
            "import os\n"
            "import shutil\n"
            "from pathlib import Path\n\n"
            "_REPO_ROOT = Path(__file__).resolve().parent.parent.parent\n"
            '_BASELINE_PATH = _REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json"\n'
            'other = _REPO_ROOT / "somewhere.json"\n\n\n'
            "def test_writes():\n"
            f"    {statement}\n"
        )
        repo = make_repo(tmp_path, {"test_forms.py": source})

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_VIOLATION, f"{statement!r} was not detected:\n{output}"
        assert "power_pcb_dataset/drc_ceiling.json" in output


class TestAntiVacuity:
    """The gate must fail closed rather than pass having examined nothing."""

    def test_no_protected_artifacts_is_a_gate_error(self, tmp_path, capsys):
        repo = tmp_path / "empty_repo"
        (repo / "packages" / "demo" / "tests").mkdir(parents=True)
        (repo / "packages" / "demo" / "tests" / "test_x.py").write_text(
            "def test_ok():\n    pass\n"
        )

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_GATE_ERROR
        assert "zero files" in output
        assert "vacuously" in output

    def test_no_test_files_is_a_gate_error(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        baselines = repo / "power_pcb_dataset" / "baselines"
        baselines.mkdir(parents=True)
        (baselines / "b.yaml").write_text("x: 1\n")

        exit_code, output = run_gate(repo, capsys)

        assert exit_code == EXIT_GATE_ERROR
        assert "zero test files" in output

    def test_real_repo_registry_is_non_empty(self):
        """Guards against the registry silently matching nothing in-tree."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from _lib.protected_artifacts import protected_paths
        from _lib.repo import find_repo_root

        repo_root = find_repo_root(Path(__file__).resolve().parent)
        paths = protected_paths(repo_root)

        assert len(paths) > 10, f"registry matched only {len(paths)} files"
        relpaths = {p.relative_to(repo_root).as_posix() for p in paths}
        assert "power_pcb_dataset/drc_ceiling.json" in relpaths
        assert "power_pcb_dataset/baselines/temper_production_baseline.yaml" in relpaths
