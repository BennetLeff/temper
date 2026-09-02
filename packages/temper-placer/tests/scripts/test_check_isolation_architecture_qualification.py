"""Focused offline tests for the isolation qualification replay gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_isolation_architecture_qualification as gate  # noqa: E402


REAL_MANIFEST = (
    Path(__file__).resolve().parents[4]
    / "power_pcb_dataset"
    / "isolation_architecture_candidates.json"
)


def _fake_oracle(monkeypatch, *, mutate: Path | None = None, output_mutator=None):
    """Install a fake boundary that records the runner's Rust call shape."""

    calls: list[str] = []

    class FakeOracle:
        @staticmethod
        def evaluate_isolation_qualification_json(value: str) -> str:
            calls.append(value)
            if mutate is not None:
                mutate.write_bytes(mutate.read_bytes() + b"changed")
            payload = json.loads(value)
            result = {
                "schema_version": payload["schema_version"],
                "campaign_id": payload["campaign_id"],
                "provenance": payload["provenance"],
                "corridor_requirement_mm": payload["corridor_requirement_mm"],
                "protected_inputs": payload["protected_inputs"],
                "candidates": [
                    {"candidate": candidate, "verdict": "qualified", "reasons": []}
                    for candidate in payload["candidates"]
                ],
            }
            if output_mutator is not None:
                output_mutator(result)
            return json.dumps(result, indent=2)

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", FakeOracle)
    return calls


def _copy_protected_set(tmp_path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for relative in gate.PROTECTED_PATHS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"fixture:{relative}".encode())
        pins[relative] = gate.sha256_file(target)
    return pins


def _fixture_manifest(tmp_path: Path) -> dict:
    pins = _copy_protected_set(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Qualification Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture base"], cwd=tmp_path, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    return {
        "schema_version": 1,
        "campaign_id": "fixture",
        "provenance": {
            "commit": commit,
            "dirty": True,
        },
        "corridor_requirement_mm": 12.6,
        "protected_inputs": [
            {"path": path, "sha256": pins[path]} for path in gate.PROTECTED_PATHS
        ],
        "candidates": [],
    }


def _fixture_candidate() -> dict:
    return {
        "candidate_id": "fixture-candidate",
        "family": "replacement",
        "domain": "sensing",
        "manufacturer": "Fixture",
        "part_number": "FIX-1",
        "lifecycle_status": "active",
        "sourcing_status": "approved",
        "package": "FIX-PKG",
        "footprint_provenance": "fixture-footprint",
        "evidence_as_of": "2026-09-01",
        "datasheet": {"kind": "fixture", "url": "https://fixture.invalid/datasheet", "revision": "fixture-1", "retrieved_at": "2026-09-01", "sha256": "a" * 64},
        "certification_references": [],
        "axes": [{"code": "fixture.axis", "status": "pending", "reason_code": "fixture.pending", "explanation": "fixture evidence"}],
    }


