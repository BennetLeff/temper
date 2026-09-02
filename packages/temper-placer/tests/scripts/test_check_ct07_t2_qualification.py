"""Focused tests for the CT07 candidate-only replay boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_ct07_t2_qualification as gate  # noqa: E402


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    for relative in gate.REQUIRED_PROTECTED_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((relative + "\n").encode())
    for relative in ("pcb/power.kicad_sch", "elec/src/main.ato", "firmware/main.c"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((relative + "\n").encode())
    (tmp_path / gate.OUTPUT_ROOT).mkdir(parents=True, exist_ok=True)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "CT07 test")
    _git(tmp_path, "add", "--all")
    _git(tmp_path, "commit", "-qm", "base")
    commit = _git(tmp_path, "rev-parse", "HEAD")
    pins = [
        {
            "path": relative,
            "sha256": hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest(),
        }
        for relative in gate.REQUIRED_PROTECTED_FILES
    ]
    manifest = {
        "schema_version": 1,
        "base_commit": commit,
        "protected_descriptor": gate.R18_DESCRIPTOR,
        "protected_inputs": pins,
        "construction_id": "ct07-test-construction",
        "construction_digest": "a" * 64,
        "raw_evidence": [],
    }
    manifest_path = tmp_path / gate.OUTPUT_ROOT / "evidence_index.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, manifest


def _install_oracle(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    class FakeOracle:
        @staticmethod
        def evaluate_ct07_t2_qualification_json(value: str) -> str:
            calls.append(value)
            package = json.loads(value)
            return json.dumps(
                {
                    "schema_version": package["schema_version"],
                    "construction_id": package["construction_id"],
                    "construction_digest": package["construction_digest"],
                    "internal_stage": "stopped-indeterminate",
                    "stage": "stopped-indeterminate",
                    "reasons": ["evidence"],
                }
            )

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", FakeOracle)
    return calls


def test_exact_r18_descriptor_is_required_before_replay_io(tmp_path: Path) -> None:
    manifest_path, manifest = _fixture(tmp_path)
    weakened = dict(manifest)
    descriptor = dict(gate.R18_DESCRIPTOR)
    descriptor["required_files"] = list(gate.REQUIRED_PROTECTED_FILES[:-1])
    weakened["protected_descriptor"] = descriptor
    with pytest.raises(gate.QualificationGateError, match="exactly match"):
        gate._validate_r18_descriptor(weakened)


def test_valid_replay_calls_ct07_registration_and_publishes_under_output_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _fixture(tmp_path)
    calls = _install_oracle(monkeypatch)
    output = tmp_path / gate.OUTPUT_ROOT / "decision.json"

    result = gate.replay(manifest_path, output, repo_root=tmp_path)

    assert output.read_text(encoding="utf-8") == result
    assert len(calls) == 1
    payload = json.loads(calls[0])
    assert payload["protected_descriptor"] == gate.R18_DESCRIPTOR
    assert payload["raw_evidence"] == []
    assert payload["evidence_digest"] == hashlib.sha256(b"").hexdigest()


def test_replay_without_explicit_output_is_stdout_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _fixture(tmp_path)
    _install_oracle(monkeypatch)
    result = gate.replay(manifest_path, repo_root=tmp_path)
    assert result.endswith("\n")
    assert not (tmp_path / gate.OUTPUT_ROOT / "internal_decision.json").exists()


def test_base_payload_and_git_visible_inventory_must_match(tmp_path: Path) -> None:
    manifest_path, _ = _fixture(tmp_path)
    (tmp_path / "elec/src/new.ato").write_text("untracked\n", encoding="utf-8")
    with pytest.raises(gate.QualificationGateError, match="inventory drift"):
        gate.replay(manifest_path, repo_root=tmp_path)


def test_protected_source_symlink_is_rejected(tmp_path: Path) -> None:
    manifest_path, _ = _fixture(tmp_path)
    source = tmp_path / "firmware/main.c"
    source.unlink()
    source.symlink_to(tmp_path / "pcb/power.kicad_sch")
    with pytest.raises(gate.QualificationGateError, match="symlink"):
        gate.replay(manifest_path, repo_root=tmp_path)


def test_build_snapshot_requires_the_five_declared_outputs(tmp_path: Path) -> None:
    _fixture(tmp_path)
    build = tmp_path / gate.BUILD_ROOT
    build.mkdir(parents=True)
    (build / "default.csv").write_bytes(b"one")
    with pytest.raises(gate.QualificationGateError, match="five required"):
        gate._validate_build_snapshot(tmp_path)


def test_build_snapshot_allows_preserved_generated_directories(tmp_path: Path) -> None:
    _fixture(tmp_path)
    build = tmp_path / gate.BUILD_ROOT
    build.mkdir(parents=True)
    for name in gate.BUILD_OUTPUTS:
        (build / name).write_bytes(name.encode())
    (build / "footprints").mkdir()
    (build / "footprints" / "generated.kicad_mod").write_bytes(b"footprint")

    gate._validate_build_snapshot(tmp_path)


def test_candidate_publication_normalizes_only_project_root_and_verifies_bytes(
    tmp_path: Path,
) -> None:
    _fixture(tmp_path)
    project = tmp_path / "scratch-candidate"
    build = project / "build"
    build.mkdir(parents=True)
    (build / "default.csv").write_bytes(b"Comment,Designator\r\npart,U1\r\n")
    (build / "default.layouts.json").write_text("{}", encoding="utf-8")
    (build / "default.net").write_text(
        f'(sheetpath (names "{project.resolve().as_posix()}/src/main.ato"))\n',
        encoding="utf-8",
    )

    gate.publish_candidate_build(project, repo_root=tmp_path)
    gate.verify_candidate_build(project, repo_root=tmp_path)
    canonical = tmp_path / gate.OUTPUT_ROOT / "generated"
    assert (canonical / "candidate.csv").read_bytes().endswith(b"\n")
    assert b"\r\n" not in (canonical / "candidate.csv").read_bytes()
    assert gate.CANDIDATE_ROOT.as_posix() in (canonical / "candidate.net").read_text()
    assert project.as_posix() not in (canonical / "candidate.net").read_text()

    (build / "default.layouts.json").write_text('{"drift":true}', encoding="utf-8")
    with pytest.raises(gate.QualificationGateError, match="differs"):
        gate.verify_candidate_build(project, repo_root=tmp_path)


def test_evidence_path_is_read_once_and_bound_to_the_rust_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _fixture(tmp_path)
    evidence = tmp_path / gate.CANDIDATE_ROOT / "evidence" / "capture.bin"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"capture")
    manifest["evidence_files"] = [{"id": "capture-1", "path": str(evidence.relative_to(tmp_path))}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    calls = _install_oracle(monkeypatch)
    original = gate.qualification_replay.read_once
    evidence_reads = 0

    def read_once(*args, **kwargs):
        nonlocal evidence_reads
        if str(args[0]).endswith("capture.bin"):
            evidence_reads += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(gate.qualification_replay, "read_once", read_once)
    gate.replay(manifest_path, repo_root=tmp_path)
    assert evidence_reads == 1
    assert json.loads(calls[0])["raw_evidence"][0]["bytes"] == list(b"capture")


def test_evidence_mutation_after_read_is_rejected_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _fixture(tmp_path)
    evidence = tmp_path / gate.CANDIDATE_ROOT / "evidence.bin"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"before")
    manifest["evidence_files"] = [{"id": "capture-1", "path": str(evidence.relative_to(tmp_path))}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    class MutatingOracle:
        @staticmethod
        def evaluate_ct07_t2_qualification_json(value: str) -> str:
            evidence.write_bytes(b"after")
            package = json.loads(value)
            return json.dumps(
                {
                    "schema_version": package["schema_version"],
                    "construction_id": package["construction_id"],
                    "construction_digest": package["construction_digest"],
                }
            )

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", MutatingOracle)
    output = tmp_path / gate.OUTPUT_ROOT / "decision.json"
    with pytest.raises(gate.QualificationGateError, match="single read"):
        gate.replay(manifest_path, output, repo_root=tmp_path)
    assert not output.exists()


def test_output_must_not_traverse_out_of_candidate_namespace(tmp_path: Path) -> None:
    manifest_path, _ = _fixture(tmp_path)
    with pytest.raises(gate.QualificationGateError, match="escapes"):
        gate.replay(manifest_path, tmp_path / "outside.json", repo_root=tmp_path)


def test_only_named_docs_evidence_path_is_an_allowed_second_publication_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _fixture(tmp_path)
    _install_oracle(monkeypatch)
    canonical = tmp_path / gate.CANONICAL_OUTPUT
    canonical.parent.mkdir(parents=True)

    result = gate.replay(manifest_path, canonical, repo_root=tmp_path)
    assert canonical.read_text(encoding="utf-8") == result

    with pytest.raises(gate.QualificationGateError, match="escapes"):
        gate.replay(
            manifest_path,
            canonical.with_name("not-the-canonical-result.json"),
            repo_root=tmp_path,
        )


def test_committed_evidence_index_replays_through_real_rust_to_canonical_bytes() -> None:
    result = gate.replay(repo_root=gate.REPO_ROOT)
    canonical = (gate.REPO_ROOT / gate.CANONICAL_OUTPUT).read_text(encoding="utf-8")
    internal = (gate.REPO_ROOT / gate.DEFAULT_OUTPUT.relative_to(gate.REPO_ROOT)).read_text(
        encoding="utf-8"
    )
    assert result == canonical == internal
