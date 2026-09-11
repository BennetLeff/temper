"""Replay real-catalog memory controls against the compiled Zapote validator.

The provider used here is a local echo process, explicitly not an LLM.
Output must be a new directory; earlier receipts are never overwritten.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from zapote.memory import dispatch_context, prepare_context  # noqa: E402


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main(binary: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    catalog_path = ROOT / "zapote/skills/revisions/rtd-lessons-v1/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    task = json.loads((Path(__file__).parent / "cross-unit-task.json").read_text())
    prompt = (Path(__file__).parent / "cross-unit-prompt.txt").read_text()
    evidence_paths = sorted({item["path"] for entry in catalog["entries"] for item in entry["evidence"]})
    payload = {
        "schema": "memory/v1", "command": "context.prepare",
        "input": {
            "catalog_utf8": catalog_path.read_text(),
            "entries": [{"path": entry["path"], "content_utf8": (ROOT / entry["path"]).read_text()} for entry in catalog["entries"]],
            "evidence": [{"path": path, "content_utf8": (ROOT / path).read_text()} for path in evidence_paths],
            "task": task, "base_prompt_utf8": prompt,
        },
    }
    cases = []

    def check(name: str, request: dict, selected: list[str] | None) -> None:
        result = subprocess.run([str(binary), "--memory-input", "-"], input=json.dumps(request), text=True, capture_output=True, timeout=30, check=False)
        answer = json.loads(result.stdout)
        if selected is None:
            assert result.returncode == 1 and answer["status"] == "invalid", (name, answer)
        else:
            assert result.returncode == 0 and answer["status"] == "pass", (name, answer)
            assert answer["selection"]["selected_ids"] == selected, (name, answer)
        cases.append({"case": name, "exit_code": result.returncode, "response": answer})

    check("cross-unit-procedure-only", payload, ["rtd-mem-001"])
    matched = copy.deepcopy(payload)
    matched["input"]["task"]["source_identities"] = catalog["entries"][1]["current_sources"]
    check("matching-rtd-fact", matched, ["rtd-mem-001", "rtd-mem-002"])
    mismatch = copy.deepcopy(matched)
    mismatch["input"]["task"]["source_identities"]["rtd_board"] = "a" * 64
    check("changed-board-excludes-exact-fact", mismatch, ["rtd-mem-001"])
    mismatch["input"]["task"]["required_ids"].append("rtd-mem-002")
    check("changed-required-fact-rejected", mismatch, None)
    changed = copy.deepcopy(payload)
    changed["input"]["entries"][0]["content_utf8"] += " unreviewed mutation"
    check("changed-entry-rejected", changed, None)
    changed = copy.deepcopy(payload)
    changed["input"]["evidence"][0]["content_utf8"] += " changed evidence"
    check("changed-evidence-rejected", changed, None)
    for name, alter in [
        ("duplicate-entry", lambda cat: cat["entries"].append(cat["entries"][0])),
        ("candidate-required-entry", lambda cat: cat["entries"][0].update(validation_state="candidate")),
    ]:
        changed = copy.deepcopy(payload)
        cat = copy.deepcopy(catalog)
        alter(cat)
        changed["input"]["catalog_utf8"] = json.dumps(cat)
        check(name, changed, None)
    changed = copy.deepcopy(payload)
    cat = copy.deepcopy(catalog)
    content = "x" * 65536
    cat["entries"][0]["content_sha256"] = sha(content)
    changed["input"]["entries"][0]["content_utf8"] = content
    changed["input"]["catalog_utf8"] = json.dumps(cat)
    check("rendered-notes-overflow-rejected", changed, None)

    prepared = prepare_context(ROOT, catalog_path, task, prompt, binary, output / "process-control")
    receipt = dispatch_context(prepared, [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"], 5, provider_identity={"kind": "local-process-control", "model": None})
    sent = (output / "process-control/provider-request.stdin").read_bytes()
    assert sent == (output / "process-control/provider-response.stdout").read_bytes()
    assert sent == prepared["prompt_utf8"].encode()
    assert b"rtd-mem-001" in sent and b"0.971459" not in sent
    assert receipt["model_consumption"] == "unverified" and not receipt["helper_execution"]
    report = {"status": "pass", "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "policy_controls": cases, "process_control": receipt, "live_model_control": "separate; this replay uses no LLM"}
    (output / "integration-receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(cases)} real-catalog policy controls and exact stdin process control passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    main(args.binary.resolve(strict=True), args.output.resolve())
