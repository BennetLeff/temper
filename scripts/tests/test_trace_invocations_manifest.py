"""Tests for the manifest writer in trace_invocations.py.

Regression coverage for the two bugs that left scripts/manifest.yaml
unparseable (see the docstring on update_manifest_imports):

  1. `imports:` was emitted at four spaces, nesting it under `disposition:`
     instead of making it a sibling key -- invalid YAML.
  2. The existing imports block was never consumed, so every run appended
     another copy of it. 436 real imports had grown into 1787 lines.

Both are invisible to the only production consumer, check_manifest_gate.py,
which greps for `path:` and never loads the YAML -- which is why this went
unnoticed. These tests load the YAML, so they cannot miss it the same way.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trace_invocations  # noqa: E402

MANIFEST = {
    "_meta": {"last_audit_date": "2026-06-24", "total_scripts": 2},
    "scripts": [
        {
            "path": "alpha.py",
            "purpose": "does alpha things",
            "category": "keep",
            "disposition": "utility",
            "imports": ["json", "sys"],
        },
        {
            "path": "beta.py",
            "purpose": "does beta things",
            "category": "keep",
            "disposition": "ci-gate",
        },
    ],
}


def _manifest(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(
        yaml.safe_dump(MANIFEST, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setattr(trace_invocations, "MANIFEST", path)
    return path


class TestManifestStaysValid:
    def test_output_is_parseable_yaml(self, tmp_path, monkeypatch):
        path = _manifest(tmp_path, monkeypatch)
        trace_invocations.update_manifest_imports({"alpha.py": ["argparse", "os"]})

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert [e["path"] for e in data["scripts"]] == ["alpha.py", "beta.py"]

    def test_imports_is_a_sibling_of_disposition_not_a_child(
        self, tmp_path, monkeypatch
    ):
        """Bug 1: `imports:` nested under `disposition:` broke the parse."""
        path = _manifest(tmp_path, monkeypatch)
        trace_invocations.update_manifest_imports({"alpha.py": ["argparse"]})

        entry = yaml.safe_load(path.read_text(encoding="utf-8"))["scripts"][0]
        assert entry["imports"] == ["argparse"]
        assert entry["disposition"] == "utility"
        assert not isinstance(entry["disposition"], dict)

    def test_other_fields_survive(self, tmp_path, monkeypatch):
        path = _manifest(tmp_path, monkeypatch)
        trace_invocations.update_manifest_imports({"alpha.py": ["argparse"]})

        entry = yaml.safe_load(path.read_text(encoding="utf-8"))["scripts"][0]
        assert entry["purpose"] == "does alpha things"
        assert entry["category"] == "keep"


class TestIdempotence:
    """Bug 2: repeated runs used to append another copy of the imports list."""

    def test_repeated_runs_do_not_grow_the_file(self, tmp_path, monkeypatch):
        path = _manifest(tmp_path, monkeypatch)
        imports = {"alpha.py": ["argparse", "os"], "beta.py": ["json"]}

        trace_invocations.update_manifest_imports(imports)
        first = path.read_text(encoding="utf-8")
        trace_invocations.update_manifest_imports(imports)
        second = path.read_text(encoding="utf-8")
        trace_invocations.update_manifest_imports(imports)
        third = path.read_text(encoding="utf-8")

        assert first == second == third

    def test_second_run_reports_no_modification(self, tmp_path, monkeypatch):
        _manifest(tmp_path, monkeypatch)
        imports = {"alpha.py": ["argparse"]}

        assert trace_invocations.update_manifest_imports(imports) is True
        assert trace_invocations.update_manifest_imports(imports) is False

    def test_imports_are_replaced_not_accumulated(self, tmp_path, monkeypatch):
        path = _manifest(tmp_path, monkeypatch)

        trace_invocations.update_manifest_imports({"alpha.py": ["argparse"]})
        trace_invocations.update_manifest_imports({"alpha.py": ["os"]})

        entry = yaml.safe_load(path.read_text(encoding="utf-8"))["scripts"][0]
        assert entry["imports"] == ["os"], "stale imports were carried forward"


class TestFailClosed:
    def test_missing_manifest_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(trace_invocations, "MANIFEST", tmp_path / "absent.yaml")
        assert trace_invocations.update_manifest_imports({"a.py": ["os"]}) is False

    def test_malformed_manifest_raises(self, tmp_path, monkeypatch):
        path = tmp_path / "manifest.yaml"
        path.write_text("just a string\n", encoding="utf-8")
        monkeypatch.setattr(trace_invocations, "MANIFEST", path)

        try:
            trace_invocations.update_manifest_imports({"a.py": ["os"]})
        except ValueError as exc:
            assert "scripts" in str(exc)
        else:
            raise AssertionError("expected ValueError on a malformed manifest")
