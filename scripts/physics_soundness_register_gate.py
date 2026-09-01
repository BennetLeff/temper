#!/usr/bin/env python3
"""R20 gate: fail CI when a physics-gated constraint encoder has no register entry.

Enforces the physics soundness-proof register
(``power_pcb_dataset/physics_soundness_register.yaml``, plan
2026-08-02-004 / R20): every physics-gated constraint surface must carry a
Chebyshev-style soundness proof (conservative bound or classified
approximation error) inventoried in the register, keyed by encoder identity.

# @req(2026-08-02-004, R20): Soundness-proof register for physics encodings
# @req(2026-08-02-004, KTD1): register is machine-readable YAML keyed by
#   encoder identity
# @req(2026-08-02-004, KTD2): the full proof lives at the encoder; the
#   register links to it
# @req(2026-08-02-004, KTD3): AST-scan gate following the bmc_adoption_gate
#   pattern (scan -> require coverage -> exit non-zero naming the gaps)
# @req(2026-08-02-004, KTD4): physics-gated is detected by dependency on the
#   physics modules (thermal_fdm, heat_removal, thermal_potential,
#   core/ipc2152) OR an explicit per-surface ``physics_gated: true`` marker

What counts as a physics-gated surface (KTD4):
  - The surface's module imports or references one of the physics modules
    (thermal_fdm, heat_removal, thermal_potential, ipc2152), OR
  - The surface's own code subtree references one of those modules, OR
  - The surface's own docstring declares the explicit marker
    ``physics_gated: true``.

What the scan covers (the placer constraint surfaces and router-V6
constraint classes):
  - ``placer/cp_sat/handlers/*.py`` -- functions decorated with
    explicit CP-SAT ``encode_*`` handler functions.
  - ``placer/cp_sat/domain_clearance.py`` -- the constraint generator
    ``generate_domain_clearance_constraints``.
  - ``router_v6/constraint_model.py`` -- classes subclassing ``Constraint``.

Exit codes (following the bmc_adoption_gate.py / import_linter_gate.py
conventions):
  0 -- every physics-gated surface has a register entry and every entry
       validates (proof type allowed, proof location resolves, coverage
       scope and provenance note present, encoder resolves to real code).
  3 -- a physics-gated surface has no register entry, a register entry is
       invalid, or the register and the code disagree (blocks merge).
  5 -- tool error (register missing/malformed, scan-set file missing,
       parser failure).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTER = REPO_ROOT / "power_pcb_dataset" / "physics_soundness_register.yaml"
DEFAULT_SRC_ROOT = REPO_ROOT / "packages" / "temper-placer" / "src"

EXIT_OK = 0
EXIT_MISSING = 3
EXIT_ERROR = 5

# KTD4: the physics modules whose reference marks a surface as physics-gated.
PHYSICS_MODULE_NAMES: tuple[str, ...] = (
    "thermal_fdm",
    "heat_removal",
    "thermal_potential",
    "ipc2152",
)

# KTD4: explicit per-surface declaration token (in the surface's own docstring).
PHYSICS_GATED_MARKER = "physics_gated: true"

# KTD1: the two allowed proof forms per the R24 discipline.
ALLOWED_PROOF_TYPES: tuple[str, ...] = ("conservative-bound", "classified-error")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The scan set: which modules hold constraint surfaces, and how to find the
# surfaces inside each.  ``selector`` is one of:
#   "handler_functions"      -- public encode_* functions in handler modules
#   "symbols"                -- the exact named functions
#   "constraint_subclasses"  -- classes subclassing Constraint
SCAN_SPECS: tuple[dict[str, Any], ...] = (
    {
        "glob": "temper_placer/placer/cp_sat/handlers/*.py",
        "selector": "handler_functions",
    },
    {
        "path": "temper_placer/placer/cp_sat/domain_clearance.py",
        "selector": "symbols",
        "symbols": ("generate_domain_clearance_constraints",),
    },
    {
        "path": "temper_placer/router_v6/constraint_model.py",
        "selector": "constraint_subclasses",
    },
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Surface:
    """One discovered constraint surface (an encoder or constraint class)."""

    rel_path: str  # path relative to src_root, e.g. temper_placer/.../separated.py
    symbol: str  # function or class name
    kind: str  # handler-encoder | constraint-generator | constraint-class
    physics_gated: bool
    reasons: tuple[str, ...] = ()

    @property
    def encoder_key(self) -> str:
        """The register identity key (KTD1): dotted module path + symbol."""
        module = self.rel_path.removesuffix(".py").replace("/", ".")
        return f"{module}.{self.symbol}"


@dataclass
class RegisterEntry:
    """One parsed register entry, carrying any schema violations."""

    encoder: str
    proof_type: str
    proof_path: str
    proof_symbol: str
    coverage_scope: str
    exemptions: str | None
    audit: str | None
    last_verified: str
    provenance_note: str
    errors: list[str] = field(default_factory=list)


@dataclass
class Report:
    """Gate outcome: tool errors (exit 5) vs coverage errors (exit 3)."""

    tool_errors: list[str] = field(default_factory=list)
    coverage_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    covered: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.tool_errors and not self.coverage_errors


# ---------------------------------------------------------------------------
# Register loading + entry validation
# ---------------------------------------------------------------------------


def load_register(register_path: Path) -> dict[str, Any]:
    """Parse the register YAML.  Raises on missing/malformed file."""
    if not register_path.exists():
        raise FileNotFoundError(f"register not found: {register_path}")
    try:
        with open(register_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"register is malformed YAML: {register_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"register is not a mapping: {register_path}")
    return data


def parse_entries(register: dict[str, Any]) -> list[RegisterEntry]:
    """Extract and schema-validate every entry in the register's ``surfaces``.

    Schema violations (missing/empty required fields) land in each entry's
    ``errors`` list rather than raising, so the gate reports ALL of them.
    """
    raw_surfaces = register.get("surfaces")
    if not isinstance(raw_surfaces, list):
        raise ValueError("register is missing a non-empty 'surfaces' list")

    entries: list[RegisterEntry] = []
    for i, raw in enumerate(raw_surfaces):
        if not isinstance(raw, dict):
            entries.append(
                RegisterEntry(
                    encoder=f"<surfaces[{i}]>",
                    proof_type="",
                    proof_path="",
                    proof_symbol="",
                    coverage_scope="",
                    exemptions=None,
                    audit=None,
                    last_verified="",
                    provenance_note="",
                    errors=[f"surfaces[{i}] is not a mapping"],
                )
            )
            continue

        loc = raw.get("proof_location") or {}
        if not isinstance(loc, dict):
            loc = {}
        entry = RegisterEntry(
            encoder=str(raw.get("encoder", "")).strip(),
            proof_type=str(raw.get("proof_type", "")).strip(),
            proof_path=str(loc.get("path", "")).strip(),
            proof_symbol=str(loc.get("symbol", "")).strip(),
            coverage_scope=str(raw.get("coverage_scope", "")).strip(),
            exemptions=(
                str(raw["exemptions"]).strip() if raw.get("exemptions") is not None else None
            ),
            audit=str(raw.get("audit", "")).strip() or None,
            last_verified=str(raw.get("last_verified", "")).strip(),
            provenance_note=str(raw.get("provenance_note", "")).strip(),
        )

        # ---- schema rules (U1 + U4) ----
        if not entry.encoder:
            entry.errors.append("missing required field: encoder")
        if not entry.proof_type:
            entry.errors.append("missing required field: proof_type (add requires proof type)")
        elif entry.proof_type not in ALLOWED_PROOF_TYPES:
            entry.errors.append(
                f"unknown proof_type {entry.proof_type!r}; must be one of "
                + ", ".join(ALLOWED_PROOF_TYPES)
            )
        if not entry.proof_path:
            entry.errors.append("missing required field: proof_location.path")
        if not entry.proof_symbol:
            entry.errors.append("missing required field: proof_location.symbol")
        if not entry.coverage_scope:
            entry.errors.append("missing required field: coverage_scope")
        if not entry.last_verified:
            entry.errors.append("missing required field: last_verified")
        elif not DATE_RE.match(entry.last_verified):
            entry.errors.append(
                f"last_verified {entry.last_verified!r} is not a YYYY-MM-DD date"
            )
        if not entry.provenance_note:
            entry.errors.append(
                "missing required field: provenance_note (edits require a provenance note)"
            )
        entries.append(entry)
    return entries


def encoder_source_file(encoder_key: str, src_root: Path) -> Path | None:
    """Map an encoder key like ``pkg.mod.symbol`` to its source file under
    ``src_root``, or None if the module part does not resolve."""
    module, _, symbol = encoder_key.rpartition(".")
    if not module or not symbol:
        return None
    rel = module.replace(".", "/") + ".py"
    return src_root / rel


def _is_pure_delegation_reexport(node: ast.AST, symbol: str) -> bool:
    """True if ``node`` is a top-level ``symbol = <dotted attribute chain>``
    assignment -- the pure-delegation re-export pattern this repo uses when a
    pyclass migrates from Python to a pyo3/maturin Rust extension (e.g.
    ``core/net_types.py``; ``router_v6/constraint_model.py``'s own module
    docstring names this "the pure-delegation pattern"). The name is real,
    live, importable code -- it is just bound via assignment rather than a
    ``class``/``def`` statement, which the plain FunctionDef/ClassDef check
    above does not recognize on its own.

    Deliberately narrow: only a single ``Name`` target whose value is a bare
    name or an attribute-chain rooted in one (``_mb.CapacityConstraint``,
    ``_tdb.model_builder.CapacityConstraint``) counts. This is intentionally
    unable to be satisfied by a same-named local holding an unrelated literal
    or call result -- it is not a general "any assignment resolves" carve-out.
    """
    if not isinstance(node, ast.Assign):
        return False
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return False
    if node.targets[0].id != symbol:
        return False
    value = node.value
    while isinstance(value, ast.Attribute):
        value = value.value
    return isinstance(value, ast.Name)


def encoder_resolves(encoder_key: str, src_root: Path) -> tuple[bool, str]:
    """True if the encoder key resolves to a real function/class -- or a real
    pure-delegation re-export of one (see ``_is_pure_delegation_reexport``)
    -- in a real file under ``src_root``.  Returns (ok, detail)."""
    src_file = encoder_source_file(encoder_key, src_root)
    if src_file is None or not src_file.exists():
        return False, f"encoder source file not found for {encoder_key}"
    try:
        tree = ast.parse(src_file.read_text(), filename=str(src_file))
    except SyntaxError as exc:
        return False, f"encoder source unparseable: {src_file}: {exc}"
    symbol = encoder_key.rpartition(".")[2]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == symbol:
            return True, str(src_file)
        if _is_pure_delegation_reexport(node, symbol):
            return True, f"{src_file} (pure-delegation re-export, e.g. a Rust migration)"
    return False, f"encoder symbol not found in {src_file}"


def validate_proof_location(entry: RegisterEntry, repo_root: Path) -> None:
    """U1/U2: proof_location.path must exist and contain proof_location.symbol
    (substring check).  A missing symbol is the stale-proof class -- the proof
    the register cites no longer exists in the file, so it is flagged, not
    silently carried."""
    proof_file = repo_root / entry.proof_path
    if not proof_file.exists():
        entry.errors.append(
            f"proof_location.path does not exist: {entry.proof_path}"
        )
        return
    text = proof_file.read_text(errors="replace")
    if entry.proof_symbol not in text:
        entry.errors.append(
            f"proof_location.symbol {entry.proof_symbol!r} not found in "
            f"{entry.proof_path} (stale proof class: cited proof no longer in file)"
        )


# ---------------------------------------------------------------------------
# Surface discovery + physics-gated detection (KTD4)
# ---------------------------------------------------------------------------


def _module_references_physics(tree: ast.AST) -> bool:
    """True if any import/reference in the module names a physics module."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            if any(name in module for name in PHYSICS_MODULE_NAMES):
                return True
        elif isinstance(node, ast.Name) and node.id in PHYSICS_MODULE_NAMES:
            return True
    return False