def test_committed_manifest_covers_bounded_families_domains_and_t2_state():
    manifest = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["provenance"] == {
        "commit": "85b4e400572a77d18f0ee6c644a532ab0a55dd8e",
        "dirty": True,
    }
    assert {item["family"] for item in manifest["candidates"]} == {
        "retain-with-slot",
        "replacement",
        "hybrid",
    }
    assert {item["domain"] for item in manifest["candidates"]} == {"sensing", "gate-drive"}
    t2 = next(item for item in manifest["candidates"] if "t2" in item["candidate_id"])
    coverage = next(axis for axis in t2["axes"] if axis["code"] == "sensing.coverage_disposition")
    assert coverage["status"] == "pending"
    assert "DNF" in coverage["explanation"]
    expected_gaps = {
        "sensing-retain-slot-t1-cst3015": 9.1,
        "sensing-retain-slot-t2-cst3015-dnf": 9.1,
        "gate-retain-slot-u6-ucc21550": 8.1,
        "gate-hybrid-ucc21550-edge-slot": 8.1,
    }
    for candidate_id, expected_gap in expected_gaps.items():
        candidate = next(item for item in manifest["candidates"] if item["candidate_id"] == candidate_id)
        geometry = next(
            axis for axis in candidate["axes"] if axis["code"] == "geometry.straight_corridor"
        )
        assert geometry["status"] == "fail"
        assert geometry["measured_mm"] == expected_gap
        assert geometry["required_mm"] == 12.6

    aperture = next(
        item for item in manifest["candidates"] if item["candidate_id"] == "sensing-hybrid-aperture-ct07-t2"
    )
    aperture_geometry = next(
        axis for axis in aperture["axes"] if axis["code"] == "geometry.straight_corridor"
    )
    assert aperture_geometry["status"] == "pending"
    assert "measured_mm" not in aperture_geometry
    assert "13.2655" in next(
        axis for axis in aperture["axes"] if axis["code"] == "geometry.alternate_authority"
    )["explanation"]

    dww16 = next(
        item
        for item in manifest["candidates"]
        if item["candidate_id"] == "gate-replacement-iso7741fqdwwrq1"
    )
    dww16_geometry = next(
        axis for axis in dww16["axes"] if axis["code"] == "geometry.straight_corridor"
    )
    assert dww16_geometry["status"] == "pending"
    assert "14.5" in dww16_geometry["explanation"]
    assert "measured_mm" not in dww16_geometry

    for candidate in manifest["candidates"]:
        if candidate["family"] != "replacement":
            geometry = next(
                axis for axis in candidate["axes"] if axis["code"] == "geometry.straight_corridor"
            )
            assert geometry["status"] != "pass"


def test_replay_is_offline_deterministic_and_does_not_mutate_protected_inputs(tmp_path, monkeypatch):
    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "decision.json"
    calls = _fake_oracle(monkeypatch)

    first = gate.replay(manifest_path, output, repo_root=tmp_path)
    before = {path: gate.sha256_file(tmp_path / path) for path in gate.PROTECTED_PATHS}
    second = gate.replay(manifest_path, tmp_path / "decision-2.json", repo_root=tmp_path)
    after = {path: gate.sha256_file(tmp_path / path) for path in gate.PROTECTED_PATHS}

    assert first == second == output.read_text(encoding="utf-8")
    assert json.loads(first)["provenance"] == manifest["provenance"]
    assert before == after
    assert len(calls) == 2


def test_replay_fails_when_a_protected_input_changes_mid_run(tmp_path, monkeypatch):
    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    target = tmp_path / gate.PROTECTED_PATHS[0]
    _fake_oracle(monkeypatch, mutate=target)

    with pytest.raises(gate.QualificationGateError, match="changed during replay|pin mismatch"):
        gate.replay(manifest_path, tmp_path / "decision.json", repo_root=tmp_path)
    assert not (tmp_path / "decision.json").exists()


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda result: result.pop("provenance"), "provenance"),
        (lambda result: result.update({"campaign_id": "wrong-campaign"}), "campaign_id"),
        (
            lambda result: result.update(
                {"candidates": [{"candidate": {"candidate_id": "unexpected"}}]}
            ),
            "candidate identity set",
        ),
    ],
)
def test_replay_rejects_missing_or_mismatched_rust_output(
    tmp_path, monkeypatch, mutator, message
):
    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _fake_oracle(monkeypatch, output_mutator=mutator)

    with pytest.raises(gate.QualificationGateError, match=message):
        gate.replay(manifest_path, tmp_path / "decision.json", repo_root=tmp_path)
    assert not (tmp_path / "decision.json").exists()


def test_changed_file_with_synchronized_pin_still_fails_against_provenance_base(
    tmp_path, monkeypatch
):
    manifest = _fixture_manifest(tmp_path)
    target = tmp_path / gate.PROTECTED_PATHS[0]
    target.write_bytes(target.read_bytes() + b"changed after base commit")
    for item in manifest["protected_inputs"]:
        if item["path"] == gate.PROTECTED_PATHS[0]:
            item["sha256"] = gate.sha256_file(target)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    calls = _fake_oracle(monkeypatch)

    with pytest.raises(gate.QualificationGateError, match="does not match provenance base"):
        gate.replay(manifest_path, tmp_path / "decision.json", repo_root=tmp_path)
    assert not calls
    assert not (tmp_path / "decision.json").exists()


