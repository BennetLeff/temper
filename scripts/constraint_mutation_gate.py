#!/usr/bin/env python3
"""Constraint mutation gate — enforce registered kill sets for every encoder surface.

R32 / KTD3 / KTD4: every CP-SAT constraint encoding must carry a registered,
non-empty kill set (the R4 bug-class mutations its own defenses catch), and no
survivor may be untriaged. This script AST-scans the two encoder surfaces and
verifies each against ``power_pcb_dataset/constraint_kill_sets.yaml``:

  1. PCL handler surfaces (``placer/cp_sat/handlers/*.py``, discovered via the
     ``@register_handler`` decorator) must have a register entry with a
     non-empty ``killed`` list, and every ``survived`` mutation must carry a
     triage status (``benign`` with rationale, or ``test-gap`` with rationale).
  2. Router-V6 constraint classes (``router_v6/constraint_model.py``,
     ``Constraint`` subclasses) must be registered — either active with a
     non-empty kill set, or explicitly deferred with a documented reason (the
     family's ESL/BMC defense machinery is currently removed; see the register).
  3. Register entries that resolve to no real handler or constraint class are
     stale and fail the gate (anti-drift: the register must not outlive the
     surface it documents).

Exit codes (following the import_linter_gate.py / bmc_adoption_gate.py pattern):
  0 — every surface registered with a non-empty, triaged kill set
  3 — missing entry, empty kill set, or untriaged survivor
  5 — tool error (missing files, malformed register)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HANDLERS_DIR = (
    REPO_ROOT / "packages/temper-placer/src/temper_placer/placer/cp_sat/handlers"
)
CONSTRAINT_MODEL = (
    REPO_ROOT / "packages/temper-placer/src/temper_placer/router_v6/constraint_model.py"
)
REGISTER = REPO_ROOT / "power_pcb_dataset/constraint_kill_sets.yaml"

EXIT_OK = 0
EXIT_MISSING = 3
EXIT_ERROR = 5

VALID_TRIAGE = ("benign", "test-gap")


def _die(code: int, msg: str) -> None:
    print(f"[MUTATION-GATE] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# AST scans (pure, no temper_placer import — fast and CI-safe)
# ---------------------------------------------------------------------------


def discover_handler_surfaces() -> list[str]:
    """Return sorted surface ids for every ``@register_handler`` encoder module."""
    surfaces: list[str] = []
    for path in sorted(HANDLERS_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text())
        registered = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Name)
                        and dec.func.id == "register_handler"
                    ):
                        registered = True
        if registered:
            surfaces.append(path.stem)
    return sorted(surfaces)


def discover_router_v6_classes() -> list[str]:
    """Return sorted Constraint subclasses in ``constraint_model.py``."""
    tree = ast.parse(CONSTRAINT_MODEL.read_text())
    classes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "Constraint" and node.name != "Constraint":
                classes.append(node.name)
    return sorted(classes)


# ---------------------------------------------------------------------------
# Register loading
# ---------------------------------------------------------------------------


def load_register(path: Path) -> dict:
    import yaml

    if not path.exists():
        _die(EXIT_ERROR, f"kill-set register not found: {path}")
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        _die(EXIT_ERROR, f"kill-set register is not valid YAML: {exc}")
    if not isinstance(doc, dict) or "families" not in doc:
        _die(EXIT_ERROR, "kill-set register missing 'families' section")
    return doc


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_handler_surfaces(doc: dict) -> list[str]:
    """Require a non-empty killed set and triaged survivors per handler."""
    violations: list[str] = []
    family = doc.get("families", {}).get("placer-pcl-handlers", {})
    registered: dict[str, dict] = {}
    for surface in family.get("surfaces", []):
        sid = surface.get("id")
        if not sid:
            violations.append("register has a handler surface entry without an id")
            continue
        registered[sid] = surface

    for sid in discover_handler_surfaces():
        surface = registered.get(sid)
        if surface is None:
            violations.append(f"  {sid}: no kill-set register entry (new encoder?)")
            continue
        mutations = surface.get("mutations", [])
        killed = [
            m for m in mutations
            if m.get("outcome") == "killed"
        ]
        if not killed:
            violations.append(
                f"  {sid}: empty kill set — no mutation is killed by the "
                f"encoding's defenses ({len(mutations)} registered mutations)"
            )
        for m in mutations:
            if m.get("outcome") != "survived":
                continue
            triage = m.get("triage")
            if triage not in VALID_TRIAGE:
                violations.append(
                    f"  {sid}:{m.get('id')} survives without a triage status "
                    f"(got {triage!r}; expected {VALID_TRIAGE})"
                )
            elif not m.get("triage_rationale"):
                violations.append(
                    f"  {sid}:{m.get('id')} triaged {triage} but carries no rationale"
                )

    # anti-drift: register entries must resolve to a real handler
    real = set(discover_handler_surfaces())
    for sid in registered:
        if sid not in real:
            violations.append(f"  {sid}: register entry resolves to no handler module")
    return violations


def check_router_v6(doc: dict) -> list[str]:
    """Require every router-V6 Constraint subclass to be registered (active or deferred)."""
    violations: list[str] = []
    family = doc.get("families", {}).get("router-v6-topology", {})
    status = family.get("status")
    classes = set(family.get("classes", []))

    real = set(discover_router_v6_classes())
    for cls in sorted(real):
        if cls not in classes:
            violations.append(
                f"  {cls}: router-V6 constraint class missing from the register"
            )
        elif status == "active":
            # an active family needs per-class kill sets (future state)
            entry = family.get("entries", {}).get(cls, {})
            if not entry.get("killed"):
                violations.append(f"  {cls}: active router-V6 entry has an empty kill set")

    if status not in ("active", "deferred"):
        violations.append(
            f"  router-v6-topology: family status must be 'active' or 'deferred', got {status!r}"
        )
    elif status == "deferred" and not family.get("deferred_reason"):
        violations.append("  router-v6-topology: deferred family missing deferred_reason")

    # anti-drift
    for cls in sorted(classes):
        if cls not in real:
            violations.append(f"  {cls}: register entry resolves to no router-V6 class")
    return violations


def main() -> None:
    if not HANDLERS_DIR.exists():
        _die(EXIT_ERROR, f"handlers dir not found: {HANDLERS_DIR}")
    if not CONSTRAINT_MODEL.exists():
        _die(EXIT_ERROR, f"constraint_model.py not found: {CONSTRAINT_MODEL}")

    doc = load_register(REGISTER)

    handler_violations = check_handler_surfaces(doc)
    router_v6_violations = check_router_v6(doc)

    violations = handler_violations + router_v6_violations
    if violations:
        header = (
            f"Constraint mutation gate FAILED: {len(violations)} violation(s) — "
            f"every encoding must carry a non-empty, triaged kill set:"
        )
        _die(EXIT_MISSING, f"{header}\n" + "\n".join(violations))

    n_surfaces = len(discover_handler_surfaces())
    n_classes = len(discover_router_v6_classes())
    print(
        f"[MUTATION-GATE] OK: {n_surfaces} handler surface(s) with non-empty, "
        f"triaged kill sets; {n_classes} router-V6 class(es) registered"
    )


if __name__ == "__main__":
    main()
