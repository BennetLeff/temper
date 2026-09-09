"""Collect stages 1–4 in a fresh evidence directory; Rust decides admission."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import circuit_native
import harness
import qualify_buck
import simulation_host

ROOT = harness.ROOT
REPO = ROOT.parent


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def inventory(directory: Path) -> dict[str, str]:
    """Inventory real, contained artifact bytes; reject symlink escapes."""
    root = directory.resolve()
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink is not an evidence artifact: {path}")
        if path.is_file():
            path.resolve().relative_to(root)
            result[path.relative_to(directory).as_posix()] = harness.file_hash(path)
    return result


def judge(payload: dict) -> dict:
    result = subprocess.run(
        [str(harness.JUDGE)],
        input=json.dumps(payload, allow_nan=False),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode not in (0, 2):
        raise RuntimeError(f"judge exited {result.returncode}: {result.stderr}")
    return json.loads(result.stdout)


def sources() -> dict[str, str]:
    paths = list((REPO / "elec/src").rglob("*.ato"))
    paths += list((ROOT / "engineering").rglob("*"))
    paths += list((ROOT / "src").glob("*.rs"))
    paths += list(ROOT.glob("*.py"))
    paths += [qualify_buck.CONTRACT, ROOT / "Cargo.lock", ROOT / "Cargo.toml"]
    return {
        p.relative_to(REPO).as_posix(): harness.file_hash(p)
        for p in sorted(paths)
        if p.is_file()
    }


def collect_stage(stage: str, output: Path, collect) -> tuple[dict, list[Path]]:
    raw_path = output / f"{stage}-input.json"
    result_path = output / f"{stage}-result.json"
    try:
        raw = collect()
        write_json(raw_path, raw)
        result = judge(raw)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        result = {
            "stage": stage,
            "status": "blocked",
            "findings": [
                {
                    "id": "collection_unavailable",
                    "message": f"{type(error).__name__}: {error}",
                }
            ],
        }
        if not raw_path.exists():
            write_json(raw_path, result)
    result["stage"] = stage
    write_json(result_path, result)
    return result, [raw_path, result_path]


def run(
    output: Path,
    variant: str = "buck-dev-a",
    requirements: Path | None = None,
    model_manifest: Path | None = None,
    board: Path | None = None,
    component_qualification: Path | None = None,
) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    requirement_path = requirements or ROOT / "engineering/requirements.json"
    shutil.copyfile(requirement_path, output / "requirements.json")
    manifest = json.loads((output / "requirements.json").read_text())
    source_inventory = sources()
    write_json(output / "sources.json", source_inventory)
    if not harness.JUDGE.is_file():
        raise RuntimeError("build the Rust judge with make -C harness-lab build first")
    write_json(
        output / "toolchain.json",
        {
            "judge": str(harness.JUDGE),
            "judge_sha256": harness.file_hash(harness.JUDGE),
            "kicad_python": harness.KICAD_PYTHON,
        },
    )
    candidate_dir = output / "candidate"
    qualify_buck.prepare(candidate_dir, variant)
    shutil.copyfile(
        board or candidate_dir / "witness.kicad_pcb",
        candidate_dir / "candidate.kicad_pcb",
    )
    candidate = candidate_dir / "candidate.kicad_pcb"
    current = {
        "requirements_sha256": harness.file_hash(output / "requirements.json"),
        "sources_sha256": identity(
            {
                path: digest
                for path, digest in source_inventory.items()
                if path.startswith("elec/src/")
                or path
                in {
                    "harness-lab/engineering/buck.ato",
                    "harness-lab/engineering/ato.yaml",
                    "harness-lab/engineering/circuit-contract.json",
                }
            }
        ),
        "board_sha256": harness.file_hash(candidate),
    }

    def circuit_collection() -> dict:
        payload = circuit_native.collect(REPO, output / "circuit", candidate)
        payload["circuit_source_sha256"] = current["sources_sha256"]
        if component_qualification:
            qualification = json.loads(component_qualification.read_text())
            relative = Path(qualification["artifact_path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("qualification artifact must stay within repository")
            artifact = (REPO / relative).resolve()
            artifact.relative_to(REPO)
            qualification["verified_artifact"] = harness.file_hash(
                artifact
            ) == qualification.get("artifact_sha256")
            shutil.copyfile(
                artifact, output / "circuit/component-qualification-evidence"
            )
            write_json(output / "circuit/component-qualification.json", qualification)
            payload["component_qualification"] = qualification
        return payload

    circuit, circuit_files = collect_stage("circuit", output, circuit_collection)
    simulation, simulation_files = collect_stage(
        "simulation",
        output,
        lambda: simulation_host.collect(
            REPO,
            output / "simulation",
            model_manifest,
            circuit_identity={
                "sources": current["sources_sha256"],
                "circuit_result": harness.file_hash(circuit_files[-1]),
            },
            requirements_identity=current["requirements_sha256"],
        ),
    )

    def layout_collection() -> dict:
        import layout_native

        contract = json.loads(qualify_buck.CONTRACT.read_text())
        base = qualify_buck.evaluate(
            candidate_dir, contract, variant, output / "native"
        )
        return layout_native.collect(REPO, output / "layout", candidate, base)

    layout, layout_files = collect_stage("layout", output, layout_collection)
    receipts = {}
    dependency_hashes = {}
    for name, result, files in (
        ("circuit", circuit, circuit_files),
        ("simulation", simulation, simulation_files),
        ("layout", layout, layout_files),
    ):
        receipt = {
            **result,
            "schema_version": "engineering/v1",
            "stage": name,
            "requirements_revision": manifest.get("revision"),
            "identity": current,
            "dependencies": dict(dependency_hashes),
            "artifacts": [
                {
                    "path": p.relative_to(output).as_posix(),
                    "sha256": harness.file_hash(p),
                }
                for p in files
            ],
        }
        receipts[name] = receipt
        if name == "circuit":
            dependency_hashes["circuit_sha256"] = harness.file_hash(files[-1])
    source_changed = source_inventory != sources()
    board_changed = current["board_sha256"] != harness.file_hash(candidate)
    if source_changed or board_changed:
        for receipt in receipts.values():
            receipt["stale"] = True
    payload = {
        "profile": "engineering",
        "requirements": manifest,
        "current_identity": current,
        "stage_receipts": receipts,
        "artifact_inventory": inventory(output),
    }
    write_json(output / "engineering-input.json", payload)
    report = judge(payload)
    report["variant"] = variant
    report["evidence_directory"] = str(output)
    report["stage_results"] = {
        "circuit": circuit,
        "simulation": simulation,
        "layout": layout,
    }
    write_json(output / "report.json", report)
    lines = [
        f"Buck engineering validation: {report['status']}",
        "",
        "Hardware validation: unverified (stage 5 has not run).",
        "",
    ]
    for stage in report["stages"]:
        lines.append(f"{stage['stage']}: {stage['status']}")
        for finding in stage.get("findings", []):
            detail = finding.get("message") or json.dumps(finding, sort_keys=True)
            requirement = (
                f" ({finding['requirement']})" if finding.get("requirement") else ""
            )
            lines.append(f"- {finding.get('id')}{requirement}: {detail}")
        lines.append("")
    (output / "report.md").write_text("\n".join(lines))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variant", default="buck-dev-a")
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--model-manifest", type=Path)
    parser.add_argument("--board", type=Path)
    parser.add_argument("--component-qualification", type=Path)
    args = parser.parse_args()
    result = run(
        args.output,
        args.variant,
        args.requirements,
        args.model_manifest,
        args.board,
        args.component_qualification,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("eligible") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
