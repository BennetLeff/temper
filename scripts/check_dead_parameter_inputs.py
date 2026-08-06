#!/usr/bin/env python3
"""Dead-parameter & physics-input standing check (plan 2026-08-02-019, U3).

Runs the wire/unwire probe across every registered live gate input and every
registered physics parameter:

1.  **Registry validation** — every declared gate input resolves to a real
    field on its container; every physics parameter resolves at its source,
    carries a deterministic perturbation, and names resolvable consumers;
    the physics-config scan flags new float fields on registered physics
    configs that are neither registered in ``physics_parameter_map.yaml``
    nor on the documented allowlist (the "unregistered parameter" failure
    of U3 scenario 3).
2.  **Gate probes** — the acceptance-gate inner (placement-audit) surface:
    each declared input is fail-forced and the audit verdict must flip.
3.  **Physics probes** — each registered parameter is perturbed
    deterministically at its source and its downstream output must move
    beyond the measured noise floor (or flip the verdict for gate
    consumers).

Exit codes:
- 0: every probed input/parameter is live (UNMEASURED / inconclusive
  records are reported as warnings — see the plan's deferred work for
  non-mechanical fail-forcing derivation).
- 1: at least one dead input/parameter, an unregistered physics parameter,
  or a registry validation error.
- 2: usage/import error (cannot load the registry).

Modes:
- (default) run validation + all probes and report.
- ``--list-registry`` print the registry (gates, CI-script survey, tracked
  findings, physics parameters) and exit 0.
- ``--json`` emit machine-readable JSON records on stdout.

Landing discipline: the CI step wires this check warn-only
(``continue-on-error`` with a warning annotation) until the first-run
remediation triage lands (plan U3 step 2).  The script itself is strict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "packages" / "temper-placer" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from temper_placer.validation.dead_parameter_probe import (  # noqa: E402
    DEAD,
    run_all_probes,
    summarize,
)
from temper_placer.validation.gate_input_registry import (  # noqa: E402
    build_default_registry,
    scan_unregistered_physics_fields,
    validate_registry,
)

EXIT_OK = 0
EXIT_DEAD = 1
EXIT_IMPORT = 2


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list-registry", action="store_true", help="print the registry and exit")
    parser.add_argument("--json", action="store_true", help="emit JSON probe records")
    args = parser.parse_args(argv)

    try:
        registry = build_default_registry()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not build registry: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_IMPORT

    if args.list_registry:
        print(_render_registry(registry))
        return EXIT_OK

    # 1. Registry validation + unregistered-parameter scan.
    problems: list[str] = list(validate_registry(registry))
    problems.extend(scan_unregistered_physics_fields(registry))
    for problem in problems:
        print(f"FAIL {problem}")

    # 2. Probes.
    records = run_all_probes(registry)
    if args.json:
        payload = json.dumps([_record_to_json(r) for r in records], indent=2)
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        for rec in records:
            if rec.disposition == DEAD:
                print(f"FAIL {rec.target}: DEAD — {rec.detail}", file=sys.stderr)
            elif rec.disposition not in ("live",):
                print(f"WARN {rec.target}: {rec.disposition} — {rec.detail}", file=sys.stderr)
        print(payload)
        return EXIT_DEAD if (problems or any(r.disposition == DEAD for r in records)) else EXIT_OK

    print(summarize(records))

    dead = [r for r in records if r.disposition == DEAD]
    for rec in dead:
        print(f"FAIL {rec.target}: DEAD — {rec.detail}")
    for rec in records:
        if rec.disposition not in (DEAD, "live"):
            print(f"WARN {rec.target}: {rec.disposition} — {rec.detail}")

    if problems or dead:
        return EXIT_DEAD
    print("OK: every registered input and parameter is live")
    return EXIT_OK


def _record_to_json(rec) -> dict:
    return {
        "target": rec.target,
        "kind": rec.kind,
        "disposition": rec.disposition,
        "baseline_outcome": rec.baseline_outcome,
        "perturbed_outcome": rec.perturbed_outcome,
        "delta": rec.delta,
        "noise_floor": rec.noise_floor,
        "detail": rec.detail,
    }


def _render_registry(registry) -> str:
    lines = ["=== Gate inputs ==="]
    for gate in registry.gates:
        lines.append(f"{gate.name} ({gate.kind})")
        for spec in gate.declared_inputs:
            status = f"covered={spec.covered}" if spec.covered else f"non-covered: {spec.reason}"
            lines.append(f"  - {spec.name} [{spec.container}] {status}")
    lines.append("=== Non-covered inputs ===")
    for spec in registry.non_covered:
        lines.append(f"  - {spec.name}: {spec.reason}")
    lines.append("=== CI gate script survey (U1/U4) ===")
    for spec in registry.ci_scripts:
        lines.append(f"  - {spec.script} input={spec.declared_input or '-'}")
    lines.append("=== Tracked findings ===")
    for f in registry.tracked_findings:
        lines.append(f"  - [{f.status}] {f.id} ({f.remediation_unit}): {f.title}")
    lines.append("=== Physics parameters ===")
    for p in registry.physics_parameters:
        pert = p.perturbation
        lines.append(
            f"  - {p.name} source={p.source} default={p.default} "
            f"perturb={pert['mode']}{pert['delta']:+.2f} scenario={p.scenario} "
            f"consumers={len(p.consumers)}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(_main())
