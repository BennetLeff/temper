"""Thin RTD construction-memory transport.

The Rust ``zapote-rtd`` binary owns memory validation and selection.  This
module owns only byte transport and evidence: it reads the catalog and its
entries from the repository, asks Rust to prepare a context, and sends the
exact Rust-produced prompt to a caller-supplied provider process.

Preparation is deliberately not delivery.  A successful provider process is
also not proof that a model consumed the prompt or executed a helper.  Those
states are recorded separately in the immutable attempt receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "memory/v1"
CATALOG_SCHEMA = "zapote.memory.catalog.v1"
MAX_PREPARE_SECONDS = 30.0
MAX_PROMPT_BYTES = 256 * 1024


class TransportError(RuntimeError):
    """A transport boundary or immutable-attempt failure."""


class RustPrepareError(TransportError):
    """Rust invocation failed before a normal response could be returned."""

    def __init__(self, message: str, *, stdout: bytes = b"", stderr: bytes = b""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_loads(data: bytes | str) -> Any:
    def pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON field: {key}")
            value[key] = item
        return value

    return json.loads(data, object_pairs_hook=pairs)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _rooted_path(
    repo_root: Path,
    path: str | os.PathLike[str],
    *,
    label: str,
    allow_absolute: bool = False,
) -> Path:
    """Resolve a file only after rejecting absolute, traversal, or symlink paths."""
    if not isinstance(path, (str, os.PathLike)):
        raise ValueError(f"{label} path is not a path string")
    raw = os.fspath(path)
    if not raw or (not allow_absolute and raw.startswith(("/", "\\"))) or "\\" in raw:
        raise ValueError(f"{label} path must be repository-relative: {raw!r}")
    relative = Path(raw)
    if relative.is_absolute() and allow_absolute:
        if ".." in relative.parts:
            raise ValueError(f"{label} path escapes repository: {raw!r}")
        candidate = relative
        probe = Path(candidate.anchor)
        path_parts = candidate.parts[1:]
    elif relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} path escapes repository: {raw!r}")
    else:
        candidate = Path(repo_root).resolve(strict=True) / relative
        probe = Path(repo_root).resolve(strict=True)
        path_parts = relative.parts

    root = Path(repo_root).resolve(strict=True)
    # Check each component before resolve(); resolve() alone would hide a
    # symlink escape and would make a malicious path look ordinary.
    inside_root_real = probe.resolve(strict=False) == root
    for component in path_parts:
        probe /= component
        if probe.is_symlink() and inside_root_real:
            raise ValueError(f"{label} path traverses a symlink: {raw!r}")
        if probe.resolve(strict=False) == root:
            inside_root_real = True
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} path escapes repository: {raw!r}") from error
    return resolved


def _read_repo_utf8(repo_root: Path, path: str, *, label: str) -> tuple[str, bytes]:
    target = _rooted_path(repo_root, path, label=label)
    if not target.is_file():
        raise FileNotFoundError(f"{label} file is missing: {path}")
    data = target.read_bytes()
    try:
        return data.decode("utf-8"), data
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} file is not UTF-8: {path}") from error


def _atomic_bytes(path: Path, data: bytes) -> Path:
    """Create an immutable file without ever replacing an existing artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o444)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o444)
    except BaseException:
        # The exclusive path remains a visible failed artifact if writing was
        # interrupted.  It must never be silently replaced on retry.
        raise
    return path


def _atomic_json(path: Path, value: Any) -> Path:
    return _atomic_bytes(path, _json_bytes(value) + b"\n")


