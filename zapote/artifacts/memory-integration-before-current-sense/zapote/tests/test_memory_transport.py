"""Boundary tests for the thin RTD construction-memory transport."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from zapote.memory import dispatch_context, prepare_context


def _catalog(root: Path, *, entry_path: str = "memory/lesson.md") -> Path:
    target = root / entry_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("selected RTD lesson\n", encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    catalog = root / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema": "zapote.memory.catalog.v1",
                "revision": "rtd-lessons-v1",
                "entries": [
                    {
                        "id": "rtd-mem-001",
                        "path": entry_path,
                        "content_sha256": digest,
                        "evidence": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return catalog


def _rust_stub(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/env python3
import hashlib, json, sys
request = json.load(sys.stdin)
payload = request["input"]
notes = payload["entries"][0]["content_utf8"]
task = json.dumps(payload["task"], sort_keys=True, separators=(",", ":"))
prompt = payload["base_prompt_utf8"] + "\\nTASK=" + task + "\\nNOTES=" + notes
digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
print(json.dumps({
  "status": "pass",
  "attempt_id": payload["task"]["attempt_id"],
  "catalog_sha256": digest(payload["catalog_utf8"]),
  "selection": {"selected_ids": ["rtd-mem-001"]},
  "notes_utf8": notes,
  "notes_sha256": digest(notes),
  "prompt_utf8": prompt,
  "prompt_sha256": digest(prompt),
}))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _provider(*code: str) -> list[str]:
    return [sys.executable, "-c", " ".join(code)]


def test_child_receives_exact_rust_prompt_and_prepare_is_not_delivered(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    rust = _rust_stub(tmp_path / "rust-stub.py")
    attempt = tmp_path / "attempt-01"
    task = {"attempt_id": "rtd-01", "capabilities": ["simulation-evidence-scoping"]}

    prepared = prepare_context(tmp_path, catalog, task, "Construct safely", rust, attempt)
    assert prepared["status"] == "prepared"
    assert prepared["status"] != "delivered"

    receipt = dispatch_context(
        prepared,
        _provider("import sys;", "sys.stdout.buffer.write(sys.stdin.buffer.read())"),
        3,
    )
    assert receipt["status"] == "completed"
    assert receipt["process_completed"] is True
    assert receipt["model_consumption"] == "unverified"
    sent = (attempt / "provider-request.stdin").read_bytes()
    assert sent == prepared["prompt_utf8"].encode()
    assert sent == (attempt / "provider-response.stdout").read_bytes()
    assert b"selected RTD lesson" in sent
    assert b'"attempt_id":"rtd-01"' in sent


def test_tampered_prepared_payload_is_rejected_against_frozen_result(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    rust = _rust_stub(tmp_path / "rust-stub.py")
    attempt = tmp_path / "attempt-02"
    prepared = prepare_context(
        tmp_path, catalog, {"attempt_id": "rtd-02"}, "Base", rust, attempt
    )
    tampered = dict(prepared)
    tampered["prompt_utf8"] += " forged"
    with pytest.raises(ValueError, match="hash verification"):
        dispatch_context(tampered, _provider("import sys"), 3)
    tampered = dict(prepared)
    tampered["selection"] = {"selected_ids": []}
    with pytest.raises(ValueError, match="frozen Rust result"):
        dispatch_context(tampered, _provider("import sys"), 3)
    assert not (attempt / "provider-request.stdin").exists()
    tampered = dict(prepared)
    tampered["prompt_utf8"] += " forged"
    tampered["prompt_sha256"] = hashlib.sha256(tampered["prompt_utf8"].encode()).hexdigest()
    with pytest.raises(ValueError, match="frozen Rust result"):
        dispatch_context(tampered, _provider("import sys"), 3)
    request = attempt / "memory-input.json"
    request.chmod(0o644)
    request.write_bytes(request.read_bytes().replace(b"Base", b"forged"))
    request.chmod(0o444)
    with pytest.raises(ValueError, match="memory input artifact"):
        dispatch_context(prepared, _provider("import sys"), 3)


def test_binary_drift_blocks_dispatch_before_provider_send(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    rust = _rust_stub(tmp_path / "rust-stub.py")
    attempt = tmp_path / "attempt-drift"
    prepared = prepare_context(tmp_path, catalog, {"attempt_id": "drift"}, "Base", rust, attempt)
    rust.chmod(0o644)
    rust.write_bytes(rust.read_bytes() + b"\n")
    rust.chmod(0o755)
    with pytest.raises(ValueError, match="Rust binary changed"):
        dispatch_context(prepared, _provider("import sys"), 3)
    assert not (attempt / "provider-request.stdin").exists()


def test_missing_traversal_and_symlink_entries_fail_before_rust_success(tmp_path: Path) -> None:
    missing = _catalog(tmp_path, entry_path="missing.md")
    (tmp_path / "missing.md").unlink()
    rust = _rust_stub(tmp_path / "rust-stub.py")
    attempt = tmp_path / "missing-attempt"
    with pytest.raises(FileNotFoundError):
        prepare_context(tmp_path, missing, {"attempt_id": "missing"}, "Base", rust, attempt)
    assert (attempt / "preparation-receipt.json").is_file()
    with pytest.raises(ValueError, match="attempt already exists"):
        prepare_context(tmp_path, missing, {"attempt_id": "missing"}, "Base", rust, attempt)

    traversal = _catalog(tmp_path, entry_path="../outside.md")
    with pytest.raises(ValueError, match="escapes repository"):
        prepare_context(
            tmp_path,
            traversal,
            {"attempt_id": "traversal"},
            "Base",
            rust,
            tmp_path / "traversal",
        )

    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    linked = _catalog(tmp_path, entry_path="link.md")
    with pytest.raises(ValueError, match="symlink"):
        prepare_context(
            tmp_path,
            linked,
            {"attempt_id": "link"},
            "Base",
            rust,
            tmp_path / "link-attempt",
        )


def test_timeout_partial_failure_and_duplicate_attempt_are_retained(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    rust = _rust_stub(tmp_path / "rust-stub.py")
    timeout_attempt = tmp_path / "timeout"
    prepared = prepare_context(
        tmp_path, catalog, {"attempt_id": "timeout"}, "Base", rust, timeout_attempt
    )
    timeout_receipt = dispatch_context(
        prepared,
        _provider("import time;", "time.sleep(2)"),
        0.05,
    )
    assert timeout_receipt["status"] == "timeout"
    assert timeout_receipt["process_completed"] is False
    with pytest.raises(ValueError, match="already dispatched"):
        dispatch_context(prepared, _provider("pass"), 1)

    failed_attempt = tmp_path / "failed"
    failed = prepare_context(
        tmp_path, catalog, {"attempt_id": "failed"}, "Base", rust, failed_attempt
    )
    partial = dispatch_context(
        failed,
        _provider("import sys;", "sys.stdout.write('partial');", "sys.exit(7)"),
        3,
    )
    assert partial["status"] == "failed"
    assert partial["process_completed"] is True
    assert partial["returncode"] == 7
    assert (failed_attempt / "provider-response.stdout").read_bytes() == b"partial"


def test_invalid_provider_controls_do_not_start_an_attempt(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    rust = _rust_stub(tmp_path / "rust-stub.py")
    attempt = tmp_path / "attempt-05"
    prepared = prepare_context(tmp_path, catalog, {"attempt_id": "controls"}, "Base", rust, attempt)
    with pytest.raises(ValueError, match="finite positive"):
        dispatch_context(prepared, _provider("pass"), 0)
    assert not (attempt / "provider-request.stdin").exists()


def test_prepare_and_run_cli_expose_the_two_transport_phases(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    rust = _rust_stub(tmp_path / "rust-stub.py")
    task = json.dumps({"attempt_id": "cli-01", "capabilities": []})
    script = Path(__file__).parents[1] / "memory.py"
    attempt = tmp_path / "cli-attempt"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "run",
            "--repo-root",
            str(tmp_path),
            "--catalog",
            str(catalog),
            "--task",
            task,
            "--prompt",
            "Construct safely",
            "--binary",
            str(rust),
            "--attempt-dir",
            str(attempt),
            "--timeout",
            "3",
            "--",
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["prepared"]["status"] == "prepared"
    assert output["dispatch"]["status"] == "completed"


def test_invalid_rust_response_retains_failed_attempt_and_partial_output(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    rust = tmp_path / "broken-rust.py"
    rust.write_text("#!/usr/bin/env python3\nprint('incomplete response')\n")
    rust.chmod(0o755)
    attempt = tmp_path / "broken-attempt"
    with pytest.raises(RuntimeError, match="invalid JSON"):
        prepare_context(tmp_path, catalog, {"attempt_id": "broken"}, "Base", rust, attempt)
    assert (attempt / "memory-input.json").is_file()
    assert (attempt / "rust-response.json").read_text() == "incomplete response\n"
    receipt = json.loads((attempt / "preparation-receipt.json").read_text())
    assert receipt["status"] == "failed" and receipt["phase"] == "prepare"
    assert not (attempt / "provider-request.stdin").exists()
    with pytest.raises(ValueError, match="attempt already exists"):
        prepare_context(tmp_path, catalog, {"attempt_id": "broken"}, "Base", rust, attempt)
