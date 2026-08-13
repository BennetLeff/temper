#!/usr/bin/env python3
"""Declared <-> emitted layer gate: if the board declares a layer with a
power-plane role, something in the actual production pipeline must be
capable of pouring copper onto it.

Motivating defect (commit ``c4956df66`` and the same-day investigation
that followed it -- see this gate's ``docs/evidence/
2026-08-11-correspondence-gates.md`` for the live before/after run):
``c4956df66`` declared ``In1.Cu``/``In2.Cu`` as power-plane layers in
``pcb/temper.kicad_pcb``'s ``(layers ...)`` stack (role token ``power``,
not ``signal``). Both layers are empty on the real board -- zero copper
of any kind -- for two independent reasons, both still live on
``origin/main`` as of this gate's writing (confirmed by this gate's own
sub-checks, see the evidence doc):

  1. ``packages/temper-design-bundle/src/parse_engine.rs``'s
     ``raw_board_from_tree`` (the Rust parse engine's board-level
     ``"layers" => { ... }`` match arm) reads only the quoted NAME token
     at index 1 of each ``(N "LayerName" role ...)`` entry and never
     touches index 2 -- the arm's own comment says "index 2 is the layer
     type" immediately before discarding it. Nothing downstream of this
     parser can ever learn a layer was declared with a power-plane role,
     because that information never survives parsing.
  2. ``packages/temper-placer/src/temper_placer/router_v6/
     _zone_pour_stitch.py``'s ``_zone_layers_for_net`` -- the function
     ``_adapter_convert.route_pcb`` (the actual production routing entry
     point, via its call to ``_emit_zone_pours``) uses to decide which
     layer(s) a net's zone pour lands on -- returns only ``["F.Cu",
     "B.Cu"]`` or ``[]``. No return path in this function, or anywhere
     else reachable from ``route_pcb``, can ever produce ``"In1.Cu"`` or
     ``"In2.Cu"``. (``router_v6/power_plane.py`` DOES contain layer-aware
     pour geometry generation -- ``generate_ground_pour`` on ``In1.Cu``,
     ``generate_power_pours`` on ``In2.Cu`` -- but it is called only from
     ``_pipeline_verify.py``'s manufacturing-report path, purely to LOG a
     "Power planes: ..." summary line; that geometry is never merged into
     ``route_pcb``'s ``routed_pcb_content``. A code path that computes
     plane geometry nobody writes to the board is not an emitter for this
     gate's purposes -- see PROPERTY 2 below for why it is deliberately
     excluded from the checked "emitter" surface.)

Meanwhile ``scripts/route_board.py``'s ``_should_route()`` EXCLUDES
power/ground/HV nets from Stage 4 A* routing entirely, on the stated
assumption that they are "presumed zone-covered" -- so a net that never
gets a pour AND never gets point-to-point routing ends up with no copper
at all. Net ``gnd`` (86 pads, the board's largest) is the real-world
casualty. This gate does not re-derive that specific consequence (that is
``check_copper_net_consistency.py``'s and the routing pipeline's
territory); it exists one level up, at the declaration/capability level:
nothing before it checked that a declared plane layer even HAS an
emission path leading to it, regardless of which specific nets end up
using it.

Two independent properties, checked separately because they are
different failure shapes -- fixing one does not imply the other is
fixed (mirrors ``check_hv_netclass_coverage.py``'s two-property design):

PROPERTY 1 -- parser role-token fidelity
-------------------------------------------
Statically confirms that ``raw_board_from_tree``'s board-level
``"layers" => { ... }`` match arm in ``parse_engine.rs`` reads BOTH the
name (index 1) and the role/type token (index 2) of each layer-stack
entry, not just the name. This is a source-text check, not a build+run
check (this gate does not compile the Rust crate -- "fast and
deterministic... no solving" per this gate family's contract), scoped
precisely to ``raw_board_from_tree``'s own match arm (there are two OTHER
unrelated ``"layers" =>`` arms in this file, for pad and zone
``(layers F.Cu B.Mask ...)`` lists -- a flat list of layer names with no
per-entry role token at all, a different shape this property must not be
confused with). The scoping is done by locating the ``fn
raw_board_from_tree`` function boundary first, then searching for
``"layers" =>`` only within that function's body.

PROPERTY 2 -- zone-emitter layer coverage
--------------------------------------------
Every layer ``pcb/temper.kicad_pcb`` declares with role ``power`` in its
own ``(layers ...)`` block (parsed directly from the board file, never a
hardcoded layer-name constant) must be a layer name that
``_zone_layers_for_net`` in ``router_v6/_zone_pour_stitch.py`` can
actually return -- i.e. must appear as a string literal inside that
function's body. "Capable of pouring" is scoped deliberately to this one
function (and not, e.g., ``router_v6/power_plane.py``): it is the
function ``_adapter_convert.route_pcb`` -- the pipeline entry point that
actually produces ``routed_pcb_content``, the bytes that become the
board -- consults to decide zone layers. A layer name appearing anywhere
else in the codebase (a report-only geometry generator, a test fixture, a
docstring) is not evidence of a real emission path; only appearing inside
the function actually wired into ``route_pcb`` counts.

Fail-closed contract (this repo's gate-family convention): this gate
exits non-zero for every one of:
  - the board file is missing, unparsable, or has no non-empty
    ``(layers ...)`` block
  - ``parse_engine.rs`` is missing, or ``raw_board_from_tree`` cannot be
    located in it (the function was renamed/moved and this gate's static
    scoping broke)
  - ``_zone_pour_stitch.py`` is missing, or ``_zone_layers_for_net``
    cannot be located in it

Exit codes:
  0 - PASSED: the parser captures the role token, and every declared
      power-plane layer is reachable from the zone emitter
  3 - VIOLATION: the parser discards the role token, and/or at least one
      declared power-plane layer has no emitter path
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_layer_plane_emission_coverage.py
  uv run python scripts/check_layer_plane_emission_coverage.py \\
      --board PATH --parser-source PATH --emitter-source PATH
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_PARSER_SOURCE = REPO_ROOT / "packages" / "temper-design-bundle" / "src" / "parse_engine.rs"
DEFAULT_EMITTER_SOURCE = (
    REPO_ROOT
    / "packages"
    / "temper-placer"
    / "src"
    / "temper_placer"
    / "router_v6"
    / "_zone_pour_stitch.py"
)

PLANE_ROLE = "power"


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Board: declared plane layers
# ---------------------------------------------------------------------------

# `(0 "F.Cu" signal)` / `(1 "In1.Cu" power)` -- ordinal, quoted name,
# bare role token (optionally followed by a quoted user-facing name this
# gate doesn't need).
_LAYER_ENTRY_RE = re.compile(r'\(\s*\d+\s+"([^"]+)"\s+([A-Za-z]+)')


def load_declared_plane_layers(board_path: Path) -> list[str]:
    """Returns the sorted list of layer names declared with role
    ``PLANE_ROLE`` in ``board_path``'s own ``(layers ...)`` block.
    """
    if not board_path.is_file():
        raise GateError(f"board file not found: {board_path}")
    text = board_path.read_text(encoding="utf-8")

    marker = text.find("(layers")
    if marker == -1:
        raise GateError(f"{board_path} has no '(layers ...)' block")
    # Balance parens from the opening '(' of '(layers' to find the block end.
    start = marker
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise GateError(f"{board_path}'s '(layers ...)' block is not balanced")
    block = text[start:end]

    entries = _LAYER_ENTRY_RE.findall(block)
    if not entries:
        raise GateError(f"{board_path}'s '(layers ...)' block has no parsable layer entries")

    planes = sorted({name for name, role in entries if role == PLANE_ROLE})
    return planes


# ---------------------------------------------------------------------------
# Property 1: parser role-token fidelity
# ---------------------------------------------------------------------------


def _extract_function_body(source: str, fn_name: str, source_label: str) -> str:
    """Returns the full source text of the top-level ``fn <fn_name>``
    (from its own signature line to the next top-level ``fn ``/``pub fn
    ``/``pub(crate) fn `` declaration, or EOF). Raises GateError if the
    function cannot be located -- this gate must fail closed, not
    silently check nothing, if the source has moved out from under it.
    """
    pattern = re.compile(rf"^\s*(?:pub(?:\([^)]*\))?\s+)?fn\s+{re.escape(fn_name)}\b", re.MULTILINE)
    m = pattern.search(source)
    if not m:
        raise GateError(f"could not locate `fn {fn_name}` in {source_label}")
    start = m.start()
    next_fn = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?fn\s+\w+", re.MULTILINE)
    m2 = next_fn.search(source, m.end())
    end = m2.start() if m2 else len(source)
    return source[start:end]


def _extract_match_arm(body: str, arm_pattern: str, context_label: str) -> str:
    """Returns the brace-balanced body of the first ``"<arm_pattern>" =>
    { ... }`` match arm found in ``body``. Raises GateError if not found.
    """
    marker = re.search(rf'"{re.escape(arm_pattern)}"\s*=>\s*\{{', body)
    if marker is not None:
        brace_start = body.index("{", marker.start())
        depth = 0
        for i in range(brace_start, len(body)):
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
                if depth == 0:
                    return body[brace_start : i + 1]
    raise GateError(f'could not locate `"{arm_pattern}" => {{ ... }}` arm in {context_label}')


def check_parser_captures_layer_role(parser_source_path: Path) -> tuple[bool, str]:
    """Returns (captures_role, detail). ``captures_role`` is True iff
    ``raw_board_from_tree``'s board-level ``"layers" => { ... }`` match
    arm reads index 2 of each layer-stack entry (the role/type token),
    not only index 1 (the name).
    """
    if not parser_source_path.is_file():
        raise GateError(f"parser source not found: {parser_source_path}")
    source = parser_source_path.read_text(encoding="utf-8")

    fn_body = _extract_function_body(source, "raw_board_from_tree", str(parser_source_path))
    arm_body = _extract_match_arm(fn_body, "layers", f"{parser_source_path}::raw_board_from_tree")

    # The role token is index 2 of each `(N "Name" role)` sub-list --
    # accept any of the common ways Rust code would read a third list
    # element (`.get(2)`, `s[2]`, or destructuring `[_, name, role]`).
    captures_role = bool(
        re.search(r"\.get\(\s*2\s*\)", arm_body)
        or re.search(r"\[\s*2\s*\]", arm_body)
        or re.search(r"\[\s*_[,\s].*,\s*\w+\s*(?:,.*)?\]", arm_body)
    )
    if captures_role:
        return True, "raw_board_from_tree's 'layers' arm reads index 2 (the role token)"
    return (
        False,
        "raw_board_from_tree's 'layers' arm in "
        f"{parser_source_path} only reads index 1 (the name) -- the role/type "
        'token at index 2 of each `(N "Name" role)` entry is discarded, '
        "so nothing downstream of parsing can learn a layer's declared "
        "power-plane role",
    )


# ---------------------------------------------------------------------------
# Property 2: zone-emitter layer coverage
# ---------------------------------------------------------------------------

_LAYER_LITERAL_RE = re.compile(r'"([A-Za-z][A-Za-z0-9_]*\.Cu)"')


def _strip_docstring(body: str) -> str:
    """Blanks out the function's own docstring (if any) from ``body``.

    ``load_emittable_layers`` below treats any ``"X.Cu"`` string literal in
    the function body as evidence the function can *emit* layer ``X.Cu`` --
    a deliberate over-approximation of real control flow. A docstring is
    prose, not control flow: it can (and, 2026-08-11 commit ``259758f6a``,
    does) name a layer literal while explaining why a branch for it was
    *not* added ("NOT CHANGED 2026-08-11 ... an `\"In2.Cu\"` branch here
    ... was prototyped and reverted"). Left unstripped, that sentence reads
    as proof the function emits ``In2.Cu``, which is the opposite of what
    it says. Only the function's own leading docstring is stripped (not
    every string literal), so real emitted-layer literals like
    ``return ["F.Cu", "B.Cu"]`` are untouched.
    """
    import ast

    try:
        tree = ast.parse(body)
    except SyntaxError:
        return body
    if not tree.body or not isinstance(tree.body[0], ast.FunctionDef):
        return body
    fn_body = tree.body[0].body
    if not fn_body:
        return body
    first = fn_body[0]
    if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)):
        return body
    lines = body.splitlines(keepends=True)
    start_line, start_col = first.lineno - 1, first.col_offset
    end_line, end_col = first.end_lineno - 1, first.end_col_offset
    if start_line == end_line:
        line = lines[start_line]
        lines[start_line] = line[:start_col] + " " * (end_col - start_col) + line[end_col:]
    else:
        lines[start_line] = lines[start_line][:start_col]
        for i in range(start_line + 1, end_line):
            lines[i] = "\n" if lines[i].endswith("\n") else ""
        lines[end_line] = " " * end_col + lines[end_line][end_col:]
    return "".join(lines)


def load_emittable_layers(emitter_source_path: Path) -> set[str]:
    """Returns the set of ``*.Cu`` layer-name string literals appearing
    anywhere in ``_zone_layers_for_net``'s body -- the over-approximation
    of "every layer this function could possibly return for some net".
    The function's own docstring is excluded first (see
    ``_strip_docstring``): prose describing a layer literal is not the
    same claim as code that can return it.
    """
    if not emitter_source_path.is_file():
        raise GateError(f"emitter source not found: {emitter_source_path}")
    source = emitter_source_path.read_text(encoding="utf-8")

    m = re.search(r"^def _zone_layers_for_net\(", source, re.MULTILINE)
    if not m:
        raise GateError(f"could not locate `def _zone_layers_for_net` in {emitter_source_path}")
    next_def = re.search(r"^def \w+\(", source[m.end() :], re.MULTILINE)
    end = m.end() + next_def.start() if next_def else len(source)
    body = source[m.start() : end]
    body = _strip_docstring(body)

    return set(_LAYER_LITERAL_RE.findall(body))


def check_emitter_covers_declared_planes(
    declared_planes: list[str], emittable_layers: set[str]
) -> list[str]:
    """Returns the sorted list of declared plane layers absent from
    ``emittable_layers``."""
    return sorted(layer for layer in declared_planes if layer not in emittable_layers)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    declared_plane_layers: list[str] = field(default_factory=list)
    parser_captures_role: bool | None = None
    parser_detail: str = ""
    unemittable_planes: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(
    board_path: Path, parser_source_path: Path, emitter_source_path: Path
) -> tuple[str, Report]:
    report = Report()
    try:
        declared_planes = load_declared_plane_layers(board_path)
        parser_ok, parser_detail = check_parser_captures_layer_role(parser_source_path)
        emittable = load_emittable_layers(emitter_source_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    if not declared_planes:
        report.tool_errors.append(
            f"{board_path} declares zero layers with role {PLANE_ROLE!r} -- vacuous "
            "run, not a clean pass (this gate has nothing to check plane emission "
            "coverage for)"
        )
        return "tool_error", report

    report.declared_plane_layers = declared_planes
    report.parser_captures_role = parser_ok
    report.parser_detail = parser_detail
    report.unemittable_planes = check_emitter_covers_declared_planes(declared_planes, emittable)

    if not parser_ok or report.unemittable_planes:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "Declared <-> emitted layer gate -- "
        f"{len(report.declared_plane_layers)} declared power-plane layer(s): "
        f"{report.declared_plane_layers}"
    )

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")
        if state == "tool_error":
            print(
                "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
                "could not run a trustworthy check.",
                file=sys.stderr,
            )
            return

    print("\n=== PROPERTY 1: PARSER ROLE-TOKEN FIDELITY ===")
    status = "OK" if report.parser_captures_role else "VIOLATION"
    print(f"  {status} {report.parser_detail}")

    print(
        f"\n=== PROPERTY 2: PLANE LAYERS WITH NO EMITTER PATH: {len(report.unemittable_planes)} ==="
    )
    for layer in report.unemittable_planes:
        print(
            f"  VIOLATION layer {layer!r} is declared with role {PLANE_ROLE!r} in "
            "pcb/temper.kicad_pcb but does not appear anywhere in "
            "_zone_layers_for_net's body -- no code path reachable from "
            "route_pcb can ever pour copper on it"
        )

    if state == "clean":
        print("\nDeclared <-> emitted layer gate passed")
    elif state == "violation":
        print(
            f"\nFAILED -- parser role-token fidelity: {'OK' if report.parser_captures_role else 'VIOLATION'}, "
            f"{len(report.unemittable_planes)} plane layer(s) with no emitter path"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--parser-source", type=Path, default=DEFAULT_PARSER_SOURCE)
    parser.add_argument("--emitter-source", type=Path, default=DEFAULT_EMITTER_SOURCE)
    args = parser.parse_args()

    state, report = run(args.board, args.parser_source, args.emitter_source)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Declared <-> Emitted Layer Gate: {state}\n")
            f.write(
                f"- Declared power-plane layers: {report.declared_plane_layers}\n"
                f"- Parser captures role token: {report.parser_captures_role}\n"
                f"- Plane layers with no emitter path: {report.unemittable_planes}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