def test_replay_refuses_to_overwrite_protected_input(tmp_path, monkeypatch):
    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _fake_oracle(monkeypatch)

    with pytest.raises(gate.QualificationGateError, match="protected input"):
        gate.replay(
            manifest_path,
            tmp_path / gate.PROTECTED_PATHS[0],
            repo_root=tmp_path,
        )


def test_replay_rejects_output_hardlinked_to_protected_input(tmp_path, monkeypatch):
    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    protected = tmp_path / gate.PROTECTED_PATHS[0]
    original = protected.read_bytes()
    hardlink = tmp_path / "hardlink-output.json"
    os.link(protected, hardlink)
    _fake_oracle(monkeypatch)

    with pytest.raises(gate.QualificationGateError, match="sharing protected input inode"):
        gate.replay(manifest_path, hardlink, repo_root=tmp_path)
    assert protected.read_bytes() == original


def test_replay_detects_protected_inode_mutation_after_output_write(tmp_path, monkeypatch):
    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    protected = tmp_path / gate.PROTECTED_PATHS[0]
    original = protected.read_bytes()
    output = tmp_path / "decision.json"
    _fake_oracle(monkeypatch)
    original_replace = os.replace

    def replace_then_mutate(source, destination, *args, **kwargs):
        result = original_replace(source, destination, *args, **kwargs)
        protected.write_bytes(protected.read_bytes() + b"unexpected mutation")
        return result

    monkeypatch.setattr(os, "replace", replace_then_mutate)
    try:
        with pytest.raises(gate.QualificationGateError, match="changed during decision-package write"):
            gate.replay(manifest_path, output, repo_root=tmp_path)
    finally:
        protected.write_bytes(original)
    assert protected.read_bytes() == original


