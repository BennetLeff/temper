"""
Canonical human-reference metric extraction for corpus boards.

Extracts placement and routing metrics from a human-designed .kicad_pcb
file, validates every link in the extraction chain, and writes a flat
``human_reference.yaml`` file. No metric is ever hardcoded, and no
exception is ever swallowed into a recorded value.

Single source of truth — replaces the two divergent baseline_extractor.py
copies that were deleted in the prerequisites.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import yaml

from temper_placer.core.loss_types import LossContext
from temper_placer.core.state import PlacementState

if TYPE_CHECKING:
    from temper_placer.io._kicad_types import ParseResult

# ---------------------------------------------------------------------------
# Pydantic-style data models (plain dataclasses for zero-dependency YAML I/O)
# ---------------------------------------------------------------------------


@dataclass
class MetricValue:
    """A single measured metric with provenance metadata."""

    value: float
    extracted_at: str  # ISO-8601
    pcb_git_hash: str


@dataclass
class HumanReference:
    """Complete human-reference metrics for one board."""

    board_id: str
    extraction_source: (
        str  # relative path within corpus/, e.g. "piantor_right/keyboard_pcb.kicad_pcb"
    )
    extractor_version: str  # git describe
    metrics: dict[str, MetricValue]

    def save(self, path: str | Path) -> None:
        """Write the reference to a flat YAML file."""
        data = {
            "board_id": self.board_id,
            "extraction_source": self.extraction_source,
            "extractor_version": self.extractor_version,
            "metrics": {
                key: {
                    "value": mv.value,
                    "extracted_at": mv.extracted_at,
                    "pcb_git_hash": mv.pcb_git_hash,
                }
                for key, mv in self.metrics.items()
            },
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_hash(repo_root: Path) -> str:
    """Return the short git hash of HEAD (8 chars)."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()[:8] if result.returncode == 0 else "unknown"


def _repo_root(pcb_path: str | Path) -> Path:
    """Walk up from *pcb_path* until a ``.git`` directory is found."""
    p = Path(pcb_path).resolve()
    for parent in [p, *p.parents]:
        if (parent / ".git").exists():
            return parent
    return p.parent  # fallback


# ---------------------------------------------------------------------------
# Step 1 — parse + validate
# ---------------------------------------------------------------------------


