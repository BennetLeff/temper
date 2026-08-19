#!/usr/bin/env python3
"""Enclosure-declaration gate: the pollution-degree classification must be
declared, verified, resolvable, and identically enforced everywhere.

What problem this closes
------------------------
The board's pollution-degree classification sets the reinforced HV<->SELV
creepage requirement -- the single most consequential safety number in this
design. It used to be a **literal** (``MIN_BARRIER_WIDTH_MM = 12.6``), with
the alternative (8.0 mm, PD2) in a docstring and the rationale in an evidence
document. Three structural gaps followed:

1. **Nothing connected them.** Every investigation re-derived the reasoning
   and some got it wrong.
2. **The stated precondition was unverifiable.** The docstring's *"sealed,
   gasketed PCB compartment ... verified before release"* had no mechanism
   behind it -- the same defect class as a creepage checker that reported 242
   violations and exited 0, and as ``verify_proofs.py`` claiming CI
   enforcement since 2026-06-28 with no workflow ever running it.
3. **The physical state and the number could drift silently in both
   directions.** Build the compartment, nothing loosened; remove it, nothing
   re-tightened.

``elec/enclosure_manifest.yaml`` (the declaration),
``packages/temper-design-bundle/src/enclosure.rs`` (the rule and the
derivation) and ``temper_placer.core.enclosure_declaration`` (the loader)
close (1) and (3). **This gate is what closes (2)**, as far as software can.

WHAT THIS GATE CANNOT DO -- printed on every run, not just written here
----------------------------------------------------------------------
**No gate makes a physical enclosure real.** Everything checked below
operates on a *claim*. This gate can ensure the claim is explicit, current,
internally consistent, and traceable to a dated measurement, and that every
enforcement point in the tree agrees with the number it implies. It cannot
observe a cover, a gasket, or an airflow path. The sealing itself is a
manufacturing and QA matter. A mechanism that implied more assurance than it
provides would be worse than none, which is why this paragraph is part of the
gate's output and not only its docstring.

What this gate checks
---------------------
1. **The declaration resolves at all.** Delegated to
   ``temper_placer.core.enclosure_declaration.resolve_declaration`` -- the
   same code path the production constant is computed by, so this gate cannot
   pass on a declaration the library would reject, or vice versa. That covers:
   missing/empty/unparseable file, wrong ``schema_version``, unknown keys
   (including a hand-written ``pollution_degree``), placeholder verification
   fields, a malformed ``measured_at_commit``, and a **stale** declaration
   (facts edited after the verification digest that backs them).
2. **The verification commit resolves -- unconditionally.** The library only
   needs this when the PD2 exception is claimed (so a PD3 import never shells
   out to git). This gate checks it on *every* run, via
   ``check_evidence_provenance.verify_commits_exist`` -- the repo's canonical
   batched ``git cat-file --batch-check`` mechanism, which raises on a shallow
   clone rather than reporting every historical SHA as fake. A well-formed but
   dangling anchor is a hard failure, worse than an honest gap, because it
   claims traceability it does not have while looking exactly like a record
   that does.
   *This is the check the ceiling corpus did not have*: its "fully-evidenced"
   control used ``measured_at_commit = "0" * 40``, which the ratchet rejected
   as unresolvable, so the control never ran and the specificity half of R9
   was dead for months. **Verification must resolve, not merely be present.**
3. **Every named artifact exists.** A dated verification pointing at a
   document that is not in the tree is not a verification.
4. **Every consumer of the classification sees the identical figure.** The
   gate imports each enforcement point and compares its live value against the
   declaration-derived one. This is the half that catches drift in the
   *loosening* direction: flip the declaration to a sealed compartment and any
   enforcement point still carrying the PD3 number fails here, rather than
   quietly disagreeing with the rest of the tree.

Exit codes (mirrors ``check_pd2_compartment_evidence.py``, same job, same
reader):
  0 - PASSED
  3 - VIOLATION: the declaration is unusable, unbacked, or a consumer
      disagrees with it
  5 - GATE ERROR: the gate could not run a trustworthy check (shallow clone,
      git unavailable, a consumer that cannot be imported)

Usage:
  uv run python scripts/check_enclosure_declaration.py
  uv run python scripts/check_enclosure_declaration.py --declaration PATH
  uv run python scripts/check_enclosure_declaration.py --print-digest
  uv run python scripts/check_enclosure_declaration.py \\
      --print-digest --sealed --gasketed --outside-forced-air-path
"""

