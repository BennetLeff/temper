#!/usr/bin/env python3
"""2026-08-11 Pumpkin real-budget spike: HPWL + feasibility at TRUE real-board
scale (169 components / 110 nets, ``pcb/temper.kicad_pcb``) -- NOT the stale
33-component ``power_pcb_dataset`` fixture the existing harness's own
``build_full_board_corpus()`` loads (see the companion .md doc Sec 5 for why
that distinction matters: three prior CP-SAT spikes called that fixture "the
real golden board").

Read-only against ``pcb/temper.kicad_pcb`` (never writes it) and against
``configs/constraints/temper_induction_cooker.yaml`` (a schema-stripped COPY
is used -- see ``_stripped_pcl_config()`` below -- because ``load_constraints()``
currently rejects the committed file's own top-level keys; see the .md doc
Sec 4.0). Reuses the existing harness's courtyard/PlacementModel/CorpusModel
machinery and the existing ``PumpkinEngine``'s wire format + the standalone
Rust binary (extended with ``hpwl_nets`` support in this same branch,
``docs/evidence/2026-08-07-pumpkin-engine/src/main.rs``).

Does NOT modify any file under
``packages/temper-placer/src/temper_placer/placer/cp_sat/**``. The OR-Tools
HPWL objective is added via a runtime monkeypatch of
``CpSatModel.apply_objective`` (same technique as the existing harness's own
``_forced_worker_count``), not a source edit.

Usage:
    (cd docs/evidence/2026-08-07-pumpkin-engine && cargo build --release)
    uv run --no-sync python docs/evidence/scripts/2026-08-11-pumpkin-hpwl-realboard-run.py

Writes ``docs/evidence/2026-08-11-pumpkin-hpwl-realboard-summary.json``.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACER_ROOT = REPO_ROOT / "packages" / "temper-placer"
HARNESS_PATH = Path(__file__).resolve().parent / "2026-08-07-cpsat-equivalence-harness.py"
PUMPKIN_BIN = REPO_ROOT / "target-shared" / "release" / "pumpkin_engine"
REAL_BOARD_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"
OUT_PATH = Path(__file__).resolve().parent / "2026-08-11-pumpkin-hpwl-realboard-summary.json"

sys.path.insert(0, str(PLACER_ROOT / "src"))
sys.path.insert(0, str(HARNESS_PATH.parent))

spec = importlib.util.spec_from_file_location("cpsat_equivalence_harness", HARNESS_PATH)
assert spec is not None and spec.loader is not None
harness = importlib.util.module_from_spec(spec)
sys.modules["cpsat_equivalence_harness"] = harness
spec.loader.exec_module(harness)

from temper_placer.placer.cp_sat import _encoder_core  # noqa: E402
from temper_placer.placer.cp_sat.model import CpSatModel  # noqa: E402
from temper_placer.router_v6._net_policy import _should_route  # noqa: E402
from temper_placer.io.config_loader import load_constraints  # noqa: E402
from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402
from temper_placer.placer.cp_sat._encoder_solve import _POLARIZED_REFS  # noqa: E402

build_courtyard_constraints = harness.build_courtyard_constraints
default_clearance_mm = harness.default_clearance_mm
courtyard_clearance_mm = harness.courtyard_clearance_mm
PlacementModel = harness.PlacementModel
CorpusModel = harness.CorpusModel
IndependentVerifier = harness.IndependentVerifier
_forced_worker_count = harness._forced_worker_count


def _stripped_pcl_config() -> Path:
    """``load_constraints()`` (temper-design-bundle's Rust config_loader.rs
    ``reject_unknown_raw_keys`` guard) currently raises on the committed
    ``temper_induction_cooker.yaml`` because its own top-level keys
    (``version``/``metadata``/``netclasses``) are not in the guard's
    allowlist -- a live bug, independent of this spike (see the .md doc
    Sec 4.0). Builds a read-only temp copy with just those 3 keys removed,
    never touching the committed file."""
    import yaml

    src = PLACER_ROOT / "configs" / "constraints" / "temper_induction_cooker.yaml"
    data = yaml.safe_load(src.read_text())
    for key in ("version", "metadata", "netclasses"):
        data.pop(key, None)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="temper_induction_cooker_stripped_", delete=False
    )
    yaml.safe_dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


def build_real_board_corpus() -> "CorpusModel":
    """Same mechanism as the existing harness's own
    ``build_full_board_corpus()``, pointed at ``pcb/temper.kicad_pcb`` (169
    components) instead of the stale
    ``power_pcb_dataset/corpus/temper/temper.kicad_pcb`` fixture (33
    components, last touched 2026-07-08)."""
    parse_result = parse_kicad_pcb(REAL_BOARD_PATH)
    netlist = parse_result.netlist
    board = parse_result.board
    assert board is not None and netlist.components, "real board parse failed"

    pcl_config = _stripped_pcl_config()
    loaded = load_constraints(pcl_config)
    extra_constraints = list(getattr(loaded, "pcl_constraints", []))
    zones = {z.name: z.bounds for z in getattr(loaded, "zones", [])}

    _encoder_core._UNRESOLVED_REF_POLICY = "warn"  # same downgrade the harness/tests apply

    refs_sizes = {c.ref: (float(c.bounds[0]), float(c.bounds[1])) for c in netlist.components}
    zone_dict = {name: tuple(bounds) for name, bounds in zones.items()}
    zone_components: dict[str, list[str]] = {}
    for z in board.zones:
        zone_components.setdefault(z.name, list(z.components))

    tau = courtyard_clearance_mm(default_clearance_mm())
    full_constraints = build_courtyard_constraints(list(refs_sizes), extra_constraints, tau)
    vmodel = PlacementModel(
        board_w_mm=float(board.width), board_h_mm=float(board.height), sizes_mm=refs_sizes,
        constraints=full_constraints, zones=zone_dict, zone_components=zone_components,
        loop_components={},
    )
    return CorpusModel(
        name="real-board-169", netlist=netlist, board=board, extra_constraints=extra_constraints,
        zones=zones, zone_components={}, loop_components={}, minimize_displacement_to=None,
        verification_model=vmodel,
    )


def build_hpwl_nets(netlist) -> dict[str, list[str]]:
    """Router-eligible nets (``_should_route``, the same predicate router_v6
    uses to decide A*-vs-zone-pour) with >=2 distinct member component refs.
    Matches the wirelength plan's R3 filter (power/ground zone-poured nets
    excluded)."""
    comp_refs = {c.ref for c in netlist.components}
    nets: dict[str, list[str]] = {}
    for net in netlist.nets:
        if not _should_route(net.name):
            continue
        members = sorted({ref for ref, _pin in net.pins if ref in comp_refs})
        if len(members) >= 2:
            nets[net.name] = members
    return nets


def serialize_model(vm, seed: int, timeout_ms: int, hpwl_nets: dict | None) -> dict:
    components = {
        ref: {"w0_mm": w0, "h0_mm": h0, "rotatable": ref not in _POLARIZED_REFS}
        for ref, (w0, h0) in vm.sizes_mm.items()
    }
    constraints = [c.to_dict() for c in vm.constraints]
    payload = {
        "board_w_mm": vm.board_w_mm, "board_h_mm": vm.board_h_mm, "edge_margin_mm": vm.edge_margin_mm,
        "components": components, "zones": {name: list(bounds) for name, bounds in vm.zones.items()},
        "zone_components": vm.zone_components, "loop_components": vm.loop_components,
        "constraints": constraints, "minimize_displacement_to": None, "seed": seed, "timeout_ms": timeout_ms,
    }
    if hpwl_nets:
        payload["hpwl_nets"] = hpwl_nets
    return payload


def run_pumpkin(vm, hpwl_nets, seed, timeout_ms, safety_margin_s: float = 20.0) -> dict:
    payload = serialize_model(vm, seed, timeout_ms, hpwl_nets)
    t0 = time.monotonic()
    proc = subprocess.run(
        [str(PUMPKIN_BIN)], input=json.dumps(payload), capture_output=True, text=True,
        timeout=(timeout_ms / 1000.0) + safety_margin_s,
    )
    elapsed = (time.monotonic() - t0) * 1000.0
    if proc.returncode != 0:
        return {"status": "error", "solve_time_ms": elapsed, "stderr": proc.stderr[-2000:]}
    out = json.loads(proc.stdout)
    out["solve_time_ms"] = elapsed
    return out


def hpwl_objective_patch(hpwl_nets: dict[str, list[str]]):
    """Context manager: monkeypatches ``CpSatModel.apply_objective`` to add
    HPWL span terms (``AddMaxEquality``/``AddMinEquality`` over component
    centers, summed and ``Minimize()``'d) BEFORE the real
    ``apply_objective`` runs -- same technique as the existing harness's own
    ``_forced_worker_count``, no source file touched."""
    original = CpSatModel.apply_objective
    BOUND_UNITS = 200_000  # generous fixed bound; real board is a few 100mm

    def patched(self):
        for name, members in hpwl_nets.items():
            comp_vars = [self._components[r] for r in members if r in self._components]
            if len(comp_vars) < 2:
                continue
            xs = [cv.x_center for cv in comp_vars]
            ys = [cv.y_center for cv in comp_vars]
            max_x = self.model_ref.NewIntVar(0, BOUND_UNITS, f"hpwl_maxx_{name}")
            min_x = self.model_ref.NewIntVar(0, BOUND_UNITS, f"hpwl_minx_{name}")
            max_y = self.model_ref.NewIntVar(0, BOUND_UNITS, f"hpwl_maxy_{name}")
            min_y = self.model_ref.NewIntVar(0, BOUND_UNITS, f"hpwl_miny_{name}")
            self.model_ref.AddMaxEquality(max_x, xs)
            self.model_ref.AddMinEquality(min_x, xs)
            self.model_ref.AddMaxEquality(max_y, ys)
            self.model_ref.AddMinEquality(min_y, ys)
            span_x = self.model_ref.NewIntVar(0, BOUND_UNITS, f"hpwl_spanx_{name}")
            span_y = self.model_ref.NewIntVar(0, BOUND_UNITS, f"hpwl_spany_{name}")
            self.model_ref.Add(span_x == max_x - min_x)
            self.model_ref.Add(span_y == max_y - min_y)
            self.add_objective_term(span_x, 1)
            self.add_objective_term(span_y, 1)
        return original(self)

    @contextlib.contextmanager
    def _cm():
        CpSatModel.apply_objective = patched
        try:
            yield
        finally:
            CpSatModel.apply_objective = original

    return _cm()


@contextlib.contextmanager
def _null_cm():
    yield


def run_ortools(corpus, seed, timeout_ms, num_workers, hpwl_nets) -> dict:
    from temper_placer.placer.cp_sat.encoder import solve_placement

    t0 = time.monotonic()
    cm = hpwl_objective_patch(hpwl_nets) if hpwl_nets else _null_cm()
    with _forced_worker_count(num_workers), cm:
        result = solve_placement(
            netlist=corpus.netlist, board=corpus.board, extra_constraints=corpus.extra_constraints,
            timeout_ms=timeout_ms, seed=seed, zones=corpus.zones,
            zone_components=corpus.zone_components, loop_components=corpus.loop_components,
        )
    elapsed = (time.monotonic() - t0) * 1000.0
    return {
        "status": result.status, "objective_value": result.objective_value,
        "solve_time_ms": elapsed, "positions": dict(result.positions),
    }


def compute_hpwl(positions: dict, hpwl_nets: dict) -> float | None:
    total = 0.0
    any_net = False
    for _name, members in hpwl_nets.items():
        pts = [positions[m] for m in members if m in positions]
        if len(pts) < 2:
            continue
        any_net = True
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total if any_net else None


def main() -> None:
    print("Building real-board corpus (pcb/temper.kicad_pcb, 169 components)...", flush=True)
    corpus = build_real_board_corpus()
    vm = corpus.verification_model
    n_comp = len(vm.sizes_mm)
    n_constr = len(vm.constraints)
    hpwl_nets = build_hpwl_nets(corpus.netlist)
    n_nets = len(hpwl_nets)
    print(f"real-board-169: components={n_comp} constraints={n_constr} hpwl_nets={n_nets}", flush=True)

    seeds = [0, 1, 7]
    results: list[dict[str, Any]] = []

    for seed in seeds:
        r = run_ortools(corpus, seed, 30_000, 1, hpwl_nets=None)
        print(f"[ortools feasibility] seed={seed} timeout=30000 status={r['status']} solve_ms={r['solve_time_ms']:.0f}", flush=True)
        results.append({"engine": "ortools", "mode": "feasibility", "seed": seed, "timeout_ms": 30_000,
                         "status": r["status"], "objective_value": r["objective_value"], "solve_time_ms": r["solve_time_ms"]})
        rp = run_pumpkin(vm, None, seed, 30_000)
        print(f"[pumpkin feasibility] seed={seed} timeout=30000 status={rp.get('status')} solve_ms={rp.get('solve_time_ms', 0):.0f}", flush=True)
        results.append({"engine": "pumpkin", "mode": "feasibility", "seed": seed, "timeout_ms": 30_000,
                         "status": rp.get("status"), "objective_value": rp.get("objective_value"), "solve_time_ms": rp.get("solve_time_ms")})

    for timeout_ms in (5_000, 30_000):
        for seed in seeds:
            r = run_ortools(corpus, seed, timeout_ms, 1, hpwl_nets=hpwl_nets)
            hpwl_check = compute_hpwl(r["positions"], hpwl_nets)
            print(f"[ortools hpwl] seed={seed} timeout={timeout_ms} status={r['status']} obj={r['objective_value']} recomputed={hpwl_check} solve_ms={r['solve_time_ms']:.0f}", flush=True)
            results.append({"engine": "ortools", "mode": "hpwl", "seed": seed, "timeout_ms": timeout_ms,
                             "status": r["status"], "objective_value": r["objective_value"],
                             "recomputed_hpwl_mm": hpwl_check, "solve_time_ms": r["solve_time_ms"]})
            rp = run_pumpkin(vm, hpwl_nets, seed, timeout_ms)
            rp_positions = {k: tuple(v) for k, v in rp.get("positions", {}).items()}
            hpwl_check_p = compute_hpwl(rp_positions, hpwl_nets)
            print(f"[pumpkin hpwl] seed={seed} timeout={timeout_ms} status={rp.get('status')} obj={rp.get('objective_value')} recomputed={hpwl_check_p} solve_ms={rp.get('solve_time_ms', 0):.0f}", flush=True)
            results.append({"engine": "pumpkin", "mode": "hpwl", "seed": seed, "timeout_ms": timeout_ms,
                             "status": rp.get("status"), "objective_value": rp.get("objective_value"),
                             "recomputed_hpwl_mm": hpwl_check_p, "solve_time_ms": rp.get("solve_time_ms")})

    OUT_PATH.write_text(json.dumps({
        "provenance": {"note": "2026-08-11 real-budget spike, real board pcb/temper.kicad_pcb"},
        "n_components": n_comp, "n_constraints": n_constr, "n_hpwl_nets": n_nets,
        "seeds": seeds, "results": results,
    }, indent=2, default=str))
    print(f"\nWrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