def _entry_evidence_paths(catalog: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    for descriptor in catalog.get("entries", []):
        evidence = descriptor.get("evidence", [])
        if not isinstance(evidence, list):
            raise ValueError("catalog entry evidence must be a list")
        for item in evidence:
            path = item.get("path") if isinstance(item, Mapping) else item
            if not isinstance(path, str) or not path:
                raise ValueError("catalog evidence must contain a path")
            if path not in paths:
                paths.append(path)
    return paths


def _read_catalog(
    repo_root: Path, catalog_path: Path
) -> tuple[str, dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    if not catalog_path.is_file():
        raise FileNotFoundError(f"catalog file is missing: {catalog_path}")
    catalog_bytes = catalog_path.read_bytes()
    try:
        catalog_text = catalog_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"catalog file is not UTF-8: {catalog_path}") from error
    try:
        catalog = _json_loads(catalog_text)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"catalog is invalid JSON: {catalog_path}") from error
    if not isinstance(catalog, dict) or catalog.get("schema") != CATALOG_SCHEMA:
        raise ValueError("unsupported memory catalog schema")
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        raise ValueError("memory catalog entries must be a list")

    loaded: list[dict[str, str]] = []
    for index, descriptor in enumerate(entries):
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("path"), str):
            raise ValueError(f"catalog entry {index} has no repo-relative path")
        path = descriptor["path"]
        text, data = _read_repo_utf8(repo_root, path, label="memory entry")
        declared = descriptor.get("content_sha256")
        digest = _sha256(data)
        if declared is not None and declared != digest:
            raise ValueError(f"memory entry hash mismatch: {path}")
        loaded.append({"path": path, "content_utf8": text})

    # Keep evidence as a separate channel.  Do not infer delivery or policy
    # from these bytes; Rust receives them for its own applicability checks.
    evidence: list[dict[str, str]] = []
    # Evidence paths are collected later because task is part of the input.
    return catalog_text, catalog, loaded, evidence


