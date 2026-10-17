#!/usr/bin/env python3
"""Check source identities, executed-script preservation and final case accounting."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    result, imports = [], []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.dump(node))
        else:
            result.extend(sorted(imports))
            imports = []
            result.append(ast.dump(node))
    result.extend(sorted(imports))
    return result


def main() -> None:
    proof = {}
    for name in ("run", "refine"):
        old, new = HERE / f"{name}-executed.py.txt", HERE / f"{name}.py"
        equivalent = canonical(old) == canonical(new)
        if not equivalent:
            raise ValueError(f"non-format change: {name}")
        proof[name] = {
            "executed_sha256": sha(old),
            "current_sha256": sha(new),
            "ast_equivalent_except_contiguous_import_order": equivalent,
        }
    (HERE / "format-equivalence.json").write_text(json.dumps(proof, indent=2) + "\n")
    checks = []
    for file in HERE.glob("*-provenance.json"):
        for path, expected in json.loads(file.read_text())["inputs_sha256"].items():
            target = HERE.parents[4] / path
            if target == HERE / "run.py" and sha(target) != expected:
                target = HERE / "run-executed.py.txt"
            if sha(target) != expected:
                raise ValueError(f"input hash mismatch: {target}")
            checks.append({"path": path, "sha256": expected})
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", str(HERE)], text=True
    ).splitlines()
    tracked = subprocess.check_output(["git", "ls-files", str(HERE)], text=True).splitlines()
    if any("/cache/" in n or n.endswith((".lib", ".zip")) for n in untracked + tracked):
        raise ValueError("licensed/cache file exposed to version control")
    audit = json.loads((HERE / "audit.json").read_text())
    if audit["checked_complete"] != 105 or audit["indeterminate"] != 1:
        raise ValueError("unexpected completion accounting")
    if any(s["pass"] or (s["tt_ns"] <= 260 and s["complete"] != 16) for s in audit["s4_summary"]):
        raise ValueError("unexpected S4 conclusion or missing corners")
    receipt = {
        "complete_results": 105,
        "complete_s4": 86,
        "complete_recovery": 19,
        "s4_all_fail": True,
        "interrupted_indeterminate": 1,
        "planned_not_run": 29,
        "source_hash_checks": len(checks),
        "licensed_files_excluded": True,
        "format_equivalence": proof,
        "inputs": checks,
    }
    (HERE / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in receipt.items() if k not in ("inputs", "format_equivalence")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
