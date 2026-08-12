#!/usr/bin/env python3
"""PCL config <-> board correspondence gate: every component reference in a
placement-constraint config resolves to a real board component, and every
declared zone lies within the board's physical outline.

Motivating defect (PR #1026 and its triage table; confirmed still present
on ``origin/main`` at the time this gate was written -- see this gate's
own ``docs/evidence/2026-08-11-correspondence-gates.md`` write-up for the
live before/after run): ``packages/temper-placer/configs/constraints/
temper_induction_cooker.yaml`` holds 21 placement constraints against
``pcb/temper.kicad_pcb`` (169 components, 152x234mm). Not one has a safe
mechanical fix:

  - ``J_AC_IN``, ``J_COIL``, ``J_DEBUG`` name components that do not exist
    anywhere on the board -- no footprint on the board carries that
    Reference designator, and ``temper_constraints.references.yaml``
    (the hand-reconciled alias manifest between this legacy config's
    names and the live board) explicitly lists all three under
    ``unresolved_components`` as having "no source-backed connector
    instance".
  - ``adj_Q1_Q2`` (the ``adjacent: {a: Q1, b: Q2}`` constraint) resolves
    to unrelated small transistors -- ``Q1``/``Q2`` ARE real board
    Reference designators (confirmed: ``pcb/temper.kicad_pcb`` has
    footprints literally named ``Q1``/``Q2``), so a naive
    does-this-name-exist-on-the-board check would pass this constraint.
    But ``temper_constraints.references.yaml`` explicitly documents that
    the config's *intent* was the IGBTs (board refs ``U5``/``U6``, ~91.5mm
    apart -- nowhere near the constraint's <=10mm requirement), not the
    unrelated parts that happen to share the ``Q1``/``Q2`` designators.
    This is exactly why ``unresolved_components`` entries are checked
    BEFORE a direct board-reference match below: a name can be
    "resolvable" in the weak sense (it happens to name a real component)
    while still being the wrong component entirely, and the alias
    manifest is this repo's authoritative record of which legacy names
    are known to be mis-resolved this way.
  - The zone geometry (``MCU_ZONE``/``ISOLATION_BARRIER``/``HV_ZONE``,
    origin (0,0) sized for a 100x150mm board) does not lie within the
    real board's Edge.Cuts outline at all: the real board outline is the
    rectangle (20,20)-(172,254) (152x234mm, confirmed by parsing the
    board's own ``gr_poly`` Edge.Cuts geometry), so a zone whose bounds
    start at (0,0) is entirely off the physical board -- not merely
    undersized relative to it.

Nothing before this gate checked that the config's component references
resolve, or that its zones fit the board -- the config could name
components that were deleted, renamed, or never existed, and the only
symptom would be a downstream placement/DRC failure with no signal
pointing back at "the config itself is unsatisfiable, not merely
unsatisfied".

Distinguishing "unsatisfiable" from "unsatisfied" (the scope boundary
this gate exists to hold) -- deliberately, by design:
  - A constraint naming a nonexistent part, or a zone outside the board
    outline, is a BROKEN CONFIG: no placement of real components could
    ever satisfy it, because the referent doesn't physically exist where
    the config thinks it does. This is what this gate checks.
  - A constraint the board's *actual placement* merely VIOLATES (e.g. two
    real, correctly-referenced components that are farther apart than a
    max-distance constraint allows) is a placement-quality problem, is
    NOT checked here, and never will be -- this gate parses zero
    component coordinates from the board (other than the four corners of
    the Edge.Cuts outline, for containment) and computes zero distances
    between placed components. Whether the board's current placement
    satisfies ``temper_induction_cooker.yaml``'s constraints is entirely
    a different question, answered by the CP-SAT placer / DRC, not by
    this gate.

Two independent properties are checked, for the same reason
``check_hv_netclass_coverage.py`` keeps its two properties separate:
fixing one does not imply the other is fixed.

PROPERTY 1 -- component reference resolution
----------------------------------------------
Every component-context name in the config (``adjacent.a``/``.b``,
``separated.a``/``.b``, ``on_side.components``, ``aligned.components``,
``enclosing.inner``) must resolve to a real board Reference designator.
A name that matches a declared zone (from the config's own ``zones:``
list) is a zone reference, not a component reference, and is skipped
here (checked instead by Property 2's containment, and by
``enclosing.outer``, which is REQUIRED to be a zone name, not a
component). Resolution order, deliberately fail-closed and manifest-
first (see the ``adj_Q1_Q2`` case above for why manifest-first matters):

  1. Name is a declared zone -> not a component reference, skip.
  2. Name is a key in ``temper_constraints.references.yaml``'s
     ``unresolved_components`` -> BROKEN. The manifest itself documents
     why (wrong component, ambiguous candidate, or no source-backed
     part at all) -- surfaced verbatim in the violation message.
  3. Name is a key in ``component_aliases`` -> resolves to the aliased
     board reference; BROKEN only if that reference is somehow itself
     absent from the board (a manifest gone stale against the board it
     claims to describe -- fail closed rather than trust a dangling
     alias).
  4. Name literally matches a board Reference designator -> OK.
  5. None of the above -> BROKEN (a name the manifest has never even
     seen, and that doesn't exist on the board either -- the
     lowest-confidence, most obviously broken case).

Constraint types not in the known field-extraction table make the gate
fail closed as a tool error rather than silently skip the constraint --
an unrecognized constraint type is a gate blind spot, not a clean pass.

PROPERTY 2 -- zone containment
--------------------------------
Every zone in the config's ``zones:`` list must have its declared
rectangular bounds ``[x_min, y_min, x_max, y_max]`` fully contained
within the board's Edge.Cuts outline bounding box, computed directly
from ``pcb/temper.kicad_pcb``'s own graphic geometry (``gr_poly``,
``gr_rect``, ``gr_line``, ``gr_arc``, ``gr_circle`` on the ``Edge.Cuts``
layer) -- never a hardcoded board-size constant, so this property tracks
the real board's outline through any future resize. Malformed bounds
(wrong arity, non-numeric, ``x_min >= x_max`` or ``y_min >= y_max``) are
also BROKEN: a zone that cannot even describe a valid rectangle is
exactly as unsatisfiable as one placed off the board.

Fail-closed contract (this repo's gate-family convention -- see
``check_hv_netclass_coverage.py``, ``check_domain_partition.py``): this
gate never exits 0 unless it positively confirms it ran a real check on
real, fresh data. It exits non-zero for every one of:
  - the PCL config is missing, empty, not YAML, or has no non-empty
    ``constraints`` list. ``zones`` is OPTIONAL -- a component-only PCL
    file (e.g. ``thermal_management.yaml``, which declares no zones at
    all) is a legitimate config, not a vacuous one: Property 1 (reference
    resolution) still has real content to check even with zero zones.
    A config with neither a non-empty ``constraints`` list nor any zones
    has nothing for either property to check and is still rejected via
    the ``constraints`` requirement above.
  - the board file is missing, has zero parsed component references, or
    has no Edge.Cuts geometry (an empty outline bbox)
  - the reference alias manifest path is given (or the default exists)
    but is malformed YAML, or is missing top-level ``component_aliases``/
    ``unresolved_components`` keys entirely
  - a constraint has a type this gate does not know how to extract
    component references from

Exit codes:
  0 - PASSED: every component reference resolves, every zone is
      contained in the board outline
  3 - VIOLATION: at least one broken reference or zone
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_pcl_config_board_correspondence.py
  uv run python scripts/check_pcl_config_board_correspondence.py \\
      --config PATH --board PATH --references PATH
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_CONFIG = (
    REPO_ROOT
    / "packages"
    / "temper-placer"
    / "configs"
    / "constraints"
    / "temper_induction_cooker.yaml"
)
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_REFERENCES = (
    REPO_ROOT / "packages" / "temper-placer" / "configs" / "temper_constraints.references.yaml"
)

EDGE_CUTS_LAYER = "Edge.Cuts"
# Sub-forms carrying a coordinate pair, keyed by the tag that precedes
# the (x y) pair. `xy` covers `(pts (xy x y) (xy x y) ...)` polygons.
_COORD_TAGS = frozenset({"start", "end", "center", "mid", "xy"})


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Minimal, dependency-free KiCad s-expression reader.
#
# Deliberately not the Rust parse engine (temper_design_bundle_python):
# this gate must run with zero compiled-extension dependency and zero
# solving, and only needs two facts out of the board file -- footprint
# Reference designators, and Edge.Cuts outline geometry -- so a small,
# self-contained tokenizer/parser is faster to trust here than depending
# on a much larger parser (which, per the sibling "declared/emitted
# layers" gate, has its own live, unrelated bug -- reason enough not to
# lean on it for a gate that doesn't need it).
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "(" or c == ")":
            tokens.append(c)
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = ['"']
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j])
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            buf.append('"')
            tokens.append("".join(buf))
            i = j + 1
            continue
        j = i
        while j < n and text[j] not in " \t\r\n()":
            j += 1
        tokens.append(text[i:j])
        i = j
    return tokens


def _parse_tokens(tokens: list[str]) -> Any:
    """Parses a single top-level form; returns (node, next_index)."""
    pos = 0

    def parse_form(p: int) -> tuple[Any, int]:
        if tokens[p] != "(":
            return tokens[p], p + 1
        p += 1
        items: list[Any] = []
        while tokens[p] != ")":
            node, p = parse_form(p)
            items.append(node)
        return items, p + 1

    node, pos = parse_form(pos)
    return node


def _strip_quotes(atom: str) -> str:
    if len(atom) >= 2 and atom[0] == '"' and atom[-1] == '"':
        return atom[1:-1]
    return atom


def _walk(node: Any):
    """Yields every list-node in the tree (depth-first, includes root)."""
    if isinstance(node, list):
        yield node
        for child in node:
            yield from _walk(child)


def parse_board(board_path: Path) -> tuple[set[str], tuple[float, float, float, float] | None]:
    """Returns (board_reference_designators, edge_cuts_bbox).

    ``edge_cuts_bbox`` is ``None`` when no Edge.Cuts geometry was found
    (a fail-closed condition the caller must reject).
    """
    if not board_path.is_file():
        raise GateError(f"board file not found: {board_path}")
    text = board_path.read_text(encoding="utf-8")
    try:
        tokens = _tokenize(text)
        tree = _parse_tokens(tokens)
    except (IndexError, ValueError) as e:
        raise GateError(
            f"{board_path} could not be parsed as a KiCad s-expression file: {e}"
        ) from e

    refs: set[str] = set()
    xs: list[float] = []
    ys: list[float] = []

    for node in _walk(tree):
        if not node or not isinstance(node[0], str):
            continue
        head = node[0]
        if head == "property" and len(node) >= 3:
            key = _strip_quotes(node[1]) if isinstance(node[1], str) else None
            if key == "Reference" and isinstance(node[2], str):
                refs.add(_strip_quotes(node[2]))
            continue
        if head.startswith("gr_"):
            layer_ok = False
            for sub in node[1:]:
                if isinstance(sub, list) and sub and sub[0] == "layer" and len(sub) >= 2:
                    if isinstance(sub[1], str) and _strip_quotes(sub[1]) == EDGE_CUTS_LAYER:
                        layer_ok = True
            if not layer_ok:
                continue
            for sub in _walk(node):
                if not sub or not isinstance(sub[0], str):
                    continue
                if sub[0] in _COORD_TAGS and len(sub) >= 3:
                    try:
                        x = float(sub[1])
                        y = float(sub[2])
                    except (TypeError, ValueError):
                        continue
                    xs.append(x)
                    ys.append(y)

    bbox = None
    if xs and ys:
        bbox = (min(xs), min(ys), max(xs), max(ys))
    return refs, bbox


# ---------------------------------------------------------------------------
# Config / reference-manifest loading
# ---------------------------------------------------------------------------


def load_pcl_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise GateError(f"PCL config not found: {config_path}")
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise GateError(f"{config_path} is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise GateError(f"{config_path} did not parse to a mapping")
    constraints = data.get("constraints")
    zones = data.get("zones")
    if not isinstance(constraints, list) or not constraints:
        raise GateError(f"{config_path} has no non-empty 'constraints' list")
    # zones is optional: a component-only PCL file (thermal_management.yaml,
    # half_bridge_base.yaml) legitimately declares none. A present-but-wrong-
    # typed zones key is still a tool error (malformed input), but missing/
    # empty is normalized to an empty list -- Property 2 then trivially
    # checks zero zones instead of the run erroring out before Property 1
    # (component reference resolution) ever gets to run at all.
    if zones is None:
        data["zones"] = []
    elif not isinstance(zones, list):
        raise GateError(f"{config_path}'s 'zones' key is present but not a list")
    return data


def load_reference_manifest(references_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Returns (component_aliases, unresolved_components). Fails closed if
    the file exists but is malformed or missing the keys this gate
    depends on -- a manifest that cannot be trusted must not be silently
    treated as empty (that would demote every alias to "unknown
    reference", masking real resolutions as violations).
    """
    if not references_path.is_file():
        raise GateError(f"reference alias manifest not found: {references_path}")
    try:
        data = yaml.safe_load(references_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise GateError(f"{references_path} is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise GateError(f"{references_path} did not parse to a mapping")
    if "component_aliases" not in data or "unresolved_components" not in data:
        raise GateError(
            f"{references_path} is missing 'component_aliases' and/or "
            "'unresolved_components' -- cannot distinguish a resolvable "
            "alias from a known-broken reference without both"
        )
    aliases = data.get("component_aliases") or {}
    unresolved = data.get("unresolved_components") or {}
    if not isinstance(aliases, dict) or not isinstance(unresolved, dict):
        raise GateError(
            f"{references_path}'s 'component_aliases'/'unresolved_components' must both be mappings"
        )
    return {str(k): str(v) for k, v in aliases.items()}, {
        str(k): str(v) for k, v in unresolved.items()
    }


# ---------------------------------------------------------------------------
# Property 1: component reference resolution
# ---------------------------------------------------------------------------

# Constraint type -> function extracting the raw (possibly zone-or-
# component) name strings it references. Any constraint type absent from
# this table makes the gate fail closed (see module docstring).
_FIELD_EXTRACTORS: dict[str, Any] = {
    "adjacent": lambda c: [c[k] for k in ("a", "b") if c.get(k)],
    "separated": lambda c: [c[k] for k in ("a", "b") if c.get(k)],
    "on_side": lambda c: list(c.get("components") or []),
    "aligned": lambda c: list(c.get("components") or []),
    "enclosing": lambda c: list(c.get("inner") or []),
    "loop_area": lambda c: [],  # loop_name is not a component reference
}
# enclosing.outer is required to be a zone name -- validated separately,
# not folded into the generic name-resolution loop (a component-context
# name there would be a schema error of its own, out of this gate's two
# properties, so it is neither checked nor silently accepted).


@dataclass
class BrokenReference:
    constraint_index: int
    constraint_type: str
    field: str
    name: str
    reason: str


def resolve_component_references(
    config: dict[str, Any],
    board_refs: set[str],
    component_aliases: dict[str, str],
    unresolved_components: dict[str, str],
) -> tuple[list[BrokenReference], list[str]]:
    """Returns (broken_references, unknown_constraint_types).

    ``unknown_constraint_types`` is returned rather than raised so the
    caller can fold it into the fail-closed tool-error path with the
    other GateError conditions, while still letting a single call site
    own the decision.
    """
    zone_names = {z.get("name") for z in config.get("zones", []) if isinstance(z, dict)}
    broken: list[BrokenReference] = []
    unknown_types: list[str] = []

    for idx, c in enumerate(config.get("constraints", [])):
        if not isinstance(c, dict):
            continue
        ctype = c.get("type")
        extractor = _FIELD_EXTRACTORS.get(ctype)
        if extractor is None:
            unknown_types.append(f"constraint[{idx}] has unrecognized type {ctype!r}")
            continue
        for name in extractor(c):
            if not isinstance(name, str) or not name:
                continue
            if name in zone_names:
                continue
            if name in unresolved_components:
                broken.append(
                    BrokenReference(idx, str(ctype), "?", name, unresolved_components[name])
                )
                continue
            if name in component_aliases:
                target = component_aliases[name]
                if target not in board_refs:
                    broken.append(
                        BrokenReference(
                            idx,
                            str(ctype),
                            "?",
                            name,
                            f"aliases to {target!r}, which is not a board reference "
                            "(reference alias manifest is stale)",
                        )
                    )
                continue
            if name in board_refs:
                continue
            broken.append(
                BrokenReference(
                    idx,
                    str(ctype),
                    "?",
                    name,
                    "not a board reference, not a known alias, and not listed as "
                    "unresolved -- unrecognized component reference",
                )
            )

    return broken, unknown_types


# ---------------------------------------------------------------------------
# Property 2: zone containment
# ---------------------------------------------------------------------------


@dataclass
class BrokenZone:
    name: str
    reason: str


def check_zone_containment(
    config: dict[str, Any], board_bbox: tuple[float, float, float, float]
) -> list[BrokenZone]:
    bx_min, by_min, bx_max, by_max = board_bbox
    broken: list[BrokenZone] = []
    for z in config.get("zones", []):
        if not isinstance(z, dict):
            continue
        name = str(z.get("name", "<unnamed>"))
        bounds = z.get("bounds")
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            broken.append(
                BrokenZone(name, f"bounds {bounds!r} is not a 4-element [x_min,y_min,x_max,y_max]")
            )
            continue
        try:
            x_min, y_min, x_max, y_max = (float(v) for v in bounds)
        except (TypeError, ValueError):
            broken.append(BrokenZone(name, f"bounds {bounds!r} contains non-numeric values"))
            continue
        if x_min >= x_max or y_min >= y_max:
            broken.append(
                BrokenZone(name, f"bounds {bounds!r} is not a valid rectangle (min >= max)")
            )
            continue
        if x_min < bx_min or y_min < by_min or x_max > bx_max or y_max > by_max:
            broken.append(
                BrokenZone(
                    name,
                    f"bounds [{x_min}, {y_min}, {x_max}, {y_max}] is not contained in the "
                    f"board outline [{bx_min}, {by_min}, {bx_max}, {by_max}] (from "
                    "pcb/temper.kicad_pcb's own Edge.Cuts geometry)",
                )
            )
    return broken


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    constraints_checked: int = 0
    zones_checked: int = 0
    broken_references: list[BrokenReference] = field(default_factory=list)
    broken_zones: list[BrokenZone] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(
    config_path: Path,
    board_path: Path,
    references_path: Path,
) -> tuple[str, Report]:
    report = Report()
    try:
        config = load_pcl_config(config_path)
        board_refs, board_bbox = parse_board(board_path)
        component_aliases, unresolved_components = load_reference_manifest(references_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    if not board_refs:
        report.tool_errors.append(
            f"{board_path} parsed with zero footprint Reference designators -- "
            "vacuous run, not a clean pass"
        )
        return "tool_error", report
    if board_bbox is None:
        report.tool_errors.append(
            f"{board_path} has no Edge.Cuts geometry -- cannot check zone containment"
        )
        return "tool_error", report

    report.constraints_checked = len(config.get("constraints", []))
    report.zones_checked = len(config.get("zones", []))

    broken_refs, unknown_types = resolve_component_references(
        config, board_refs, component_aliases, unresolved_components
    )
    if unknown_types:
        report.tool_errors.extend(unknown_types)
        return "tool_error", report

    report.broken_references = broken_refs
    report.broken_zones = check_zone_containment(config, board_bbox)

    if report.broken_references or report.broken_zones:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "PCL config <-> board correspondence gate -- "
        f"{report.constraints_checked} constraint(s) and {report.zones_checked} "
        "zone(s) checked"
    )

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")

    print(f"\n=== PROPERTY 1: BROKEN COMPONENT REFERENCES: {len(report.broken_references)} ===")
    for b in report.broken_references:
        print(
            f"  VIOLATION constraint[{b.constraint_index}] (type={b.constraint_type!r}) "
            f"references {b.name!r}: {b.reason}"
        )

    print(f"\n=== PROPERTY 2: ZONES OUTSIDE BOARD OUTLINE: {len(report.broken_zones)} ===")
    for z in report.broken_zones:
        print(f"  VIOLATION zone {z.name!r}: {z.reason}")

    if state == "clean":
        print("\nPCL config <-> board correspondence gate passed")
    elif state == "violation":
        print(
            f"\nFAILED -- {len(report.broken_references)} broken reference(s), "
            f"{len(report.broken_zones)} zone(s) outside the board outline"
        )
    else:
        print(
            "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    args = parser.parse_args()

    state, report = run(args.config, args.board, args.references)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### PCL Config <-> Board Correspondence Gate: {state}\n")
            f.write(
                f"- Constraints checked: {report.constraints_checked}\n"
                f"- Zones checked: {report.zones_checked}\n"
                f"- Broken references: {len(report.broken_references)}\n"
                f"- Zones outside board outline: {len(report.broken_zones)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )
            if report.broken_references:
                f.write("\nBroken references:\n")
                for b in report.broken_references:
                    f.write(
                        f"- constraint[{b.constraint_index}] ({b.constraint_type}) `{b.name}`: {b.reason}\n"
                    )
            if report.broken_zones:
                f.write("\nZones outside board outline:\n")
                for z in report.broken_zones:
                    f.write(f"- `{z.name}`: {z.reason}\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