def _rust_prepare(
    *,
    binary: Path | str,
    payload: bytes,
    timeout: float,
) -> tuple[dict[str, Any], bytes, bytes, int]:
    command = [os.fspath(binary), "--memory-input", "-"]
    try:
        result = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RustPrepareError(
            "zapote-rtd memory preparation timed out",
            stdout=error.output or b"",
            stderr=error.stderr or b"",
        ) from error
    except OSError as error:
        raise RustPrepareError(f"zapote-rtd memory preparation unavailable: {error}") from error
    try:
        answer = _json_loads(result.stdout)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        detail = result.stderr.decode("utf-8", "replace")[-500:]
        raise RustPrepareError(
            f"zapote-rtd returned invalid JSON: {detail}",
            stdout=result.stdout,
            stderr=result.stderr,
        ) from error
    if not isinstance(answer, dict):
        raise RustPrepareError(
            "zapote-rtd memory response is not an object",
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return answer, result.stdout, result.stderr, result.returncode


def _binary_identity(binary: Path | str) -> dict[str, str]:
    path = Path(binary).expanduser().resolve(strict=True)
    if not path.is_file():
        raise FileNotFoundError(f"memory binary is not a file: {path}")
    return {"path": str(path), "sha256": _sha256(path.read_bytes())}


def _verify_rust_context(answer: Mapping[str, Any], catalog_text: str) -> tuple[str, str]:
    """Verify content hashes emitted by Rust; this is integrity, not selection policy."""
    notes = answer.get("notes_utf8")
    prompt = answer.get("prompt_utf8")
    if not isinstance(notes, str) or not isinstance(prompt, str):
        raise TransportError("Rust memory response omitted notes or prompt bytes")
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise TransportError("prepared prompt exceeds transport limit")
    if answer.get("catalog_sha256") != _sha256(catalog_text.encode("utf-8")):
        raise TransportError("Rust memory response catalog hash does not match input")
    if answer.get("notes_sha256") != _sha256(notes.encode("utf-8")):
        raise TransportError("Rust memory response notes hash does not match bytes")
    if answer.get("prompt_sha256") != _sha256(prompt.encode("utf-8")):
        raise TransportError("Rust memory response prompt hash does not match bytes")
    attempt_id = answer.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise TransportError("Rust memory response omitted attempt_id")
    return notes, prompt


def prepare_context(
    repo_root: Path,
    catalog_path: Path,
    task: Mapping[str, Any],
    base_prompt: str,
    binary: Path | str,
    attempt_dir: Path,
) -> dict[str, Any]:
    """Prepare a Rust-selected construction context and retain its exact bytes.

    ``task`` and ``base_prompt`` are caller context.  Catalog selection and
    applicability are decided by Rust, including required IDs and source
    identity behavior.  The returned mapping has status ``prepared`` and is
    safe to pass to :func:`dispatch_context` only while its hashes remain
    unchanged.
    """
    if not isinstance(task, Mapping):
        raise TypeError("task must be a mapping")
    if not isinstance(base_prompt, str):
        raise TypeError("base_prompt must be UTF-8 text")
    attempt_path = Path(attempt_dir)
    if not isinstance(binary, (str, os.PathLike)) or not os.fspath(binary):
        raise ValueError("memory binary is required")
    try:
        attempt_path.parent.mkdir(parents=True, exist_ok=True)
        attempt_path.mkdir()
    except FileExistsError as error:
        raise ValueError("attempt already exists; retry or resume is forbidden") from error
    try:
        repo = Path(repo_root).resolve(strict=True)
        binary_identity = _binary_identity(binary)
        catalog_file = _rooted_path(repo, catalog_path, label="catalog", allow_absolute=True)
        catalog_text, catalog, entries, _ = _read_catalog(repo, catalog_file)
        evidence = [
            {"path": path, "content_utf8": _read_repo_utf8(repo, path, label="evidence")[0]}
            for path in _entry_evidence_paths(catalog)
        ]
        input_value = {
            "schema": SCHEMA,
            "command": "context.prepare",
            "input": {
                "catalog_utf8": catalog_text,
                "entries": entries,
                "evidence": evidence,
                "task": dict(task),
                "base_prompt_utf8": base_prompt,
            },
        }
        input_bytes = _json_bytes(input_value)
        # This is written before invoking Rust so a rejected or unavailable
        # policy process still has the exact request that was attempted.
        _atomic_bytes(attempt_path / "memory-input.json", input_bytes + b"\n")
        answer, raw_stdout, raw_stderr, returncode = _rust_prepare(
            binary=binary_identity["path"], payload=input_bytes, timeout=MAX_PREPARE_SECONDS
        )
        _atomic_bytes(attempt_path / "rust-response.json", raw_stdout)
        _atomic_bytes(attempt_path / "rust-response.stderr", raw_stderr)
        if returncode != 0 or answer.get("status") != "pass":
            message = answer.get("error") or raw_stderr.decode("utf-8", "replace").strip()
            raise ValueError(message or "Rust memory policy rejected context")
        notes, prompt = _verify_rust_context(answer, catalog_text)

        prepared = {
            "status": "prepared",
            "attempt_id": answer["attempt_id"],
            "request_sha256": _sha256(input_bytes),
            "binary_identity": binary_identity,
            "catalog_sha256": answer["catalog_sha256"],
            "selection": answer.get("selection"),
            "notes_utf8": notes,
            "notes_sha256": answer["notes_sha256"],
            "prompt_utf8": prompt,
            "prompt_sha256": answer["prompt_sha256"],
        }
        _atomic_json(attempt_path / "prepared-context.json", prepared)
        prepared["_attempt_dir"] = str(attempt_path)
        prepared["_rust_binary"] = binary_identity["path"]
        return prepared
    except BaseException as error:
        if isinstance(error, RustPrepareError):
            # An invocation failure still needs both partial output and the
            # structured failure receipt below.
            for name, data in (
                ("rust-response.json", error.stdout),
                ("rust-response.stderr", error.stderr),
            ):
                try:
                    _atomic_bytes(attempt_path / name, data)
                except FileExistsError:
                    pass
        # Reserve the attempt before reading anything so even missing files,
        # policy rejection, and timeouts cannot be retried under its identity.
        try:
            _atomic_json(
                attempt_path / "preparation-receipt.json",
                {
                    "schema": SCHEMA,
                    "status": "failed",
                    "phase": "prepare",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
        except FileExistsError:
            pass
        raise


def _verify_prepared(prepared: Mapping[str, Any]) -> bytes:
    if prepared.get("status") != "prepared":
        raise ValueError("context is not in prepared state")
    notes = prepared.get("notes_utf8")
    prompt = prepared.get("prompt_utf8")
    if not isinstance(notes, str) or not isinstance(prompt, str):
        raise ValueError("prepared context bytes are missing")
    if prepared.get("notes_sha256") != _sha256(notes.encode("utf-8")):
        raise ValueError("prepared notes failed hash verification")
    if prepared.get("prompt_sha256") != _sha256(prompt.encode("utf-8")):
        raise ValueError("prepared prompt failed hash verification")
    if not isinstance(prepared.get("attempt_id"), str) or not prepared["attempt_id"]:
        raise ValueError("prepared context has no attempt identity")
    return prompt.encode("utf-8")


def _verify_frozen_prepared(prepared: Mapping[str, Any], directory: Path) -> None:
    """Reject mutation of a prepared mapping after Rust returned it.

    This compares against the immutable file emitted by preparation, rather
    than trusting hashes recomputed over caller-mutated fields.  The Rust
    response and the exact Rust request remain the source of the selection;
    Python only checks their retained byte identity here.
    """
    path = directory / "prepared-context.json"
    if not path.is_file():
        raise ValueError("prepared context artifact is missing")
    frozen = _json_loads(path.read_bytes())
    if not isinstance(frozen, dict):
        raise ValueError("prepared context artifact is malformed")
    fields = (
        "status",
        "attempt_id",
        "request_sha256",
        "binary_identity",
        "catalog_sha256",
        "selection",
        "notes_utf8",
        "notes_sha256",
        "prompt_utf8",
        "prompt_sha256",
    )
    if any(prepared.get(field) != frozen.get(field) for field in fields):
        raise ValueError("prepared context differs from its frozen Rust result")
    request_path = directory / "memory-input.json"
    if not request_path.is_file():
        raise ValueError("memory input artifact is missing")
    request_bytes = request_path.read_bytes()
    if request_bytes.endswith(b"\n"):
        request_bytes = request_bytes[:-1]
    if prepared.get("request_sha256") != _sha256(request_bytes):
        raise ValueError("memory input artifact failed hash verification")
    identity = prepared.get("binary_identity")
    if not isinstance(identity, dict) or not isinstance(identity.get("path"), str):
        raise ValueError("prepared context has no Rust binary identity")
    try:
        current = _binary_identity(identity["path"])
    except (OSError, ValueError) as error:
        raise ValueError("Rust binary identity cannot be resolved") from error
    if current != identity:
        raise ValueError("Rust binary changed since preparation")


def _run_provider(
    command: Sequence[str], prompt: bytes, timeout: float
) -> tuple[str, int | None, bytes, bytes, bool]:
    if not command or any(not isinstance(item, str) or not item for item in command):
        raise ValueError("provider_command must be a non-empty argv list")
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(input=prompt, timeout=timeout)
            return "completed", process.returncode, stdout, stderr, True
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate()
            # communicate() returns the complete post-termination buffers;
            # TimeoutExpired.output may refer to the same already-read prefix.
            return "timeout", None, stdout, stderr, False
    except OSError as error:
        return "launch_failed", None, b"", str(error).encode("utf-8", "replace"), False


def dispatch_context(
    prepared: Mapping[str, Any],
    provider_command: list[str],
    timeout: float,
    *,
    attempt_dir: Path | None = None,
    provider_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Send the exact prepared prompt to a provider and retain the outcome.

    The provider receives argv directly and the prompt as stdin; no shell or
    credential environment is serialized.  ``process_completed`` says only
    that the child exited.  ``model_consumption`` and ``helper_execution``
    remain unverified/empty because a provider response cannot prove either.
    """
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout must be a finite positive number")
    if not provider_command or any(
        not isinstance(item, str) or not item for item in provider_command
    ):
        raise ValueError("provider_command must be a non-empty argv list")
    prompt = _verify_prepared(prepared)
    target_dir = attempt_dir or prepared.get("_attempt_dir")
    if target_dir is None:
        raise ValueError("prepared context has no attempt directory")
    directory = Path(target_dir)
    directory.mkdir(parents=True, exist_ok=True)
    _verify_frozen_prepared(prepared, directory)
    receipt_path = directory / "dispatch-receipt.json"
    dispatch_artifacts = (
        receipt_path,
        directory / "provider-request.stdin",
        directory / "provider-response.stdout",
        directory / "provider-response.stderr",
    )
    if any(path.exists() for path in dispatch_artifacts):
        raise ValueError("attempt already dispatched; retry or resume is forbidden")

    # Capture at the send boundary, before creating the child.  If process
    # creation fails, this still proves exactly which bytes were attempted.
    _atomic_bytes(directory / "provider-request.stdin", prompt)
    status, returncode, stdout, stderr, process_completed = _run_provider(
        provider_command, prompt, timeout
    )
    if status == "completed" and returncode != 0:
        status = "failed"
    _atomic_bytes(directory / "provider-response.stdout", stdout)
    _atomic_bytes(directory / "provider-response.stderr", stderr)
    receipt = {
        "schema": SCHEMA,
        "status": status,
        "attempt_id": prepared["attempt_id"],
        "prompt_sha256": prepared["prompt_sha256"],
        "provider": {
            "argv": list(provider_command),
            "identity": dict(provider_identity) if provider_identity is not None else None,
        },
        "returncode": returncode,
        "process_completed": process_completed,
        "model_consumption": "unverified",
        "reported_use": None,
        "helper_execution": [],
        "stdout_sha256": _sha256(stdout),
        "stderr_sha256": _sha256(stderr),
    }
    _atomic_json(receipt_path, receipt)
    return receipt


def _cli_task(value: str) -> Mapping[str, Any]:
    path = Path(value)
    raw = path.read_text(encoding="utf-8") if path.is_file() else value
    parsed = _json_loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--task must be a JSON object or a JSON file")
    return parsed


def _cli_prompt(value: str) -> str:
    path = Path(value)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def _cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RTD construction-memory transport")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--repo-root", required=True, type=Path)
        subparser.add_argument("--catalog", required=True, type=Path)
        subparser.add_argument("--task", required=True, help="JSON object or JSON file")
        subparser.add_argument("--prompt", required=True, help="Prompt text or UTF-8 file")
        subparser.add_argument("--binary", required=True, type=Path)
        subparser.add_argument("--attempt-dir", required=True, type=Path)
        if name == "run":
            subparser.add_argument("--timeout", required=True, type=float)
            subparser.add_argument("provider", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for one immutable prepare or prepare-and-run attempt."""
    args = _cli_parser().parse_args(argv)
    try:
        prepared = prepare_context(
            args.repo_root,
            args.catalog,
            _cli_task(args.task),
            _cli_prompt(args.prompt),
            args.binary,
            args.attempt_dir,
        )
        public_prepared = {key: value for key, value in prepared.items() if not key.startswith("_")}
        if args.command == "prepare":
            print(json.dumps(public_prepared, ensure_ascii=False, sort_keys=True))
            return 0
        provider = list(args.provider)
        if provider[:1] == ["--"]:
            provider = provider[1:]
        receipt = dispatch_context(prepared, provider, args.timeout)
        print(
            json.dumps(
                {"prepared": public_prepared, "dispatch": receipt},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if receipt["status"] == "completed" else 1
    except Exception as error:
        print(f"zapote memory transport: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess CLI test
    raise SystemExit(main())


__all__ = ["SCHEMA", "TransportError", "prepare_context", "dispatch_context", "main"]
