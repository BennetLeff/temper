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
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    requirements_manifest_text: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    repo, output = Path(repo).resolve(), Path(output).resolve()
    result = {
        "profile": "engineering-simulation",
        "stage": "simulation",
        "circuit_sha256": _identity(circuit_identity),
        "requirements_sha256": _identity(requirements_identity),
        "requirements_manifest": requirements_manifest_text,
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
        try:
            requirements_obj = json.loads(requirements_manifest_text or "")
        except json.JSONDecodeError:
            requirements_obj = {}
        protocol_required = any(
            item.get("id") in {"startup_ramp", "load_step_slew"}
            for item in requirements_obj.get("requirements", [])
        )
        if not protocol_required and (
            len(specs) != 4 or {s.get("name") for s in specs} != MANDATORY_SCENARIOS
        ):
            return blocked(
                "startup, input variation, and two load profiles are required",
                "scenario_manifest_invalid",
            )
        if protocol_required:
            names = [s.get("name") for s in specs]
            if (
                len(specs) < 13
                or names.count("startup") < 6
                or names.count("load_variation") < 6
                or names.count("input_variation") < 1
            ):
                return blocked(
                    "adopted protocol requires six startup, six load, and one input case",
                    "scenario_manifest_invalid",
                )
            if any(
                not isinstance(s.get("case_id"), str) or not s["case_id"] for s in specs
            ):
                return blocked(
                    "adopted protocol requires explicit unique case_id values",
                    "scenario_case_id_missing",
                )
            if len({s["case_id"] for s in specs}) != len(specs):
                return blocked(
                    "scenario case_id values must be unique",
                    "scenario_case_id_duplicate",
                )
        spec_profiles = [
            s.get("profile_id") for s in specs if s.get("name") == "load_variation"
        ]
        if (
            not protocol_required
            and (
                len(spec_profiles) != 2
                or len({p for p in spec_profiles if isinstance(p, str)}) != 2
            )
        ) or (
            protocol_required
            and any(
                p not in {"continuous_50mA_to_500mA", "pulse_50mA_to_1A"}
                for p in spec_profiles
            )
        ):
            return blocked(
                "both required load profiles must have explicit scenario specs",
                "load_profile_mismatch",
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
        settings_manifest = json.dumps(
            specs, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        result["settings_manifest"] = settings_manifest
        result["settings_sha256"] = hashlib.sha256(
            settings_manifest.encode()
        ).hexdigest()
        reviewed_scenarios = model.get("reviewed_scenarios_sha256")
        if reviewed_scenarios is not None:
            if (
                not isinstance(reviewed_scenarios, str)
                or reviewed_scenarios != result["settings_sha256"]
            ):
                return blocked(
                    "scenario settings are not bound to the reviewed scenario receipt",
                    "reviewed_scenarios_mismatch",
                )
            result["reviewed_scenarios_verified"] = True
        tool = shutil.which("ngspice")
        if tool is None:
            return blocked("ngspice is unavailable", "simulator_missing")
        version = subprocess.run(
            [tool, "--version"], capture_output=True, text=True, check=False, timeout=5
        )
        result["simulator"] = {"path": tool, "version": version.stdout}
        for spec in specs:
            name = spec["name"]
            raw_format = spec.get("raw_format", "ascii")
            if raw_format not in {"ascii", "ngspice-binary-le64"}:
                return blocked("unsupported waveform format", "raw_format_invalid")
            binary = raw_format == "ngspice-binary-le64"
            if binary and (
                not isinstance(spec.get("timeout_seconds", 3600), (int, float))
                or not 0 < float(spec.get("timeout_seconds", 3600)) <= 3600
            ):
                return blocked(
                    "binary scenario timeout must be between 0 and 3600 seconds",
                    "scenario_timeout_invalid",
                )
            deck = verified_file(spec, "deck", "deck_sha256")
            case_id = spec.get("case_id")
            folder_name = (
                f"case-{hashlib.sha256(case_id.encode()).hexdigest()[:16]}"
                if isinstance(case_id, str) and case_id
                else name
                if name != "load_variation"
                else f"load_variation-{hashlib.sha256(spec['profile_id'].encode()).hexdigest()[:16]}"
            )
            folder = output / folder_name
            folder.mkdir()
            shutil.copyfile(deck, folder / "scenario.cir")
            # Decks use the retained exact model at ../model.lib. No implicit include search.
            rawfile = folder / "waveform.raw"
            scenario = {
                "name": name,
                "case_id": spec.get("case_id"),
                "spec": spec,
                "deck_sha256": spec["deck_sha256"],
                "raw_format": raw_format,
            }
            if binary:
                scenario["raw_file"] = rawfile.relative_to(output).as_posix()
            result["scenarios"].append(scenario)
            argv = [tool, "-n", "-b", "-r", str(rawfile), "scenario.cir"]
            env = {**os.environ}
            if binary:
                env.pop("SPICE_ASCIIRAWFILE", None)
            else:
                env["SPICE_ASCIIRAWFILE"] = "1"
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
                        env=env,
                        timeout=(
                            float(spec.get("timeout_seconds", 3600))
                            if binary
                            else timeout_seconds
                        ),
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
                if not rawfile.is_file() or (
                    not binary and rawfile.stat().st_size > 32 * 1024 * 1024
                ):
                    scenario["status"] = "truncated"
                elif binary:
                    if rawfile.stat().st_size > 8 * 1024 * 1024 * 1024:
                        scenario["status"] = "truncated"
                    else:
                        scenario["artifact_sha256"] = _sha256(rawfile)
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