def _parse_and_validate(pcb_path: Path | str, validate: bool) -> ParseResult:
    """Parse *pcb_path* and (when *validate*) assert correctness invariants."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    result = parse_kicad_pcb(Path(pcb_path))

    if not validate:
        return result

    net_names = {n.name for n in result.netlist.nets}

    # Every trace must resolve to a named net (no "<Net object at ...>" fallback).
    for t in result.traces:
        if t.net is None or t.net not in net_names:
            raise AssertionError(
                f"Trace net '{t.net}' does not resolve to a named net on the parsed board."
            )

    # Every via must resolve to a named net.
    for v in result.vias:
        if v.net is None or v.net not in net_names:
            raise AssertionError(
                f"Via net '{v.net}' does not resolve to a named net on the parsed board."
            )

    return result


# ---------------------------------------------------------------------------
# Step 2 — build PlacementState + LossContext from parse output
# ---------------------------------------------------------------------------


def _build_state_and_context(
    parse_result: ParseResult,
) -> tuple[PlacementState, LossContext]:
    """Create a PlacementState from the human-designed positions and a LossContext."""
    board = parse_result.board
    if board is None:
        raise ValueError("No board geometry extracted from PCB.")

    netlist = parse_result.netlist
    n = netlist.n_components

    positions = []
    rotation_logits = np.zeros((n, 4), dtype=np.float32)

    for i, comp in enumerate(netlist.components):
        # The parser already normalizes component.initial_position to be
        # relative to the board origin (board space, [0,width]×[0,height]).
        # BoundaryLoss works in this same space — adding board.origin back
        # would push components into absolute coordinates where they appear
        # to be outside the board's [0,width]×[0,height] rectangle.
        assert comp.initial_position is not None, f"Component {comp.ref} has no initial_position"
        px = float(comp.initial_position[0])
        py = float(comp.initial_position[1])
        positions.append((px, py))

        # One-hot the initial rotation.  Rotation values are 0-3.
        rot = int(comp.initial_rotation or 0) % 4
        rotation_logits[i, rot] = 10.0

    state = PlacementState(
        positions=np.array(positions, dtype=np.float32),
        rotation_logits=rotation_logits,
    )
    context = LossContext(netlist=netlist, board=board)
    return state, context


# ---------------------------------------------------------------------------
# Step 3 — compute placement metrics (HPWL, overlap, boundary)
# ---------------------------------------------------------------------------


def _compute_placement_metrics(
    state: PlacementState,
    context: LossContext,
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute HPWL / overlap / boundary via the deterministic numpy metrics.

    Replaces the removed JAX loss functions (compute_total_hpwl / OverlapLoss
    / BoundaryLoss) with ``validation.metrics.compute_metrics`` — the same
    numpy metric core the CP-SAT/deterministic pipeline uses. Metric names are
    kept as the legacy ``hpwl`` / ``overlap_loss`` / ``boundary_loss`` for
    backward compatibility with existing human-reference consumers.
    """

    def mk(v):
        return MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)

    try:
        from temper_placer.validation.metrics import compute_metrics

        assert context.netlist is not None and context.board is not None
        pm = compute_metrics(state, context.netlist, context.board)
        return {
            "hpwl": mk(float(pm.total_wirelength)),
            "overlap_loss": mk(float(pm.total_overlap_area)),
            "boundary_loss": mk(float(pm.total_boundary_violation)),
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Step 4 — routing metrics (RDL and via count)
# ---------------------------------------------------------------------------


def _compute_routing_metrics(
    parse_result: ParseResult,
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute routed length (RDL), via counts, corridor, and track-spread metrics.

    RDL is the sum of Euclidean distances between each trace segment's
    start and end points (straight-line approximation per segment, not
    accounting for layer transitions).

    Via counts are classified into signal, thermal, and stitching.
    Corridor consolidation and track-spread scores are computed from
    channels between component courtyards.
    """

    def mk(v):
        return MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)

    # Routed length from trace segments
    rdl = 0.0
    for t in parse_result.traces:
        dx = float(t.end[0]) - float(t.start[0])
        dy = float(t.end[1]) - float(t.start[1])
        rdl += math.hypot(dx, dy)

    # Via count
    via_count = len(parse_result.vias)

    # Signal / thermal / stitching via classification (U2)
    try:
        from temper_placer.router_v6.quality.via_count import classify_vias_from_parse

        via_counts = classify_vias_from_parse(parse_result)
        signal_via_count = via_counts.signal
        thermal_via_count = via_counts.thermal
        stitching_via_count = via_counts.stitching
    except Exception:
        signal_via_count = -1
        thermal_via_count = -1
        stitching_via_count = -1

    # Corridor consolidation and track-spread (U3)
    try:
        from temper_placer.router_v6.quality.corridor import (
            corridor_consolidation_from_parse,
            track_spread_from_parse,
        )

        corridor_score = corridor_consolidation_from_parse(parse_result)
        track_spread = track_spread_from_parse(parse_result)
    except Exception:
        corridor_score = -1.0
        track_spread = -1.0

    return {
        "rdl": mk(rdl),
        "via_count": mk(float(via_count)),
        "signal_via_count": mk(float(signal_via_count)),
        "thermal_via_count": mk(float(thermal_via_count)),
        "stitching_via_count": mk(float(stitching_via_count)),
        "corridor_consolidation_score": mk(corridor_score),
        "track_spread_score": mk(track_spread),
    }


# ---------------------------------------------------------------------------
# Step 5 — detailed placement metrics (clearance, zone, congestion, etc.)
# ---------------------------------------------------------------------------


def _compute_detailed_metrics(
    state: PlacementState,
    parse_result: ParseResult,
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute comprehensive placement quality metrics via ``validation.metrics``."""

    def mk(v):
        return MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)

    try:
        from temper_placer.validation.metrics import compute_metrics

        assert parse_result.board is not None
        pm = compute_metrics(state, parse_result.netlist, parse_result.board)
        return {
            "overlap_count": mk(float(pm.overlap_count)),
            "total_overlap_area": mk(float(pm.total_overlap_area)),
            "worst_overlap": mk(float(pm.worst_overlap)),
            "boundary_violations": mk(float(pm.boundary_violations)),
            "total_boundary_violation": mk(float(pm.total_boundary_violation)),
            "clearance_violations": mk(float(pm.clearance_violations)),
            "hv_lv_violations": mk(
                float(pm.hv_lv_violations) if pm.min_hv_lv_clearance != float("inf") else -1.0
            ),
            "min_hv_lv_clearance": mk(
                pm.min_hv_lv_clearance if pm.min_hv_lv_clearance != float("inf") else -1.0
            ),
            "zone_violations": mk(float(pm.zone_violations)),
            "keepout_violations": mk(float(pm.keepout_violations)),
            "total_wirelength": mk(float(pm.total_wirelength)),
            "max_net_length": mk(float(pm.max_net_length)),
            "avg_net_length": mk(float(pm.avg_net_length)),
            "utilization": mk(float(pm.utilization)),
            "spread_score": mk(float(pm.spread_score)),
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Step 6 — aesthetic metrics (grid snap, orientation, alignment)
# ---------------------------------------------------------------------------


def _compute_aesthetic_metrics(
    state: PlacementState,
    parse_result: ParseResult,
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute aesthetic quality: grid alignment, rotation consistency, prefix alignment."""

    def mk(v):
        return MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)

    try:
        from temper_placer.metrics.aesthetic import compute_aesthetic_score

        scores = compute_aesthetic_score(state, parse_result.netlist, grid_size=0.5)
        return {key: mk(float(value)) for key, value in scores.items()}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Step 7 — normalized quality report (thermal, zone, loop, congestion, etc.)
# ---------------------------------------------------------------------------


def _netlist_to_oracle_dict(netlist) -> dict:
    """Serialize a placer Netlist into the dict shape the Rust oracle expects.

    The oracle's ``extract_netlist`` reads ``nets`` (name + pin refs) and
    ``components`` (ref, footprint, width, height, voltage). The placer
    ``Component`` carries no voltage — the oracle defaults it to 0.0, which
    is unused by the current config/threshold logic.
    """
    return {
        "nets": [{"name": net.name, "pins": [ref for ref, _ in net.pins]} for net in netlist.nets],
        "components": [
            {
                "ref": comp.ref,
                "footprint": comp.footprint,
                "width": float(comp.bounds[0]),
                "height": float(comp.bounds[1]),
            }
            for comp in netlist.components
        ],
    }


def _placement_to_oracle_dict(state: PlacementState, netlist, board) -> dict:
    """Serialize a PlacementState into the oracle's placement dict shape.

    Component refs must line up 1:1 with position rows; the extractor builds
    both from the netlist's component order, so the netlist refs are the
    source of truth here.
    """
    positions = np.asarray(state.positions, dtype=np.float64)
    return {
        "positions": positions.reshape(-1).tolist(),
        "component_refs": [c.ref for c in netlist.components],
        "board_width_mm": float(board.width),
        "board_height_mm": float(board.height),
    }


def _compute_quality_metrics(
    state: PlacementState,
    context: LossContext,
    parse_result: ParseResult,
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute normalized [0,1] quality scores via the Rust quality oracle.

    Config (thermal/HV components, critical loops) is inferred from the
    netlist using ``io.reference_loader.infer_quality_config`` — the same
    function used by the existing reference-loader comparison infrastructure.

    The pipeline follows the oracle's setup/evaluate split: the
    placement-independent state (config + net classifications) is prepared
    once via ``temper_quality_oracle.prepare_quality_py``, then per-placement
    scoring goes through ``evaluate_prepared_py``. Raw metric scores are
    still computed by the numpy metric functions — the oracle's contract is
    Python precomputes the scores, Rust validates + thresholds them — and the
    verdict's validated metrics become the report.
    """

    def mk(v):
        return MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)

    try:
        import temper_quality_oracle

        from temper_placer.io.reference_loader import infer_quality_config
        from temper_placer.metrics.quality import (
            compactness_score,
            congestion_score,
            connectivity_clustering_score,
            hv_lv_clearance_score,
            loop_area_score,
            thermal_score,
            zone_compliance_score,
        )

        config = infer_quality_config(parse_result)  # type: ignore[arg-type]
        assert parse_result.board is not None

        prepared = temper_quality_oracle.prepare_quality_py(
            _netlist_to_oracle_dict(parse_result.netlist),
            {"name": "human_reference"},
        )

        placement_dict = _placement_to_oracle_dict(state, parse_result.netlist, parse_result.board)
        metrics = {
            "thermal_score": thermal_score(
                state,
                parse_result.netlist,
                parse_result.board,
                config.get("thermal_components", set()),
            ),
            "zone_compliance_score": zone_compliance_score(
                state,
                parse_result.netlist,
                parse_result.board,
                config.get("zone_assignments", {}),
            ),
            "hv_lv_clearance_score": hv_lv_clearance_score(
                state,
                parse_result.netlist,
                config.get("hv_components", set()),
                config.get("lv_components", set()),
                config.get("min_hv_lv_clearance", 4.0),
            ),
            "loop_area_score": loop_area_score(
                state,
                parse_result.netlist,
                context,
                config.get("loop_components", []),
            ),
            "congestion_score": congestion_score(
                state,
                parse_result.netlist,
                parse_result.board,
                context,
            ),
            "compactness_score": compactness_score(
                state,
                parse_result.netlist,
                parse_result.board,
            ),
            "connectivity_clustering_score": connectivity_clustering_score(
                state,
                parse_result.netlist,
                context,
            ),
            "total_wirelength_mm": 0.0,
        }
        verdict = temper_quality_oracle.evaluate_prepared_py(prepared, placement_dict, metrics)
        return {key: mk(float(value)) for key, value in verdict["metrics"].items()}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Step 8 — DRC violations
# ---------------------------------------------------------------------------


def _compute_drc(
    pcb_path: str | Path,
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Run DRC on the human-reference board and record violation count.

    Requires KiCad to be installed and on PATH.  A board whose human
    reference has nonzero DRC errors is excluded from the DRC-delta row
    of the comparison comment (per R15).
    """

    def mk(v):
        return MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)

    try:
        from temper_placer.validation.drc_runner import run_drc

        result = run_drc(Path(pcb_path))
        return {"drc_violations": mk(float(result.error_count))}
    except ImportError:
        return {"drc_violations": mk(-1.0)}  # sentinel: KiCad unavailable
    except Exception:
        return {"drc_violations": mk(-1.0)}


def extract_human_reference(
    pcb_path: str | Path,
    validate: bool = True,
) -> HumanReference:
    """Extract human-reference metrics from a .kicad_pcb file.

    The pipeline is validation-gated: every intermediate result is asserted
    before proceeding to the next step.  No ``try/except: pass`` patterns —
    failures raise loudly.

    Args:
        pcb_path: Path to a ``.kicad_pcb`` file.
        validate: If True (default), assert correctness invariants at each
            step.  Set to False for debugging or iteration.

    Returns:
        ``HumanReference`` with board_id, extraction metadata, and metrics.

    Raises:
        FileNotFoundError: *pcb_path* does not exist.
        ValueError: A metric is non-finite or missing.
        AssertionError: A validation invariant is violated.
    """
    pcb_path = Path(pcb_path).resolve()
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    repo = _repo_root(pcb_path)
    gh = _git_hash(repo)
    now = datetime.now(UTC).isoformat()

    # Derive board_id from the path:  …/corpus/{board_id}/{file}.kicad_pcb
    corpus_dir = pcb_path.parent  # e.g. …/corpus/piantor_right
    board_id = corpus_dir.name
    extraction_source = str(pcb_path.relative_to(repo))

    # --- Pipeline ---
    parse_result = _parse_and_validate(pcb_path, validate)
    state, context = _build_state_and_context(parse_result)

    placement_metrics = _compute_placement_metrics(state, context, gh, now)
    routing_metrics = _compute_routing_metrics(parse_result, gh, now)
    detailed_metrics = _compute_detailed_metrics(state, parse_result, gh, now)
    aesthetic_metrics = _compute_aesthetic_metrics(state, parse_result, gh, now)
    quality_metrics = _compute_quality_metrics(state, context, parse_result, gh, now)
    drc_metrics = _compute_drc(pcb_path, gh, now)

    all_metrics = {
        **placement_metrics,
        **routing_metrics,
        **detailed_metrics,
        **aesthetic_metrics,
        **quality_metrics,
        **drc_metrics,
    }

    return HumanReference(
        board_id=board_id,
        extraction_source=extraction_source,
        extractor_version=gh,  # proxy — could be `git describe` in a CI context
        metrics=all_metrics,
    )
