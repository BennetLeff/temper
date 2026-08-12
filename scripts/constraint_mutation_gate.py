#!/usr/bin/env python3
"""Constraint mutation gate — enforce registered kill sets for every encoder surface.

R32 / KTD3 / KTD4: every CP-SAT constraint encoding must carry a registered,
non-empty kill set (the R4 bug-class mutations its own defenses catch), and no
survivor may be untriaged. This script verifies the two encoder surfaces
against ``power_pcb_dataset/constraint_kill_sets.yaml``:

  1. PCL handler surfaces (``placer/cp_sat/handlers/*.py``, discovered via the
     ``@register_handler`` decorator) must have a register entry with a
     non-empty ``killed`` list, and every ``survived`` mutation must carry a
     triage status (``benign`` with rationale, or ``test-gap`` with rationale).
  2. Router-V6 constraint classes (``router_v6/constraint_model.py``, resolved
     dynamically by importing the module rather than AST-scanning its source
     — see ``discover_router_v6_classes``) must be registered — either active
     with a non-empty kill set, or explicitly deferred with a documented
     reason (the family's ESL/BMC defense machinery is currently removed; see
     the register).
  3. Register entries that resolve to no real handler or constraint class are
     stale and fail the gate (anti-drift: the register must not outlive the
     surface it documents).

Live verification (2026-08-11, gate-vacuity audit / U5, fixing finding 8 of
docs/evidence/2026-08-11-gate-vacuity-audit.md): checks 1-3 above only read
``constraint_kill_sets.yaml`` — a snapshot the gate never re-verifies against
the code it certifies. A scratch-tree repro proved that gutting
``handlers/keepout.py``'s ``encode_keepout`` (deleting every enforcement
statement, including the ``AddNoOverlap2D`` call that is the sole mechanism
keeping components out of the mains<->SELV isolation keepout) leaves the
gate's exit code and output byte-identical: the register still claims
``keepout_drop_no_overlap`` is ``killed`` no matter what the encoder's source
currently says, because nothing ever re-derives that claim from current code.

Check 4 closes this: the gate re-runs ``constraint_mutation_runner.run_suite()``
live (the same AST-mutate-and-solve harness that generates the register,
~1s for all 32 registered mutations) and requires every entry's *registered*
outcome to still match what a fresh run of the *current* encoder source
produces. A mismatch means the register no longer describes reality — most
commonly because an encoder's enforcement was weakened or removed after the
register was last regenerated — and the gate fails closed rather than
silently trusting stale bookkeeping.

Exit codes (following the import_linter_gate.py / bmc_adoption_gate.py pattern):
  0 — every surface registered with a non-empty, triaged kill set, and a live
      re-run reproduces every registered outcome
  3 — missing entry, empty kill set, untriaged survivor, or a live/register
      outcome mismatch (register is stale)
  5 — tool error (missing files, malformed register)
"""

from __future__ import annotations

import ast
import importlib
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