def _surface_references_physics(node: ast.AST) -> bool:
    """True if the surface's own code subtree references a physics module."""
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Import, ast.ImportFrom)):
            module = getattr(sub, "module", "") or ""
            if any(name in module for name in PHYSICS_MODULE_NAMES):
                return True
        elif isinstance(sub, ast.Name) and sub.id in PHYSICS_MODULE_NAMES:
            return True
    return False


def _docstring_has_marker(node: ast.AST) -> bool:
    doc = ast.get_docstring(node)
    return doc is not None and PHYSICS_GATED_MARKER in doc


def _surface_defs(tree: ast.AST, spec: dict[str, Any]) -> list[ast.AST]:
    """Select the surface nodes from a module AST per the scan spec."""
    selector = spec["selector"]
    selected: list[ast.AST] = []
    for node in tree.body:
        if selector == "handler_functions":
            if isinstance(node, ast.FunctionDef) and node.name.startswith("encode_"):
                selected.append(node)
        elif selector == "symbols":
            if isinstance(node, ast.FunctionDef) and node.name in spec["symbols"]:
                selected.append(node)
        elif selector == "constraint_subclasses":
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "Constraint" and node.name != "Constraint":
                    selected.append(node)
                    break
    return selected


def discover_surfaces(src_root: Path, scan_specs: Iterable[dict[str, Any]] = SCAN_SPECS) -> tuple[list[Surface], list[str]]:
    """Scan the surface modules and classify each surface (KTD4).

    Returns (surfaces, tool_errors).  A missing/unparseable scan-set module
    is a tool error (exit 5), not a coverage gap.
    """
    surfaces: list[Surface] = []
    tool_errors: list[str] = []

    for spec in scan_specs:
        if "glob" in spec:
            matches = sorted(src_root.glob(spec["glob"]))
            if not matches:
                tool_errors.append(f"scan glob matched no files: {spec['glob']}")
            paths = matches
        else:
            paths = [src_root / spec["path"]]

        for path in paths:
            if not path.exists():
                tool_errors.append(f"scan-set module not found: {path}")
                continue
            try:
                tree = ast.parse(path.read_text(), filename=str(path))
            except SyntaxError as exc:
                tool_errors.append(f"scan-set module unparseable: {path}: {exc}")
                continue

            rel_path = path.relative_to(src_root).as_posix()
            module_refs_physics = _module_references_physics(tree)
            for node in _surface_defs(tree, spec):
                reasons: list[str] = []
                if module_refs_physics:
                    reasons.append("module imports/references a physics module")
                if _surface_references_physics(node):
                    reasons.append("surface code references a physics module")
                if _docstring_has_marker(node):
                    reasons.append(f"docstring declares {PHYSICS_GATED_MARKER!r}")
                surfaces.append(
                    Surface(
                        rel_path=rel_path,
                        symbol=node.name,
                        kind={
                            "handler_functions": "handler-encoder",
                            "symbols": "constraint-generator",
                            "constraint_subclasses": "constraint-class",
                        }[spec["selector"]],
                        physics_gated=bool(reasons),
                        reasons=tuple(reasons),
                    )
                )
    return surfaces, tool_errors


