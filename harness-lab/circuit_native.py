"""Build a fresh isolated copy of the real Atopile source; retain native evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import harness

PINNED_ATOPILE = "0.2.69"
ENGINEERING = Path(__file__).resolve().parent / "engineering"


def _build(repo: Path, build_dir: Path) -> dict[str, Any]:
    build_dir.mkdir(parents=True, exist_ok=False)
    for name in ("buck.ato", "ato.yaml"):
        shutil.copyfile(ENGINEERING / name, build_dir / name)
    shutil.copytree(
        repo / "elec/src",
        build_dir / "elec/src",
        ignore=shutil.ignore_patterns("*.log", "__pycache__"),
    )
    command = [
        "uv",
        "tool",
        "run",
        "--offline",
        "--from",
        f"atopile=={PINNED_ATOPILE}",
        "ato",
        "--non-interactive",
        "build",
        "buck.ato:BuckCircuitCandidate",
    ]
    result: dict[str, Any] = {
        "status": "blocked",
        "command": command,
        "cwd": str(build_dir),
    }
    with (
        (build_dir / "stdout.txt").open("w") as stdout,
        (build_dir / "stderr.txt").open("w") as stderr,
    ):
        try:
            proc = subprocess.run(
                command,
                cwd=build_dir,
                stdout=stdout,
                stderr=stderr,
                timeout=120,
                check=False,
            )
            result["returncode"] = proc.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            result["error"] = str(error)
    artifacts = {
        name: str(build_dir / "build" / name)
        for name in ("default.net", "default.csv")
        if (build_dir / "build" / name).is_file()
    }
    result["artifacts"] = artifacts
    result["artifact_hashes"] = {
        name: harness.file_hash(Path(path)) for name, path in artifacts.items()
    }
    if result.get("returncode") == 0 and len(artifacts) == 2:
        result["status"] = "pass"
        export_path = build_dir / "resolved-components.json"
        export_command = [
            "uv",
            "tool",
            "run",
            "--offline",
            "--from",
            f"atopile=={PINNED_ATOPILE}",
            "python",
            str(harness.ROOT / "circuit_export.py"),
            str(build_dir),
            str(export_path),
        ]
        with (
            (build_dir / "export-stdout.txt").open("w") as stdout,
            (build_dir / "export-stderr.txt").open("w") as stderr,
        ):
            try:
                export_result = subprocess.run(
                    export_command,
                    cwd=build_dir,
                    stdout=stdout,
                    stderr=stderr,
                    check=False,
                    timeout=120,
                )
                result["export_returncode"] = export_result.returncode
                if export_result.returncode == 0 and export_path.is_file():
                    result["resolved_export"] = json.loads(export_path.read_text())
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                result["export_error"] = str(error)
    return result


def collect(repo: Path, output: Path, board: Path | None = None) -> dict[str, Any]:
    repo, output = repo.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_files = sorted((repo / "elec/src").rglob("*.ato"))
    source_files += [ENGINEERING / "buck.ato", ENGINEERING / "ato.yaml"]
    before = {str(p.relative_to(repo)): harness.file_hash(p) for p in source_files}
    build = _build(repo, output / "workspace")
    evidence: dict[str, Any] = {
        "stage": "circuit",
        "profile": "engineering-circuit",
        "status": build["status"],
        "atopile": {"version": PINNED_ATOPILE, "build": build},
        "source": before,
        "source_unchanged": all(
            harness.file_hash(p) == before[str(p.relative_to(repo))]
            for p in source_files
        ),
        "resolved_export": build.get("resolved_export"),
    }
    if board is not None:
        try:
            evidence["candidate"] = harness.native(
                "measure", board, adapter=harness.ROOT / "buck_native.py"
            )
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            evidence["candidate_error"] = str(error)
    return evidence


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--board", type=Path)
    args = parser.parse_args()
    print(json.dumps(collect(args.repo, args.output, args.board), sort_keys=True))
