#!/usr/bin/env python3
"""Fail closed when external DRC finds a violation on emitted copper.

The CLI consumes normalized JSON so the route orchestrator can persist the
same evidence it used for its output board. KiCad parsing stays in the shared
DRC wrapper; this gate owns only the attribution decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(repo_root: Path) -> None:
    src = repo_root / "packages" / "temper-placer" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drc-json", type=Path, required=True)
    parser.add_argument("--emitted-json", type=Path, required=True)
    parser.add_argument("--tolerance-mm", type=float, default=0.05)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    _load(repo_root)
    from temper_placer.validation._drc_api import DrcError
    from temper_placer.validation.prover_soundness import EmittedCopper, attribute_drc_errors

    drc_data = json.loads(args.drc_json.read_text(encoding="utf-8"))
    emitted_data = json.loads(args.emitted_json.read_text(encoding="utf-8"))
    errors = tuple(
        DrcError(
            rule=str(item.get("rule", "unknown")),
            severity=str(item.get("severity", "error")),
            location=(float(item["location"][0]), float(item["location"][1])),
            message=str(item.get("message", "")),
            nets=[str(net) for net in item.get("nets", [])],
        )
        for item in drc_data.get("errors", [])
    )
    emitted = tuple(
        EmittedCopper(
            identity=str(item["identity"]),
            kind=item["kind"],
            net=str(item["net"]),
            bbox=tuple(float(value) for value in item["bbox"]),
        )
        for item in emitted_data
    )
    result = attribute_drc_errors(errors, emitted, tolerance_mm=args.tolerance_mm)
    print(
        f"prover soundness: emitted_errors={result.emitted_error_count} "
        f"inherited_errors={result.inherited_error_count}"
    )
    for error, identities in result.emitted:
        print(f"FAIL: {error.rule} at {error.location} attributed to {', '.join(identities)}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