# Sibling script, not an installed package -- import via an explicit path
# insert (mirrors tests/pcl/test_mutation_gate.py's own convention) so this
# still works regardless of CWD or how the interpreter was invoked.
_SCRIPTS_DIR = str(REPO_ROOT / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

EXIT_OK = 0
EXIT_MISSING = 3
EXIT_ERROR = 5

VALID_TRIAGE = ("benign", "test-gap", "non-applicable")


def _die(code: int, msg: str) -> None:
    print(f"[MUTATION-GATE] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Surface discovery. discover_handler_surfaces is a pure AST scan (no
# temper_placer import); discover_router_v6_classes imports temper_placer
# (see its own docstring for why an AST scan can no longer find these
# classes post Wave-4 migration).
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
    """Return sorted router-V6 constraint classes in ``constraint_model.py``.

    Pre-migration these were real ``class X(Constraint):`` definitions, and an
    ``ast.ClassDef`` scan for a ``Constraint`` base found them. The 2026-08-08
    Wave 4 migration (commit 8dce8f8ae) replaced the class bodies with
    ``X = _mb.X`` re-exports of PyO3 pyclasses that carry no Python-level
    inheritance relationship at all (confirmed: ``issubclass(CapacityConstraint,
    Constraint)`` is False at runtime post-migration, so even a runtime
    ``issubclass`` scan would not recover them) -- the AST scan has found zero
    classes, unconditionally, for three days (see the 2026-08-11 gate-vacuity
    audit, finding 8's "second defect").

    The module's ``__all__`` still names every public export, tagged by the
    repo's own "*Constraint" naming convention (``CapacityConstraint``,
    ``ChannelSeparationConstraint``, ``DiffPairConstraint``, ``LayerConstraint``
    -- as opposed to ``ConstraintModel``/``ConstraintModelEmptyError``, which
    start with, but do not end with, "Constraint"). Importing the module and
    filtering ``__all__`` by that suffix (excluding the base ``Constraint``
    name itself) recovers exactly the four classes the register expects,
    without hardcoding a class list that could itself go stale.
    """
    module = importlib.import_module("temper_placer.router_v6.constraint_model")
    classes = [
        name
        for name in getattr(module, "__all__", [])
        if name != "Constraint"
        and name.endswith("Constraint")
        and isinstance(getattr(module, name, None), type)
    ]
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
            if m.get("outcome") not in ("survived", "non-applicable"):
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


def check_live_kill_sets(doc: dict) -> list[str]:
    """Re-run the mutation suite live and require it to reproduce the register.

    This is the check that closes the 2026-08-11 gate-vacuity finding: checks
    1-3 (``check_handler_surfaces``) only ever read
    ``constraint_kill_sets.yaml`` -- a snapshot written by a prior,
    disconnected invocation of ``constraint_mutation_runner.py``. Nothing
    about the register's ``killed``/``survived``/``non-applicable`` claims is
    re-derived from the encoder source the register is supposed to describe,
    so gutting an encoder's enforcement (e.g. deleting ``keepout.py``'s
    ``AddNoOverlap2D`` call) leaves every claim -- and the gate's exit code --
    unchanged.

    ``constraint_mutation_runner.run_suite()`` is the same AST-mutate +
    pinned-solve harness that generated the register in the first place
    (``--write-register``); calling it here re-applies every registered
    mutation to the CURRENT handler source and re-classifies the outcome
    against the CURRENT defenses. Any mutation whose live outcome no longer
    matches what the register claims means the register is stale -- most
    often because a defense was weakened or an encoder's enforcement was
    removed -- and that must fail the gate, not pass through it silently.
    """
    import constraint_mutation_runner as runner

    violations: list[str] = []
    try:
        live_results = runner.run_suite()
    except RuntimeError as exc:
        # run_suite()'s own baseline sanity check: every registered defense
        # must pass against the CURRENT, unmutated encoder before any
        # mutation is even applied. A failure here is stronger evidence than
        # a stale kill-set entry -- it means the encoder's real behavior no
        # longer satisfies a scenario the register's kill claims depend on
        # (e.g. an encoder's enforcement was weakened or deleted outright).
        # Surface it as a normal, actionable gate violation instead of an
        # unhandled traceback.
        return [
            f"  live mutation suite failed its own baseline sanity check "
            f"before any mutation was applied — a registered defense no "
            f"longer passes against the CURRENT (unmutated) encoder source, "
            f"which the kill-set register's claims all depend on: {exc}"
        ]

    live = {(r.surface_id, r.mutation_id): r.outcome for r in live_results}

    family = doc.get("families", {}).get("placer-pcl-handlers", {})
    for surface in family.get("surfaces", []):
        sid = surface.get("id")
        for m in surface.get("mutations", []):
            mid = m.get("id")
            registered_outcome = m.get("outcome")
            key = (sid, mid)
            if key not in live:
                # A missing/unresolvable surface is already reported by the
                # anti-drift check in check_handler_surfaces; don't double-report.
                continue
            live_outcome = live[key]
            if live_outcome != registered_outcome:
                violations.append(
                    f"  {sid}:{mid}: register claims outcome={registered_outcome!r} but "
                    f"a live re-run of constraint_mutation_runner.py against the CURRENT "
                    f"encoder source classifies it {live_outcome!r} — the register is "
                    f"stale (re-run `python scripts/constraint_mutation_runner.py "
                    f"--write-register power_pcb_dataset/constraint_kill_sets.yaml "
                    f"--triage-from power_pcb_dataset/constraint_kill_sets.yaml` and "
                    f"review the diff before committing)"
                )
    return violations


def main() -> None:
    if not HANDLERS_DIR.exists():
        _die(EXIT_ERROR, f"handlers dir not found: {HANDLERS_DIR}")
    if not CONSTRAINT_MODEL.exists():
        _die(EXIT_ERROR, f"constraint_model.py not found: {CONSTRAINT_MODEL}")

    doc = load_register(REGISTER)

    handler_violations = check_handler_surfaces(doc)
    router_v6_violations = check_router_v6(doc)
    live_violations = check_live_kill_sets(doc)

    violations = handler_violations + router_v6_violations + live_violations
    if violations:
        header = (
            f"Constraint mutation gate FAILED: {len(violations)} violation(s) — "
            f"every encoding must carry a non-empty, triaged kill set, live-"
            f"verified against the current encoder source:"
        )
        _die(EXIT_MISSING, f"{header}\n" + "\n".join(violations))

    n_surfaces = len(discover_handler_surfaces())
    n_classes = len(discover_router_v6_classes())
    print(
        f"[MUTATION-GATE] OK: {n_surfaces} handler surface(s) with non-empty, "
        f"triaged kill sets, live-verified against current encoder source; "
        f"{n_classes} router-V6 class(es) registered"
    )


if __name__ == "__main__":
    main()
