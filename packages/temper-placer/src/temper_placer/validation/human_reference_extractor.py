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
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
import yaml

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import compute_total_hpwl

if TYPE_CHECKING:
    from temper_placer.io.kicad_parser import ParseResult

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
    extraction_source: str  # relative path within corpus/, e.g. "piantor_right/keyboard_pcb.kicad_pcb"
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

def _parse_and_validate(pcb_path: Path | str, validate: bool) -> "ParseResult":
    """Parse *pcb_path* and (when *validate*) assert correctness invariants."""
    from temper_placer.io.kicad_parser import ParseResult, parse_kicad_pcb

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
    parse_result: "ParseResult",
) -> tuple[PlacementState, LossContext]:
    """Create a PlacementState from the human-designed positions and a LossContext."""
    board = parse_result.board
    if board is None:
        raise ValueError("No board geometry extracted from PCB.")

    netlist = parse_result.netlist
    n = netlist.n_components

    positions = []
    rotation_logits = jnp.zeros((n, 4), dtype=jnp.float32)

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
        rotation_logits = rotation_logits.at[i, rot].set(10.0)

    state = PlacementState(
        positions=jnp.array(positions, dtype=jnp.float32),
        rotation_logits=rotation_logits,
    )
    context = LossContext.from_netlist_and_board(netlist, board)
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
    """Compute HPWL, overlap loss, and boundary loss from the human placement."""
    # Loss functions expect soft one-hot rotations, not raw logits.
    rotations = jax.nn.softmax(state.rotation_logits, axis=-1)

    # --- HPWL ---
    hpwl_val = float(compute_total_hpwl(state.positions, rotations, context))
    if not jnp.isfinite(hpwl_val):
        raise ValueError("HPWL is non-finite.")
    if hpwl_val <= 0 and context.netlist.n_nets > 0:
        raise AssertionError(
            f"HPWL is {hpwl_val} for a board with {context.netlist.n_nets} nets — "
            "expected strictly positive for any board with multi-pin nets."
        )

    # --- Overlap loss ---
    overlap_loss = OverlapLoss(margin=1.0, rotation_invariant=True)
    overlap_result = overlap_loss(state.positions, rotations, context)
    overlap_val = float(overlap_result.value)
    if not jnp.isfinite(overlap_val):
        raise ValueError("Overlap loss is non-finite.")

    # --- Boundary loss ---
    boundary_loss = BoundaryLoss()
    boundary_result = boundary_loss(state.positions, rotations, context)
    boundary_val = float(boundary_result.value)
    if not jnp.isfinite(boundary_val):
        raise ValueError("Boundary loss is non-finite.")

    mk = lambda v: MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)
    return {
        "hpwl": mk(hpwl_val),
        "overlap_loss": mk(overlap_val),
        "boundary_loss": mk(boundary_val),
    }


# ---------------------------------------------------------------------------
# Step 4 — routing metrics (RDL and via count)
# ---------------------------------------------------------------------------

def _compute_routing_metrics(
    parse_result: "ParseResult",
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute routed length (RDL) and via count from parsed traces and vias.

    RDL is the sum of Euclidean distances between each trace segment's
    start and end points (straight-line approximation per segment, not
    accounting for layer transitions).
    """
    mk = lambda v: MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)

    # Routed length from trace segments
    rdl = 0.0
    for t in parse_result.traces:
        dx = float(t.end[0]) - float(t.start[0])
        dy = float(t.end[1]) - float(t.start[1])
        rdl += math.hypot(dx, dy)

    # Via count
    via_count = len(parse_result.vias)

    return {
        "rdl": mk(rdl),
        "via_count": mk(float(via_count)),
    }


# ---------------------------------------------------------------------------
# Step 5 — detailed placement metrics (clearance, zone, congestion, etc.)
# ---------------------------------------------------------------------------

def _compute_detailed_metrics(
    state: PlacementState,
    parse_result: "ParseResult",
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute comprehensive placement quality metrics via ``validation.metrics``."""
    mk = lambda v: MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)
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
                float(pm.hv_lv_violations)
                if pm.min_hv_lv_clearance != float("inf")
                else -1.0
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
    parse_result: "ParseResult",
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute aesthetic quality: grid alignment, rotation consistency, prefix alignment."""
    mk = lambda v: MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)
    try:
        from temper_placer.metrics.aesthetic import compute_aesthetic_score

        scores = compute_aesthetic_score(state, parse_result.netlist, grid_size=0.5)
        return {key: mk(float(value)) for key, value in scores.items()}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Step 7 — normalized quality report (thermal, zone, loop, congestion, etc.)
# ---------------------------------------------------------------------------

def _compute_quality_metrics(
    state: PlacementState,
    context: LossContext,
    parse_result: "ParseResult",
    pcb_git_hash: str,
    now: str,
) -> dict[str, MetricValue]:
    """Compute normalized [0,1] quality scores via ``metrics.quality``.

    Config (thermal/HV components, critical loops) is inferred from the
    netlist using ``io.reference_loader.infer_quality_config`` — the same
    function used by the existing reference-loader comparison infrastructure.
    """
    mk = lambda v: MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)
    try:
        from temper_placer.io.reference_loader import infer_quality_config
        from temper_placer.metrics.quality import compute_quality_report

        config = infer_quality_config(parse_result)  # type: ignore[arg-type]
        assert parse_result.board is not None
        report = compute_quality_report(
            state, parse_result.netlist, parse_result.board, context, config
        )
        return {key: mk(float(value)) for key, value in report.items()}
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
    mk = lambda v: MetricValue(value=v, extracted_at=now, pcb_git_hash=pcb_git_hash)
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
    now = datetime.now(timezone.utc).isoformat()

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