from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_DECLARATION = REPO_ROOT / "elec" / "enclosure_manifest.yaml"

# The design margin the CP-SAT placement corridor carries over the barrier
# width. Named here only so this gate can state the relationship it is
# checking; the value itself is owned by
# `temper_placer.placer.cp_sat.isolation_barrier`, which computes it from
# MIN_BARRIER_WIDTH_MM rather than restating it.
_CORRIDOR_DESIGN_MARGIN_MM = 0.5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass(frozen=True)
class Consumer:
    """One enforcement point that must agree with the derived classification.

    ``module``/``attribute`` are imported and read *live* rather than
    text-scraped: a regex over source can be defeated by a derivation
    (which is exactly what this change turns several of these into), and the
    question here is what the running system enforces, not what its source
    spells.
    """

    module: str
    attribute: str
    description: str
    offset_mm: float = 0.0
    """Some consumers legitimately carry a design margin over the barrier
    width (the CP-SAT corridor is barrier + 0.5 mm). The offset is declared
    here so a *changed* margin is a visible diff in this file, not an
    unexplained mismatch."""


CONSUMERS: tuple[Consumer, ...] = (
    Consumer(
        module="temper_placer.core.isolation_constants",
        attribute="MIN_BARRIER_WIDTH_MM",
        description="isolation-barrier SSOT (keepout gate + CP-SAT corridor)",
    ),
    Consumer(
        module="temper_placer.placer.cp_sat.isolation_barrier",
        attribute="DEFAULT_CORRIDOR_WIDTH_MM",
        description="CP-SAT placement corridor width",
        offset_mm=_CORRIDOR_DESIGN_MARGIN_MM,
    ),
    Consumer(
        module="temper_placer.placer.cp_sat.gates",
        attribute="HV_LV_CREEPAGE_MM",
        description="IECCreepageGate HV<->LV threshold (post-route DRC)",
    ),
    Consumer(
        module="generate_kicad_dru",
        attribute="HV_CREEPAGE_ENFORCED_MM",
        description="KiCad DRU emitter (the figure the board is DRC'd against)",
    ),
    Consumer(
        module="check_isolation_keepout",
        attribute="MIN_BARRIER_WIDTH_MM",
        description="physical isolation-keepout gate",
    ),
)


def _print_limitation(resolution) -> None:
    print()
    print("LIMIT OF THIS GATE (not a formality -- read it before quoting the result):")
    for line in _wrap(resolution.limitation(), 74):
        print(f"  {line}")
    print(
        "  A PASS below means the CLAIM is well-formed, backed and consistently\n"
        "  enforced. It is not evidence that any enclosure was built or sealed."
    )


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def check_commit_resolves(sha: str, repo_root: Path) -> None:
    """Fail closed unless *sha* resolves to a real commit object.

    Uses the repo's canonical mechanism rather than a second implementation:
    ``check_evidence_provenance.verify_commits_exist`` already batches this,
    already rejects non-commit object types, and already raises on a shallow
    clone (where "nothing resolves" is indistinguishable from "everything is
    fabricated"). A ``RuntimeError`` from it is a GATE ERROR, never a pass.
    """
    try:
        from check_evidence_provenance import verify_commits_exist
    except ImportError as exc:  # pragma: no cover - import wiring
        raise GateError(
            f"cannot import verify_commits_exist to check the verification "
            f"commit: {exc}"
        ) from exc

    try:
        resolved = verify_commits_exist({sha}, repo_root)
    except RuntimeError as exc:
        raise GateError(
            f"could not verify whether the enclosure declaration's "
            f"verification commit {sha} resolves: {exc}"
        ) from exc

    if not resolved.get(sha, False):
        raise _Violation(
            f"verification.measured_at_commit {sha} does not resolve to a "
            f"commit object in this repository. The declaration claims "
            f"traceability it does not have -- which is worse than an honest "
            f"gap, because it looks exactly like a record that does. This is "
            f"the ceiling corpus's dead 'fully-evidenced' control, in a place "
            f"where the consequence is a safety figure."
        )


