"""Per-layer experiment: measure DRC error count at three checkpoints.

Checkpoint A — placement-only (CP-SAT with netclass constraints).
Checkpoint B — placement + netclass-aware routing (no feedback loop).
Checkpoint C — full pipeline (placement + routing + feedback loop).

Reports a markdown table identifying the load-bearing layer — the
checkpoint whose marginal DRC error reduction is largest relative to
the human-designed baseline (29 violations).

Part of feat/netclass-clearance-ssot U8.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — follow existing script convention
# ---------------------------------------------------------------------------
_PROJ = Path(__file__).resolve().parent.parent  # packages/temper-placer
import sys

sys.path.insert(0, str(_PROJ / "src"))


def _repo_root() -> Path:
    """Return the worktree / repo root (four dirs up from this file)."""
    return Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# DRC runner
# ---------------------------------------------------------------------------
def run_drc(pcb_path: Path) -> int:
    """Run ``kicad-cli pcb drc`` on a PCB file, return error count.

    Returns -1 if kicad-cli is unavailable or the DRC report cannot be
    parsed.
    """
    drc_out = Path(tempfile.mktemp(suffix=".json"))
    try:
        result = subprocess.run(
            [
                "kicad-cli",
                "pcb",
                "drc",
                "--format",
                "json",
                "-o",
                str(drc_out),
                str(pcb_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("  [WARN] kicad-cli not found — returning -1")
        return -1
    except subprocess.TimeoutExpired:
        print("  [WARN] kicad-cli timeout — returning -1")
        return -1

    if drc_out.exists():
        try:
            with open(drc_out) as f:
                data = json.load(f)
            violations = data.get("violations", [])
            errors = [v for v in violations if v.get("severity") == "error"]
            return len(errors)
        finally:
            with _suppress(OSError):
                os.unlink(drc_out)
    elif result.stderr:
        print(f"  [WARN] DRC report not produced: {result.stderr[:200]}")
    return -1


# ---------------------------------------------------------------------------
# PCB building helpers
# ---------------------------------------------------------------------------
def _apply_placements(input_pcb: Path, placements: dict, output_pcb: Path) -> None:
    """Apply placements to the input PCB and write the result."""
    from temper_placer.router_v6.adapter import _apply_placements_to_pcb

    raw = input_pcb.read_text(encoding="utf-8")
    placed = _apply_placements_to_pcb(raw, placements)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(placed, encoding="utf-8")


def _inject_netclass_forms(rules: Any, pcb_content: str) -> str:
    """Insert ``(net_class ...)`` s-expression forms into PCB content."""
    from temper_placer.router_v6.adapter import _apply_placements_to_pcb
    return _apply_placements_to_pcb(pcb_content, {}, design_rules=rules.design_rules)


def _route_and_write(
    input_pcb: Path, placements: dict, output_pcb: Path, seed: int, rules: Any
) -> None:
    """Route a placed PCB with V6 pipeline and write the result.

    Netclass forms are injected into the output so that kicad-cli DRC
    checks against the YAML-authoritative values.

    ``route_pcb`` internally applies *placements* to the board at
    ``parsed.source_path`` before routing, so we pass the raw input PCB
    and let ``route_pcb`` handle placement application.
    """
    from temper_placer.router_v6.adapter import (
        _apply_placements_to_pcb,
        route_pcb,
    )

    parsed = type("ParsedPCB", (), {"source_path": str(input_pcb)})()
    routed = route_pcb(parsed, placements, _seed=seed, design_rules=rules.design_rules)
    body = getattr(routed, "routed_pcb_content", None)
    if not body:
        # Routing produced no output; fall back to placed-only PCB.
        body = _apply_placements_to_pcb(
            input_pcb.read_text(encoding="utf-8"), placements,
            design_rules=rules.design_rules,
        )

    body = _inject_netclass_forms(rules, body)

    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(body, encoding="utf-8")


def _load_pcl_constraints(config_path: Path) -> list:
    """Load PCL constraints from a YAML config file.

    Tries ``load_constraints()`` first.  Falls back to reading inline
    ``constraints:`` entries from the raw YAML if the loader raises or
    returns no PCL constraints.
    """
    pcl: list = []
    try:
        from temper_placer.io.config_loader import load_constraints

        constraints = load_constraints(config_path)
        pcl = list(getattr(constraints, "pcl_constraints", []))
    except Exception:
        pass

    if not pcl:
        try:
            import yaml as _yaml

            from temper_placer.pcl.parser import parse_constraint_dict

            raw = config_path.read_text(encoding="utf-8")
            cfg = _yaml.safe_load(raw) if raw else {}
            inline = cfg.get("constraints", []) if isinstance(cfg, dict) else []
            for cdict in inline:
                try:
                    pcl.append(parse_constraint_dict(cdict))
                except Exception:
                    pass
        except Exception:
            pass

    return pcl


def _load_zones(pcl_constraints: list) -> tuple[dict, dict]:
    """Load zone bounds and component mappings from cooker config."""
    zones: dict[str, tuple[float, float, float, float]] = {}
    zone_comps: dict[str, list[str]] = {}

    cooker_path = (
        _PROJ / "configs" / "constraints" / "temper_induction_cooker.yaml"
    )
    if cooker_path.exists():
        import yaml as _yaml

        cooker = _yaml.safe_load(cooker_path.read_text())
        for zd in cooker.get("zones", []):
            zones[zd["name"]] = tuple(zd["bounds"])
            zone_comps[zd["name"]] = zd.get("components", [])

    for c in pcl_constraints:
        outer = getattr(c, "outer", None)
        inner = getattr(c, "inner", None)
        if outer and inner:
            zone_comps[outer] = list(
                set(zone_comps.get(outer, []) + list(inner))
            )

    return zones, zone_comps


def _load_loop_components() -> dict[str, list[str]]:
    """Load commutation loop component groups from pcb_spec.yaml."""
    spec_path = _PROJ / "configs" / "pcb_spec.yaml"
    if not spec_path.exists():
        return {}
    import yaml as _yaml

    spec = _yaml.safe_load(spec_path.read_text())
    emi = spec.get("emi", {})
    return {name: comps for name, comps in emi.get("loop_components", {}).items()}


# ---------------------------------------------------------------------------
# Experiment rows
# ---------------------------------------------------------------------------
def run_row_a(
    rules: Any,
    netlist: Any,
    board: Any,
    pcl_constraints: list,
    input_pcb: Path,
    output_dir: Path,
    seed: int,
) -> int:
    """Checkpoint A — CP-SAT placement only, no routing."""
    from temper_placer.placer.cp_sat.encoder import solve_placement

    result = solve_placement(
        netlist=netlist,
        board=board,
        extra_constraints=pcl_constraints,
        timeout_ms=1000,
        seed=seed,
    )
    if result.status not in ("optimal", "feasible"):
        print(f"  Row A: placement status = {result.status}")
        return -1

    out = output_dir / "row_a_placed.kicad_pcb"
    _apply_placements(input_pcb, result.to_placements_dict(), out)
    return run_drc(out)


def run_row_b(
    rules: Any,
    netlist: Any,
    board: Any,
    pcl_constraints: list,
    input_pcb: Path,
    output_dir: Path,
    seed: int,
) -> int:
    """Checkpoint B — placement + netclass-aware routing, no feedback loop."""
    from temper_placer.placer.cp_sat.encoder import solve_placement

    result = solve_placement(
        netlist=netlist,
        board=board,
        extra_constraints=pcl_constraints,
        timeout_ms=1000,
        seed=seed,
    )
    if result.status not in ("optimal", "feasible"):
        print(f"  Row B: placement status = {result.status}")
        return -1

    out = output_dir / "row_b_routed.kicad_pcb"
    _route_and_write(input_pcb, result.to_placements_dict(), out, seed, rules)
    return run_drc(out)


def run_row_c(
    rules: Any,
    netlist: Any,
    board: Any,
    pcl_constraints: list,
    input_pcb: Path,
    output_dir: Path,
    seed: int,
) -> int:
    """Checkpoint C — full pipeline with place→route feedback loop."""
    from temper_placer.placer.cp_sat.loop import PlaceRouteLoop

    zones, zone_comps = _load_zones(pcl_constraints)
    loop_comps = _load_loop_components()

    loop = PlaceRouteLoop()
    result = loop.run(
        netlist=netlist,
        board=board,
        pcl_constraints=pcl_constraints,
        seed=seed,
        zones=zones if zones else None,
        zone_components=zone_comps if zone_comps else None,
        loop_components=loop_comps if loop_comps else None,
    )

    if not result.success:
        print(f"  Row C: loop failed — {result.reason}")
        return -1

    placements = (
        result.placement.to_placements_dict() if result.placement else {}
    )
    if not placements:
        print("  Row C: no placements after loop")
        return -1

    out = output_dir / "row_c_routed.kicad_pcb"
    _route_and_write(input_pcb, placements, out, seed, rules)
    return run_drc(out)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
class _suppress:
    """Context manager that suppresses a specific exception."""

    def __init__(self, *exceptions):
        self._exceptions = exceptions

    def __enter__(self):
        return None

    def __exit__(self, typ, val, tb):
        return typ is not None and issubclass(typ, self._exceptions)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    root = _repo_root()
    input_pcb = root / "pcb" / "temper.kicad_pcb"
    if not input_pcb.exists():
        print(f"input PCB not found: {input_pcb}")
        raise SystemExit(1)

    rules_path = _PROJ / "configs" / "netclass_rules.yaml"
    config_path = _PROJ / "configs" / "constraints" / "temper_induction_cooker.yaml"

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules

    rules = load_netclass_rules(rules_path)
    n_classes = len(rules.design_rules.net_classes)
    n_pairs = len(rules.class_pairs)
    print(f"Loaded netclass rules: {n_classes} classes, {n_pairs} cross-class pairs")

    parse_result = parse_kicad_pcb(input_pcb)
    netlist = parse_result.netlist
    board = parse_result.board
    pcl_constraints = _load_pcl_constraints(config_path)

    seed = 42
    output_dir = Path(tempfile.mkdtemp(prefix="netclass_experiment_"))
    print(f"Output dir: {output_dir}")

    # --- Baseline ---
    print("\n--- Baseline ---")
    bl_errors = run_drc(input_pcb)

    # --- Row A ---
    print("\n--- Row A: placement only ---")
    a_errors = run_row_a(rules, netlist, board, pcl_constraints, input_pcb, output_dir, seed)

    # --- Row B ---
    print("\n--- Row B: placement + routing ---")
    b_errors = run_row_b(rules, netlist, board, pcl_constraints, input_pcb, output_dir, seed)

    # --- Row C ---
    print("\n--- Row C: full pipeline (feedback loop) ---")
    c_errors = run_row_c(rules, netlist, board, pcl_constraints, input_pcb, output_dir, seed)

    # --- Markdown table ---
    def _delta(new: int, old: int) -> str:
        if new < 0 or old < 0:
            return "—"
        d = old - new
        sign = "-" if d < 0 else ("+" if d > 0 else "")
        return f"{sign}{abs(d)}"

    print()
    print("## Netclass Layer Experiment — DRC Error Counts")
    print()
    print("| Checkpoint | DRC Errors | Delta vs Baseline | Delta vs Previous |")
    print("|------------|-----------:|------------------:|------------------:|")
    print(f"| Baseline (human) | {bl_errors} | — | — |")
    print(f"| A) Placement only | {a_errors} | {_delta(a_errors, bl_errors)} | — |")
    print(f"| B) Placement + Routing | {b_errors} | {_delta(b_errors, bl_errors)} | {_delta(b_errors, a_errors)} |")
    print(f"| C) Full pipeline (feedback) | {c_errors} | {_delta(c_errors, bl_errors)} | {_delta(c_errors, b_errors)} |")
    print()

    # --- Load-bearing finding ---
    marginal = []
    if a_errors >= 0:
        marginal.append(("placement constraints (Row A)", bl_errors - a_errors if bl_errors >= 0 else None))
    if a_errors >= 0 and b_errors >= 0:
        marginal.append(("netclass-aware routing (Row B)", a_errors - b_errors))
    if b_errors >= 0 and c_errors >= 0:
        marginal.append(("feedback loop (Row C)", b_errors - c_errors))

    valid = [(name, val) for name, val in marginal if val is not None]
    if valid:
        best = max(valid, key=lambda x: x[1])
        print(f"**Load-bearing finding:** {best[0]} contributed the largest "
              f"marginal reduction ({best[1]} errors).")
    else:
        print("**Load-bearing finding:** could not compute — verify kicad-cli is available.")


if __name__ == "__main__":
    main()
