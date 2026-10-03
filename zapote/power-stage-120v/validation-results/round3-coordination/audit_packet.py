"""Inventory round-three evidence and check packaging, not engineering verdicts."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
UNIT = RESULTS.parent
REPO = UNIT.parents[1]
PACKETS = (
    "01-switching-parasitics/round3",
    "02-protection-timing/round3",
    "03-loss-thermal-budget/round3",
    "04-board-current-thermal/round3/a4-copper",
    "04-board-current-thermal/round3/b3-thermal",
    "05-resonant-tank-envelope/round3",
    "07-conducted-emi/round3",
    "round3-coordination",
)


def reject_nonfinite(value: str) -> None:
    raise ValueError(f"Nonfinite JSON token: {value}")


def main() -> None:
    hashes: dict[str, str] = {}
    issues: list[str] = []
    missing_packets = []
    byte_count = 0
    for packet in PACKETS:
        root = RESULTS / packet
        if not root.is_dir():
            missing_packets.append(packet)
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path == HERE / "packet-audit.json":
                continue
            name = str(path.relative_to(RESULTS))
            if path.name == "IFX_CFD7_650V.lib" or path.name == "cfd7-650.zip":
                issues.append(f"Vendor runtime copy must not ship: {name}")
                continue
            data = path.read_bytes()
            hashes[name] = hashlib.sha256(data).hexdigest()
            byte_count += len(data)
            if len(data) > 95_000_000:
                issues.append(f"Oversize artifact: {name} ({len(data)} bytes)")
            if path.suffix == ".json":
                try:
                    json.loads(data, parse_constant=reject_nonfinite)
                except (ValueError, UnicodeError) as exc:
                    issues.append(f"Invalid JSON: {name}: {exc}")
            if path.suffix == ".md":
                for target in re.findall(r"\]\(([^\s)]+)\)", data.decode()):
                    parsed = urlsplit(target)
                    if parsed.scheme or not parsed.path or target.startswith("#"):
                        continue
                    linked = path.parent / unquote(parsed.path)
                    if not linked.exists():
                        issues.append(f"Missing local link: {name} -> {target}")
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"], cwd=REPO, text=True
    ).splitlines()
    allowed = ("zapote/power-stage-120v/validation-results/",
               "zapote/power-stage-120v/validation-plan/00-MASTER-PLAN.md")
    issues.extend(f"Unexpected tracked edit: {name}" for name in changed
                  if not name.startswith(allowed))
    result = {
        "scope": "File identity, JSON validity, local links, packaging and tracked edit scope",
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "board_sha256": hashlib.sha256((UNIT / "native-15/section.kicad_pcb").read_bytes()).hexdigest(),
        "file_count": len(hashes), "bytes": byte_count,
        "missing_packets": missing_packets, "issues": issues,
        "artifact_sha256": hashes,
        "status": "PASS" if not issues and not missing_packets else "INCOMPLETE_OR_FAILED",
        "qualification": "Does not test electrical or thermal acceptance; vendor runtime is external",
    }
    (HERE / "packet-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "artifact_sha256"}, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
