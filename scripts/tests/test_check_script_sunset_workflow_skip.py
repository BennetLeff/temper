"""Tests for the workflow-reference skip in check_script_sunset.py.

The sunset clock used to WARN on CI gates whose manifest last_run aged past
30 days whenever the invocation graph lacked a caller for them -- and the
graph is a committed artifact that goes stale between regenerations
(measured 2026-08-19: 20 scripts referenced in .github/workflows/*.yml had
no graph caller at all). The fix (script-sprawl cleanup phase 2.4) scans
.github/workflows/ directly and skips the keep-WARNING for any script whose
basename is referenced there, so a stale graph cannot manufacture
false-positive WARNINGs on gates that run on every PR.

These tests pin that behaviour at exactly the boundary where the graph and
the workflows disagree: the fixture graph reports NO callers for both
scripts, and only the workflow reference distinguishes the active gate from
the genuinely stale utility.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_script_sunset  # noqa: E402

TODAY = "2026-08-19"

MANIFEST = """\
_meta:
  last_audit_date: '2026-08-19'
scripts:
- path: active_gate.py
  purpose: runs in CI on every PR
  owner: pipeline
  last_run: '2026-06-01'
  category: keep
  disposition: ci-gate
  imports: []
- path: stale_utility.py
  purpose: no callers anywhere
  owner: pipeline
  last_run: '2026-06-01'
  category: keep
  disposition: utility
  imports: []
"""

# Both scripts have NO graph callers -- the graph is stale by construction.
GRAPH = {"active_gate.py": [], "stale_utility.py": []}

WORKFLOW_WITH_GATE = """\
name: Tests
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - run: uv run python scripts/active_gate.py
"""

WORKFLOW_NESTED_REF = """\
name: Docs
on: [push]
jobs:
  gen:
    runs-on: ubuntu-latest
    steps:
      - run: uv run python packages/temper-placer/scripts/gen_config_reference.py --check
"""


def _run_sunset(
    tmp_path, monkeypatch, capsys, manifest=MANIFEST, graph=None,
    workflows=None,
):
    """Run check_script_sunset.main() against fixture paths."""
    monkeypatch.setattr(check_script_sunset, "MANIFEST", tmp_path / "manifest.yaml")
    monkeypatch.setattr(check_script_sunset, "GRAPH", tmp_path / "invocation_graph.json")
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    monkeypatch.setattr(check_script_sunset, "WORKFLOWS_DIR", wf_dir)
    check_script_sunset.MANIFEST.write_text(manifest)
    check_script_sunset.GRAPH.write_text(json.dumps(graph or GRAPH))
    for name, text in (workflows or {}).items():
        (wf_dir / name).write_text(text)
    monkeypatch.setattr(sys, "argv", ["check_script_sunset.py", "--today", TODAY])
    try:
        rc = check_script_sunset.main()
    except SystemExit as exc:  # main() ends with sys.exit(0)
        rc = exc.code
    return rc, capsys.readouterr().out


class TestWorkflowReferencedGatesAreSkipped:
    def test_gate_in_workflow_skipped_but_stale_utility_still_warns(
        self, tmp_path, monkeypatch, capsys
    ):
        rc, out = _run_sunset(
            tmp_path, monkeypatch, capsys,
            workflows={"tests.yml": WORKFLOW_WITH_GATE},
        )
        assert rc == 0
        assert "active_gate.py" not in out, (
            "workflow-referenced gate must not warn even with a stale graph"
        )
        assert "stale_utility.py" in out, (
            "genuinely stale utility must still warn"
        )

    def test_without_workflow_reference_both_warn(self, tmp_path, monkeypatch, capsys):
        rc, out = _run_sunset(tmp_path, monkeypatch, capsys, workflows={})
        assert rc == 0
        assert "active_gate.py" in out
        assert "stale_utility.py" in out

    def test_nested_path_reference_covered_by_basename(
        self, tmp_path, monkeypatch, capsys
    ):
        """packages/temper-placer/scripts/foo.py must match basename foo.py."""
        rc, out = _run_sunset(
            tmp_path, monkeypatch, capsys,
            manifest=MANIFEST.replace("active_gate.py", "packages/temper-placer/scripts/gen_config_reference.py"),
            graph={"packages/temper-placer/scripts/gen_config_reference.py": [], "stale_utility.py": []},
            workflows={"docs.yml": WORKFLOW_NESTED_REF},
        )
        assert rc == 0
        assert "gen_config_reference" not in out
        assert "stale_utility.py" in out


class TestWorkflowReferenceCollection:
    def test_references_collected_from_all_workflow_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(check_script_sunset, "WORKFLOWS_DIR", tmp_path / "wf")
        check_script_sunset.WORKFLOWS_DIR.mkdir()
        (check_script_sunset.WORKFLOWS_DIR / "a.yml").write_text(
            "run: python scripts/alpha.py\n"
        )
        (check_script_sunset.WORKFLOWS_DIR / "b.yaml").write_text(
            "run: uv run python packages/x/scripts/beta.py\n"
        )
        refs = check_script_sunset.workflow_referenced_scripts()
        assert "alpha.py" in refs
        assert "beta.py" in refs

    def test_missing_workflows_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            check_script_sunset, "WORKFLOWS_DIR", tmp_path / "absent"
        )
        assert check_script_sunset.workflow_referenced_scripts() == set()
