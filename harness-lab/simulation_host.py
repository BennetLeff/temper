"""Bounded ngspice collection; Rust parses waveforms and judges their limits."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import harness

MANDATORY_SCENARIOS = {"startup", "input_variation", "load_variation"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and len(value) == 64:
        return value
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def collect(
    repo: Path,
    output: Path,
    model_manifest: Any = None,
    circuit_identity: Any = None,
    requirements_identity: Any = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    repo, output = Path(repo).resolve(), Path(output).resolve()
    result = {
        "profile": "engineering-simulation",
        "stage": "simulation",
        "circuit_sha256": _identity(circuit_identity),
        "requirements_sha256": _identity(requirements_identity),
        "scenarios": [],
        "findings": [],
        "layout_sensitive": False,
    }

    def blocked(message: str, code: str = "model_not_qualified") -> dict:
        result.update(status="blocked")
        result["findings"].append({"id": code, "message": message})
        return result

    def verified_file(spec: dict, path_key: str, hash_key: str) -> Path:
        relative = Path(spec[path_key])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact paths must stay within the repository")
        path = (repo / relative).resolve()
        path.relative_to(repo)
        if not path.is_file() or spec.get(hash_key) != _sha256(path):
            raise ValueError(f"missing or mismatched {path_key}: {path}")
        return path

    if output.exists():
        return blocked("output directory already exists", "stale_output")
    output.mkdir(parents=True)
    if model_manifest is None:
        return blocked(
            "no exact-device qualified model manifest supplied", "exact_model_missing"
        )
    try:
        model = (
            json.loads(Path(model_manifest).read_text())
            if isinstance(model_manifest, (str, Path))
            else dict(model_manifest)
        )
        result["model"] = model
        if (
            model.get("legacy_negative_control")
            or model.get("reference_voltage") == 0.8
        ):
            return blocked(
                "legacy 0.8 V averaged model is inadmissible", "legacy_model_rejected"
            )
        model_path = verified_file(model, "path", "sha256")
        qualification = model["qualification"]
        admission = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps(
                {
                    "profile": "engineering-qualification",
                    "kind": "model",
                    "receipt": qualification,
                }
            ),
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if (
            admission.returncode != 0
            or json.loads(admission.stdout).get("status") != "pass"
        ):
            return blocked(
                "model receipt is not in the reviewed approval registry",
                "qualification_not_approved",
            )
        qualification_path = verified_file(
            qualification, "evidence_path", "evidence_sha256"
        )
        if qualification.get("model_sha256") != model["sha256"]:
            return blocked("qualification belongs to another model")
        shutil.copyfile(model_path, output / "model.lib")
        shutil.copyfile(qualification_path, output / "qualification-evidence.txt")
        result["qualification_verified"] = True
        specs = model["scenarios"]
        if len(specs) != 3 or {s["name"] for s in specs} != MANDATORY_SCENARIOS:
            return blocked(
                "three distinct explicit scenarios are required",
                "scenario_manifest_invalid",
            )
        # Settings are trusted, reviewed operator inputs; bind them to circuit and requirements.
        if model.get("requirements_sha256") != result["requirements_sha256"]:
            return blocked(
                "scenario limits reference different requirements", "stale_requirements"
            )
        if model.get("circuit_sha256") != result["circuit_sha256"]:
            return blocked(
                "scenario decks reference a different circuit", "stale_circuit"
            )
        result["settings_sha256"] = _identity(specs)
        tool = shutil.which("ngspice")
        if tool is None:
            return blocked("ngspice is unavailable", "simulator_missing")
        version = subprocess.run(
            [tool, "--version"], capture_output=True, text=True, check=False, timeout=5
        )
        result["simulator"] = {"path": tool, "version": version.stdout}
        for spec in specs:
            name = spec["name"]
            deck = verified_file(spec, "deck", "deck_sha256")
            folder = output / name
            folder.mkdir()
            shutil.copyfile(deck, folder / "scenario.cir")
            # Decks use the retained exact model at ../model.lib. No implicit include search.
            rawfile = folder / "waveform.raw"
            scenario = {"name": name, "spec": spec, "deck_sha256": spec["deck_sha256"]}
            result["scenarios"].append(scenario)
            argv = [tool, "-b", "-r", str(rawfile), "scenario.cir"]
            with (
                (folder / "stdout.txt").open("w") as stdout,
                (folder / "stderr.txt").open("w") as stderr,
            ):
                try:
                    proc = subprocess.run(
                        argv,
                        cwd=folder,
                        stdout=stdout,
                        stderr=stderr,
                        env={**os.environ, "SPICE_ASCIIRAWFILE": "1"},
                        timeout=timeout_seconds,
                        check=False,
                    )
                    scenario.update(
                        status="pass" if proc.returncode == 0 else "fail",
                        returncode=proc.returncode,
                    )
                except subprocess.TimeoutExpired:
                    scenario["status"] = "timeout"
            scenario["command"] = argv
            for filename in ("stdout.txt", "stderr.txt"):
                scenario[filename + "_sha256"] = _sha256(folder / filename)
            if scenario["status"] == "pass":
                if not rawfile.is_file() or rawfile.stat().st_size > 32 * 1024 * 1024:
                    scenario["status"] = "truncated"
                else:
                    scenario["raw_waveform"] = rawfile.read_text()
                    scenario["artifact_sha256"] = _sha256(rawfile)
        result["status"] = "collected"
        result["synthetic"] = model.get("synthetic", False)
        return result
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        return blocked(f"{type(error).__name__}: {error}")
