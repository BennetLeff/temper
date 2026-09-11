"""Focused tests for the split-board sealed replay adapter."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
REPO_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import check_split_board_feasibility as replay  # noqa: E402


def _package() -> dict:
    return {
        "schema_version": 1,
        "candidate_id": "fixture-u1",
        "evaluator_identity": "split-board-feasibility-admission-v1",
        "joint_contract_digest": "a" * 64,
        "upstream_decision": {"verdict": "stopped-indeterminate", "reasons": ["missing.authority"]},
        "candidate_family": {"members": [], "exhausted": False},
    }


def test_fixture_replay_delegates_to_rust_and_preserves_stop(monkeypatch, tmp_path: Path):
    class FakeOracle:
        @staticmethod
        def evaluate_split_board_feasibility_json(payload: str) -> str:
            value = json.loads(payload)
            return json.dumps(
                {
                    "candidate_id": value["candidate_id"],
                    "verdict": "stopped-indeterminate",
                    "geometry_admitted": False,
                }
            )

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", FakeOracle)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(_package()), encoding="utf-8")
    result = replay.replay(fixture, repo_root=tmp_path, fixture_mode=True)
    assert result["verdict"] == "stopped-indeterminate"
    assert result["geometry_admitted"] is False


def test_fixture_cannot_publish(tmp_path: Path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(_package()), encoding="utf-8")
    with pytest.raises(replay.SplitBoardReplayError, match="cannot publish"):
        replay.replay(fixture, tmp_path / "out.json", repo_root=tmp_path, fixture_mode=True)


def test_fixture_requires_registered_evaluator(monkeypatch, tmp_path: Path):
    class EmptyOracle:
        pass

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", EmptyOracle)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(_package()), encoding="utf-8")
    with pytest.raises(replay.SplitBoardReplayError, match="registration"):
        replay.replay(fixture, repo_root=tmp_path, fixture_mode=True)


def _copy_live_inputs(tmp_path: Path) -> Path:
    """Build a read-only test repository containing only the live U9 inputs."""

    relative_trees = (
        replay.QUALIFICATION_ROOT,
        replay.U9_ROOT,
        Path("power_pcb_dataset/qualification/iso7741_gate_drive"),
        Path("power_pcb_dataset/qualification/ct07_t2"),
    )
    relative_files = (
        replay.U9_EXTERNAL_PROTECTED_PATHS
    )
    for relative in relative_trees:
        shutil.copytree(REPO_ROOT / relative, tmp_path / relative)
    for relative in relative_files:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)
    return tmp_path


def _stub_live_context(monkeypatch, root: Path) -> None:
    """Keep live replay tests focused while preserving input composition."""

    monkeypatch.setattr(replay, "_verify_manifest_protected_pins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(replay, "_verify_protected_descriptor", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        replay.qualification_replay,
        "snapshot_paths",
        lambda *_args, **_kwargs: {"stable": "digest"},
    )


def test_live_replay_calls_canonical_u9_and_rejects_byte_divergence(
    monkeypatch, tmp_path: Path
):
    root = _copy_live_inputs(tmp_path)
    import check_isolation_joint_qualification as joint

    published = json.loads((root / replay.U9_DECISION).read_text(encoding="utf-8"))
    divergent = {**published, "canonical_probe": "divergent"}
    calls: list[Path] = []
    real_replay_u9 = joint.replay_u9

    def recording_replay_u9(**kwargs):
        calls.append(kwargs["root"])
        replayed = real_replay_u9(**kwargs)
        return {**replayed, "canonical_probe": "divergent"}

    _stub_live_context(monkeypatch, root)
    # ``compose_input`` imports the canonical package-qualified symbol.  Some
    # test environments also expose the scripts directory as a top-level path,
    # which can otherwise load a second module object under the short name.
    monkeypatch.setitem(sys.modules, "scripts.check_isolation_joint_qualification", joint)
    import scripts

    monkeypatch.setattr(scripts, "check_isolation_joint_qualification", joint, raising=False)
    monkeypatch.setattr(joint, "evaluate_u9", lambda _package: divergent)
    monkeypatch.setattr(joint, "replay_u9", recording_replay_u9)

    with pytest.raises(replay.SplitBoardReplayError, match="byte-match"):
        replay.replay(repo_root=root, fixture_mode=False, mode="admission")
    assert calls == [root]


def _stub_live_evaluators(monkeypatch, root: Path, *, terminal_result=None):
    import check_isolation_joint_qualification as joint

    committed_u9 = json.loads((root / replay.U9_DECISION).read_text(encoding="utf-8"))
    admission = json.loads((root / replay.QUALIFICATION_ROOT / "admission_decision.json").read_text(encoding="utf-8"))
    terminal = terminal_result or json.loads(
        (root / replay.QUALIFICATION_ROOT / "decision.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(joint, "evaluate_u9", lambda _package: committed_u9)
    evaluations: list[dict] = []

    def evaluate(package):
        evaluations.append(package)
        return admission if package["evaluation_mode"] == "admission" else terminal

    monkeypatch.setattr(replay, "_evaluate", evaluate)
    _stub_live_context(monkeypatch, root)
    return evaluations, admission, terminal


@pytest.mark.parametrize("mode", ["both", "terminal"])
def test_live_terminal_assembly_binds_all_u7_sources_and_eight_bindings(
    monkeypatch, tmp_path: Path, mode: str
):
    root = _copy_live_inputs(tmp_path)
    evaluations, _, terminal = _stub_live_evaluators(monkeypatch, root)

    result = replay.replay(repo_root=root, fixture_mode=False, mode=mode)

    assert result == terminal
    terminal_package = next(
        package for package in evaluations if package["evaluation_mode"] == "terminal"
    )
    expected_source_names = {"manifest", "admission_decision", "evidence_index", "owner_signoffs"}
    assert set(terminal_package["u7_source_bytes"]) == expected_source_names
    for name in expected_source_names:
        expected = (root / replay.QUALIFICATION_ROOT / f"{name}.json").read_bytes()
        assert bytes(terminal_package["u7_source_bytes"][name]) == expected
    bindings = terminal_package["terminal_context"]["bindings"]
    expected_binding_paths = {
        "admission_decision": (replay.QUALIFICATION_ROOT / "admission_decision.json").as_posix(),
        "manifest": (replay.QUALIFICATION_ROOT / "manifest.json").as_posix(),
        "upstream_joint_decision": replay.U9_DECISION.as_posix(),
        "upstream_joint_contract": replay.U9_CONTRACT.as_posix(),
        "upstream_joint_manifest": replay.U9_MANIFEST.as_posix(),
        "upstream_combined_candidate": (
            replay.U9_ROOT / "combined_candidate.json"
        ).as_posix(),
        "evidence_index": (replay.QUALIFICATION_ROOT / "evidence_index.json").as_posix(),
        "owner_signoffs": (replay.QUALIFICATION_ROOT / "owner_signoffs.json").as_posix(),
    }
    assert set(bindings) == set(expected_binding_paths)
    for name, expected_path in expected_binding_paths.items():
        binding = bindings[name]
        assert binding["path"] == expected_path
        bound_path = root / expected_path
        assert binding["sha256"] == hashlib.sha256(bound_path.read_bytes()).hexdigest()


def test_live_terminal_byte_mismatch_fails_closed(monkeypatch, tmp_path: Path):
    root = _copy_live_inputs(tmp_path)
    divergent = {"verdict": "stopped-indeterminate", "terminal_probe": "divergent"}
    _stub_live_evaluators(monkeypatch, root, terminal_result=divergent)

    with pytest.raises(replay.SplitBoardReplayError, match="byte-match"):
        replay.replay(repo_root=root, fixture_mode=False, mode="terminal")


def test_live_terminal_protected_set_mutation_fails_closed(monkeypatch, tmp_path: Path):
    root = _copy_live_inputs(tmp_path)
    _stub_live_evaluators(monkeypatch, root)
    snapshots = iter(({"stable": "before"}, {"stable": "after"}))
    monkeypatch.setattr(
        replay.qualification_replay,
        "snapshot_paths",
        lambda *_args, **_kwargs: next(snapshots),
    )

    with pytest.raises(replay.SplitBoardReplayError, match="changed during replay"):
        replay.replay(repo_root=root, fixture_mode=False, mode="terminal")


def test_protected_paths_keep_admission_and_terminal_sets_distinct():
    manifest = {"inputs": {}}
    admission_paths = {
        path.as_posix() for path in replay._protected_paths(manifest)
    }
    terminal_paths = {
        path.as_posix()
        for path in replay._protected_paths(manifest, include_u7=True)
    }
    admission_artifacts = {
        (replay.QUALIFICATION_ROOT / "manifest.json").as_posix(),
        (replay.QUALIFICATION_ROOT / "admission_decision.json").as_posix(),
    }
    terminal_only_artifacts = {
        (replay.QUALIFICATION_ROOT / "evidence_index.json").as_posix(),
        (replay.QUALIFICATION_ROOT / "owner_signoffs.json").as_posix(),
    }
    assert admission_artifacts <= admission_paths
    assert terminal_only_artifacts.isdisjoint(admission_paths)
    assert admission_artifacts | terminal_only_artifacts <= terminal_paths


@pytest.mark.parametrize("inputs", [None, [], "malformed", 42])
def test_live_replay_rejects_malformed_manifest_inputs(
    monkeypatch, tmp_path: Path, inputs
):
    def read_json(path: Path, *, root: Path):
        if path == root / replay.U9_MANIFEST:
            return {"inputs": inputs}, b"{}\n"
        return {}, b"{}\n"

    monkeypatch.setattr(replay, "_read_json", read_json)
    with pytest.raises(replay.SplitBoardReplayError, match="inputs must be a mapping"):
        replay.replay(repo_root=tmp_path, fixture_mode=False, mode="admission")


def test_live_replay_normalizes_manifest_path_traversal(
    monkeypatch, tmp_path: Path
):
    def read_json(path: Path, *, root: Path):
        if path == root / replay.U9_MANIFEST:
            return {
                "inputs": {"iso": {"internal_decision_path": "../escape"}}
            }, b"{}\n"
        if path == root / replay.QUALIFICATION_ROOT / "manifest.json":
            return {}, b"{}\n"
        return {}, b"{}\n"

    monkeypatch.setattr(replay, "_read_json", read_json)
    with pytest.raises(replay.SplitBoardReplayError, match="protected inputs"):
        replay.replay(repo_root=tmp_path, fixture_mode=False, mode="admission")


def _stub_live_admission(monkeypatch, root: Path):
    package = {"candidate_id": "live-u1"}
    decision = {"verdict": "stopped-indeterminate"}

    terminal_paths = {
        root / replay.QUALIFICATION_ROOT / name
        for name in ("evidence_index.json", "owner_signoffs.json")
    }

    def read_json(path: Path, *, root: Path):
        if path in terminal_paths:
            raise AssertionError(f"admission replay read a U7 terminal source: {path}")
        return {}, b"{}\n"

    monkeypatch.setattr(replay, "_read_json", read_json)
    monkeypatch.setattr(replay, "compose_input", lambda **_kwargs: (package, []))
    monkeypatch.setattr(replay, "_verify_protected_descriptor", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(replay, "_evaluate", lambda _value: decision)
    monkeypatch.setattr(replay, "_require_byte_match", lambda *_args, **_kwargs: b"decision\n")
    monkeypatch.setattr(
        replay.qualification_replay,
        "snapshot_paths",
        lambda *_args, **_kwargs: {"stable": "digest"},
    )
    return decision


def test_live_admission_does_not_read_u7_terminal_sources(monkeypatch, tmp_path: Path):
    expected = _stub_live_admission(monkeypatch, tmp_path)

    def forbidden_read_once(*args, **kwargs):
        raise AssertionError("admission-only replay read a U7 terminal source")

    monkeypatch.setattr(replay.qualification_replay, "read_once", forbidden_read_once)
    assert replay.replay(repo_root=tmp_path, fixture_mode=False, mode="admission") == expected


def test_live_replay_is_read_only(monkeypatch, tmp_path: Path):
    _stub_live_admission(monkeypatch, tmp_path)
    with pytest.raises(replay.SplitBoardReplayError, match="read-only"):
        replay.replay(
            output_path=tmp_path / "decision.json",
            repo_root=tmp_path,
            fixture_mode=False,
            mode="admission",
        )


def test_live_admission_fails_if_protected_snapshot_changes(monkeypatch, tmp_path: Path):
    _stub_live_admission(monkeypatch, tmp_path)
    snapshots = iter(({"stable": "before"}, {"stable": "after"}))
    monkeypatch.setattr(
        replay.qualification_replay,
        "snapshot_paths",
        lambda *_args, **_kwargs: next(snapshots),
    )
    with pytest.raises(replay.SplitBoardReplayError, match="changed during replay"):
        replay.replay(repo_root=tmp_path, fixture_mode=False, mode="admission")


def test_manifest_protected_pin_must_match_current_bytes(tmp_path: Path):
    subject = tmp_path / "protected.txt"
    subject.write_bytes(b"current")
    manifest = {
        "protected_inputs": [
            {"path": "protected.txt", "sha256": "0" * 64},
        ]
    }
    with pytest.raises(replay.SplitBoardReplayError, match="digest mismatch"):
        replay._verify_manifest_protected_pins(manifest, root=tmp_path)


@pytest.mark.parametrize(
    "relative",
    [
        "elec/qualification/isolation_joint/interface_contract.json",
        "elec/qualification/isolation_joint/validation/fixture_contract.json",
    ],
)
def test_external_u9_contract_mutation_is_protected(tmp_path: Path, relative: str):
    contract = tmp_path / relative
    contract.parent.mkdir(parents=True)
    contract.write_bytes(b"original")
    manifest = {
        "protected_inputs": [
            {
                "path": relative,
                "sha256": hashlib.sha256(b"original").hexdigest(),
            }
        ]
    }
    contract.write_bytes(b"mutated")
    with pytest.raises(replay.SplitBoardReplayError, match="digest mismatch"):
        replay._verify_manifest_protected_pins(manifest, root=tmp_path)


def test_campaign_base_descriptor_rejects_declared_path_mutation(tmp_path: Path, monkeypatch):
    required = Path("required.txt")
    recursive = Path("recursive")
    (tmp_path / required).write_bytes(b"required")
    (tmp_path / recursive).mkdir()
    (tmp_path / recursive / "entry").write_bytes(b"entry")
    monkeypatch.setattr(replay, "PROTECTED_DESCRIPTOR_REQUIRED_PATHS", (required,))
    monkeypatch.setattr(replay, "PROTECTED_DESCRIPTOR_RECURSIVE_PATHS", (recursive,))
    descriptor = {
        "required_paths": [required.as_posix()],
        "recursive_paths": [recursive.as_posix()],
        "campaign_base": [
            replay._descriptor_snapshot(required, root=tmp_path),
            replay._descriptor_snapshot(recursive, root=tmp_path),
        ],
    }
    manifest = {"protected_descriptor": descriptor}
    replay._verify_protected_descriptor(manifest, root=tmp_path)
    descriptor["required_paths"] = ["different.txt"]
    with pytest.raises(replay.SplitBoardReplayError, match="path set"):
        replay._verify_protected_descriptor(manifest, root=tmp_path)


def test_campaign_base_descriptor_rejects_root_absence(tmp_path: Path, monkeypatch):
    required = Path("required.txt")
    recursive = Path("recursive")
    (tmp_path / required).write_bytes(b"required")
    (tmp_path / recursive).mkdir()
    monkeypatch.setattr(replay, "PROTECTED_DESCRIPTOR_REQUIRED_PATHS", (required,))
    monkeypatch.setattr(replay, "PROTECTED_DESCRIPTOR_RECURSIVE_PATHS", (recursive,))
    descriptor = {
        "required_paths": [required.as_posix()],
        "recursive_paths": [recursive.as_posix()],
        "campaign_base": [
            replay._descriptor_snapshot(required, root=tmp_path),
            replay._descriptor_snapshot(recursive, root=tmp_path),
        ],
    }
    (tmp_path / recursive).rmdir()
    with pytest.raises(replay.SplitBoardReplayError, match="descriptor mismatch"):
        replay._verify_protected_descriptor({"protected_descriptor": descriptor}, root=tmp_path)


@pytest.mark.parametrize("args", [["--mode", "terminal"], ["--output", "result.json"]])
def test_fixture_rejects_incompatible_cli_options(tmp_path: Path, args, capsys):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(_package()), encoding="utf-8")
    assert replay.main(["--fixture", "--input", str(fixture), *args]) == 2
    assert "incompatible with --fixture" in capsys.readouterr().err