@pytest.mark.parametrize("swap_kind", ["symlink", "hardlink"])
def test_replay_atomic_publication_survives_output_link_swap(tmp_path, monkeypatch, swap_kind):
    """A link swap after preflight must not redirect output bytes into an input."""

    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    protected = tmp_path / gate.PROTECTED_PATHS[0]
    original = protected.read_bytes()
    output = tmp_path / "decision.json"
    _fake_oracle(monkeypatch)
    original_fdopen = os.fdopen
    swapped = False

    def swap_before_write(fd, *args, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            if swap_kind == "symlink":
                output.symlink_to(protected)
            else:
                os.link(protected, output)
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", swap_before_write)
    result = gate.replay(manifest_path, output, repo_root=tmp_path)

    assert swapped
    assert protected.read_bytes() == original
    assert output.is_file()
    assert not output.is_symlink()
    assert output.read_text(encoding="utf-8") == result


def test_replay_fails_closed_when_output_parent_is_replaced(tmp_path, monkeypatch):
    """A parent namespace swap cannot redirect publication into an input dir."""

    manifest = _fixture_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    protected = tmp_path / gate.PROTECTED_PATHS[0]
    original = protected.read_bytes()
    output_parent = tmp_path / "output-parent"
    output_parent.mkdir()
    output = output_parent / protected.name
    moved_parent = tmp_path / "moved-output-parent"
    _fake_oracle(monkeypatch)
    original_open = os.open
    swapped = False

    def open_then_replace_parent(path, flags, *args, **kwargs):
        nonlocal swapped
        result = original_open(path, flags, *args, **kwargs)
        if (
            not swapped
            and kwargs.get("dir_fd") is not None
        ):
            swapped = True
            output_parent.rename(moved_parent)
            output_parent.symlink_to(protected.parent, target_is_directory=True)
        return result

    monkeypatch.setattr(os, "open", open_then_replace_parent)
    with pytest.raises(gate.QualificationGateError, match="output parent (?:changed|moved)"):
        gate.replay(manifest_path, output, repo_root=tmp_path)

    assert swapped
    assert protected.read_bytes() == original


@pytest.mark.parametrize("field", ["family", "domain", "package", "axis"])
def test_replay_rejects_mutated_same_id_candidate_payload(tmp_path, monkeypatch, field):
    manifest = _fixture_manifest(tmp_path)
    candidate = _fixture_candidate()
    manifest["candidates"] = [candidate]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def mutate(result):
        returned = result["candidates"][0]["candidate"]
        if field == "axis":
            returned["axes"][0]["explanation"] = "mutated fixture evidence"
        elif field == "package":
            returned[field] = "MUTATED-PKG"
        else:
            returned[field] = "mutated"

    _fake_oracle(monkeypatch, output_mutator=mutate)
    with pytest.raises(gate.QualificationGateError, match="candidate payload does not match"):
        gate.replay(manifest_path, tmp_path / "decision.json", repo_root=tmp_path)
    assert not (tmp_path / "decision.json").exists()


def test_protected_set_is_exact_and_pins_are_real_sha256(tmp_path):
    manifest = _fixture_manifest(tmp_path)
    current = gate.protected_hashes(manifest, tmp_path)
    assert tuple(current) == gate.PROTECTED_PATHS
    assert all(len(value) == 64 for value in current.values())


def test_local_evidence_digest_mismatch_fails_closed(tmp_path):
    source = tmp_path / "evidence.md"
    source.write_text("reviewed bytes", encoding="utf-8")
    manifest = {
        "candidates": [
            {
                "candidate_id": "fixture",
                "datasheet": {
                    "url": "evidence.md",
                    "revision": "review-1",
                    "retrieved_at": "2026-09-01",
                    "sha256": "0" * 64,
                },
                "certification_references": [],
            }
        ]
    }
    with pytest.raises(gate.QualificationGateError, match="evidence digest mismatch"):
        gate._validate_evidence_references(manifest, tmp_path)


def _geometry_source_manifest(tmp_path: Path, *, commit_source: bool, status: str = "pass") -> dict:
    source = tmp_path / "geometry.md"
    source.write_text("reviewed geometry bytes", encoding="utf-8")
    source_digest = gate.sha256_file(source)
    pins = _copy_protected_set(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Qualification Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    if not commit_source:
        subprocess.run(["git", "reset", "-q", "geometry.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture base"], cwd=tmp_path, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    return {
        "schema_version": 1,
        "campaign_id": "fixture",
        "provenance": {"commit": commit, "dirty": True},
        "corridor_requirement_mm": 12.6,
        "protected_inputs": [
            {"path": path, "sha256": pins[path]} for path in gate.PROTECTED_PATHS
        ],
        "candidates": [
            {
                "candidate_id": "fixture",
                "datasheet": {
                    "url": "geometry.md",
                    "revision": "review-1",
                    "retrieved_at": "2026-09-01",
                    "sha256": source_digest,
                },
                "certification_references": [],
                "axes": [
                    {
                        "code": "geometry.straight_corridor",
                        "status": status,
                        "source": {"path": "geometry.md", "sha256": source_digest},
                    }
                ],
            }
        ],
    }


def test_geometry_source_must_match_current_and_base_bytes(tmp_path):
    manifest = _geometry_source_manifest(tmp_path, commit_source=True)
    gate._validate_geometry_sources(manifest, tmp_path)

    source = tmp_path / "geometry.md"
    source.write_text("changed bytes", encoding="utf-8")
    with pytest.raises(gate.QualificationGateError, match="geometry source digest mismatch"):
        gate._validate_geometry_sources(manifest, tmp_path)

    changed_digest = gate.sha256_file(source)
    manifest["candidates"][0]["datasheet"]["sha256"] = changed_digest
    manifest["candidates"][0]["axes"][0]["source"]["sha256"] = changed_digest
    with pytest.raises(gate.QualificationGateError, match="does not match provenance base"):
        gate._validate_geometry_sources(manifest, tmp_path)


def test_new_geometry_source_can_only_be_pending(tmp_path):
    manifest = _geometry_source_manifest(tmp_path, commit_source=False)
    with pytest.raises(gate.QualificationGateError, match="must remain pending"):
        gate._validate_geometry_sources(manifest, tmp_path)

    manifest["candidates"][0]["axes"][0]["status"] = "pending"
    gate._validate_geometry_sources(manifest, tmp_path)


def test_real_extension_replay_matches_committed_decision_package(tmp_path):
    pytest.importorskip("temper_quality_oracle")
    output = tmp_path / "decision.json"
    result = gate.replay(REAL_MANIFEST, output)
    expected = (
        REAL_MANIFEST.parents[1]
        / "docs"
        / "evidence"
        / "2026-09-01-isolation-component-architecture-qualification.json"
    ).read_bytes()
    assert result.encode("utf-8") == expected
    assert output.read_bytes() == expected