class _Violation(Exception):
    """A real, checkable defect in the declaration or its enforcement."""


def check_artifacts_exist(artifacts: list[str], repo_root: Path) -> None:
    missing = [a for a in artifacts if not (repo_root / a).exists()]
    if missing:
        raise _Violation(
            "verification.artifacts names files that are not in the tree: "
            + ", ".join(missing)
            + ". A dated verification pointing at a document that does not "
            "exist is not a verification."
        )


def check_consumers(expected_mm: float, pollution_degree: int) -> list[str]:
    """Return one failure line per consumer whose live value disagrees."""
    failures: list[str] = []
    for consumer in CONSUMERS:
        try:
            module = importlib.import_module(consumer.module)
        except Exception as exc:  # noqa: BLE001 - any import failure is fatal
            raise GateError(
                f"could not import consumer {consumer.module} "
                f"({consumer.description}): {exc}. A consumer this gate cannot "
                f"read is a consumer this gate cannot vouch for."
            ) from exc
        try:
            actual = float(getattr(module, consumer.attribute))
        except AttributeError as exc:
            raise GateError(
                f"{consumer.module}.{consumer.attribute} no longer exists "
                f"({consumer.description}). Either the consumer was renamed -- "
                f"update CONSUMERS in this gate -- or an enforcement point was "
                f"deleted, which is not something this gate may silently allow."
            ) from exc

        want = expected_mm + consumer.offset_mm
        if actual != want:
            margin = (
                f" (barrier {expected_mm} + {consumer.offset_mm} design margin)"
                if consumer.offset_mm
                else ""
            )
            failures.append(
                f"{consumer.module}.{consumer.attribute} = {actual} mm, but the "
                f"declared enclosure derives PD{pollution_degree} -> {want} mm"
                f"{margin} -- {consumer.description}"
            )
        else:
            print(
                f"  [OK] {consumer.module}.{consumer.attribute} = {actual} mm "
                f"-- {consumer.description}"
            )
    return failures