# ---------------------------------------------------------------------------
# Coverage check (both directions)
# ---------------------------------------------------------------------------


def check_coverage(
    entries: list[RegisterEntry],
    surfaces: list[Surface],
    report: Report,
    src_root: Path,
) -> None:
    """Every physics-gated surface needs an entry; every entry must resolve
    to a real surface in code (register and code must agree)."""
    by_key = {e.encoder: e for e in entries}

    # Direction A: detected physics-gated surface without a register entry.
    for surface in surfaces:
        if not surface.physics_gated:
            continue
        if surface.encoder_key not in by_key:
            report.coverage_errors.append(
                f"physics-gated surface has no register entry: {surface.encoder_key}"
                f"  [detected via: {', '.join(surface.reasons)}]"
            )
        else:
            report.covered.append(surface.encoder_key)

    # Direction B: register entry whose encoder does not resolve to code.
    for entry in entries:
        ok, detail = encoder_resolves(entry.encoder, src_root)
        if not ok:
            report.coverage_errors.append(
                f"register entry does not resolve to code: {entry.encoder} ({detail})"
            )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_check(
    repo_root: Path = REPO_ROOT,
    register_path: Path | None = None,
    src_root: Path | None = None,
    verbose: bool = False,
) -> Report:
    """Run the full gate; returns a Report (never raises for gate outcomes)."""
    register_path = register_path or (repo_root / "power_pcb_dataset" / "physics_soundness_register.yaml")
    src_root = src_root or (repo_root / "packages" / "temper-placer" / "src")
    report = Report()

    # -- register loading (tool errors) --
    try:
        register = load_register(register_path)
    except (FileNotFoundError, ValueError) as exc:
        report.tool_errors.append(f"register load failed: {exc}")
        return report
    if "_march" not in register or not register["_march"]:
        report.tool_errors.append("register is missing the '_march' provenance log")

    try:
        entries = parse_entries(register)
    except ValueError as exc:
        report.tool_errors.append(f"register parse failed: {exc}")
        return report

    # -- schema validation of every entry (U1/U4) --
    for entry in entries:
        validate_proof_location(entry, repo_root)

    # -- surface discovery + detection (KTD3/KTD4) --
    surfaces, scan_errors = discover_surfaces(src_root)
    report.tool_errors.extend(scan_errors)

    # -- coverage (both directions) --
    check_coverage(entries, surfaces, report, src_root)

    # -- surface schema errors become coverage errors (U3: invalid entry blocks) --
    for entry in entries:
        if entry.errors:
            report.coverage_errors.append(
                f"register entry {entry.encoder or '<unnamed>'}: "
                + "; ".join(entry.errors)
            )

    if verbose:
        report.warnings.append(
            f"[VERBOSE] discovered {len(surfaces)} surface(s): "
            + ", ".join(
                f"{s.encoder_key}{' [PHYSICS-GATED: ' + '; '.join(s.reasons) + ']' if s.physics_gated else ''}"
                for s in sorted(surfaces, key=lambda s: s.encoder_key)
            )
        )
    return report