def run(declaration_path: Path, repo_root: Path) -> int:
    try:
        from temper_placer.core.enclosure_declaration import (
            EnclosureDeclarationError,
            resolve_declaration,
        )
    except ImportError as exc:
        print(
            "GATE ERROR: cannot import temper_placer.core.enclosure_declaration "
            f"({exc}). Rebuild the pyo3 extensions ('make extensions') -- a "
            "stale temper_design_bundle_python has no "
            "resolve_enclosure_declaration, and this gate must never fall back "
            "to a value it computed itself.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    print(f"Enclosure declaration: {declaration_path}")

    try:
        resolution = resolve_declaration(declaration_path, repo_root=repo_root)
    except EnclosureDeclarationError as exc:
        print(f"VIOLATION: {exc}", file=sys.stderr)
        _emit_summary(f"VIOLATION: {exc}")
        return EXIT_VIOLATION

    print(
        f"  declared: sealed={resolution.sealed} "
        f"gasketed={resolution.gasketed} "
        f"outside_forced_air_path={resolution.outside_forced_air_path}"
    )
    print(
        f"  verified: {resolution.verified_on} at "
        f"{resolution.measured_at_commit}"
    )
    print(
        f"  derived:  PD{resolution.pollution_degree} -> "
        f"{resolution.barrier_width_mm} mm reinforced HV<->SELV creepage"
    )
    print(f"  chain:    {resolution.provenance}")
    if resolution.pd2_exception_claimed:
        print(
            "  NOTE: this declaration CLAIMS the IEC 60335-2-6 cl. 29.2 "
            "Addition PD2 exception."
        )

    try:
        check_commit_resolves(resolution.measured_at_commit, repo_root)
        check_artifacts_exist(_artifacts_of(declaration_path), repo_root)
        print("Consumers of the classification:")
        failures = check_consumers(
            resolution.barrier_width_mm, resolution.pollution_degree
        )
    except _Violation as exc:
        print(f"VIOLATION: {exc}", file=sys.stderr)
        _print_limitation(resolution)
        _emit_summary(f"VIOLATION: {exc}")
        return EXIT_VIOLATION
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        _emit_summary(f"GATE ERROR: {exc}")
        return EXIT_GATE_ERROR

    if failures:
        print(
            "VIOLATION: enforcement points disagree with the declared "
            "classification:",
            file=sys.stderr,
        )
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        _print_limitation(resolution)
        _emit_summary("VIOLATION: " + "; ".join(failures))
        return EXIT_VIOLATION

    print(
        f"\nPASSED -- declaration is well-formed, backed by a resolvable "
        f"commit, and all {len(CONSUMERS)} enforcement points agree at "
        f"PD{resolution.pollution_degree} / {resolution.barrier_width_mm} mm."
    )
    _print_limitation(resolution)
    _emit_summary(
        f"PASSED: PD{resolution.pollution_degree}, "
        f"{resolution.barrier_width_mm} mm, {len(CONSUMERS)} consumers agree. "
        f"Checks a CLAIM, not a built enclosure."
    )
    return EXIT_OK


def _artifacts_of(declaration_path: Path) -> list[str]:
    """The declaration's ``verification.artifacts`` list.

    Read with PyYAML here rather than returned through the Rust resolution,
    because the artifact-existence check is a filesystem question about *this
    checkout* and has no place in a rule that also compiles to ``wasm32``.
    Only ever called on a document ``resolve_declaration`` has already parsed
    and accepted, so this cannot admit a shape the schema would reject.
    """
    import yaml

    data = yaml.safe_load(declaration_path.read_text(encoding="utf-8"))
    return list(data["verification"]["artifacts"])


def _emit_summary(message: str) -> None:
    path = get_github_summary_path()
    if path is None:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"### Enclosure declaration gate\n\n{message}\n\n")


def _print_digest(sealed: bool, gasketed: bool, outside: bool) -> int:
    try:
        import temper_design_bundle_python as tdb
    except ImportError as exc:  # pragma: no cover - import wiring
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR
    digest = tdb.enclosure_facts_digest(sealed, gasketed, outside)
    pd = tdb.enclosure_pollution_degree(sealed, gasketed, outside)
    print(
        f"sealed={sealed} gasketed={gasketed} "
        f"outside_forced_air_path={outside}"
    )
    print(f"  declared_state_sha256: {digest}")
    print(f"  would derive:          PD{pd}")
    print(
        "\nPaste the digest into verification.declared_state_sha256 ONLY as "
        "part of recording a real, dated re-verification of the enclosure. "
        "Recomputing it to silence a stale-declaration failure, without "
        "re-verifying, defeats the entire mechanism."
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--declaration",
        type=Path,
        default=DEFAULT_DECLARATION,
        help="path to the enclosure declaration (default: elec/enclosure_manifest.yaml)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository whose object store the verification commit must resolve in",
    )
    parser.add_argument(
        "--print-digest",
        action="store_true",
        help="print the canonical declared_state_sha256 for a set of facts and exit",
    )
    parser.add_argument("--sealed", action="store_true")
    parser.add_argument("--gasketed", action="store_true")
    parser.add_argument("--outside-forced-air-path", action="store_true")
    args = parser.parse_args(argv)

    if args.print_digest:
        return _print_digest(
            args.sealed, args.gasketed, args.outside_forced_air_path
        )
    return run(args.declaration.resolve(), args.repo_root.resolve())


if __name__ == "__main__":
    sys.exit(main())