def print_report(report: Report, verbose: bool = False) -> None:
    for warning in report.warnings:
        print(f"[PHYS-SND] {warning}")
    if report.tool_errors:
        print(
            f"[PHYS-SND] ERROR ({len(report.tool_errors)}):\n  "
            + "\n  ".join(report.tool_errors),
            file=sys.stderr,
        )
    if report.coverage_errors:
        print(
            f"[PHYS-SND] FAILED: {len(report.coverage_errors)} issue(s):\n  "
            + "\n  ".join(sorted(report.coverage_errors)),
            file=sys.stderr,
        )
    if report.ok:
        print(
            f"[PHYS-SND] OK: {len(report.covered)} physics-gated surface(s) "
            f"registered with soundness proofs:"
        )
        for key in sorted(report.covered):
            print(f"  - {key}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R20 gate: physics-gated constraint surfaces need a "
        "soundness-proof register entry."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--register", type=Path, default=None, help="register YAML path")
    parser.add_argument("--src-root", type=Path, default=None, help="temper-placer src root")
    parser.add_argument("--verbose", action="store_true", help="list every discovered surface")
    args = parser.parse_args(argv)

    report = run_check(
        repo_root=args.repo_root,
        register_path=args.register,
        src_root=args.src_root,
        verbose=args.verbose,
    )
    print_report(report, verbose=args.verbose)

    if report.tool_errors:
        return EXIT_ERROR
    if report.coverage_errors:
        return EXIT_MISSING
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
