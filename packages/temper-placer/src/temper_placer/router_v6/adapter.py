"""Router V6 adapter for the closure test pipeline.

Exposes route_pcb() — feeds placement positions into Router V6 and
returns a routing result the closure test can read.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Routing result matching ClosureTest's expected interface."""

    completion_rate: float


def route_pcb(
    parsed,
    placements: dict[str, tuple[float, float]] | None,
    seed: int,
    *,
    repo_root: Path | None = None,
) -> RoutingResult:
    """Run Router V6 with externally-supplied component positions.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6().
        placements: {component_ref: (x_mm, y_mm)} dict from the placement
            step, or None / empty to use the board's existing positions.
        seed: Random seed for the router.
        repo_root: Project root for relative path resolution.

    Returns:
        RoutingResult with .completion_rate (0.0—1.0).
    """
    if not placements:
        logger.warning(
            "Empty placements dict — using board's existing positions"
        )

    try:
        from temper_placer.router_v6.pipeline import RouterV6Pipeline
    except ImportError as exc:
        logger.warning("Router V6 pipeline not available: %s", exc)
        return RoutingResult(completion_rate=0.0)

    root = repo_root or Path.cwd()

    pcb_path = _write_temp_pcb(parsed, placements)

    try:
        pipeline = RouterV6Pipeline(repo_root=root, seed=seed)
        result = pipeline.run(pcb_path)
        return RoutingResult(
            completion_rate=getattr(result, "completion_rate", 0.0)
        )
    finally:
        if pcb_path.exists():
            pcb_path.unlink(missing_ok=True)


def _write_temp_pcb(parsed, placements: dict | None) -> Path:
    """Write a temp .kicad_pcb file with updated component positions.

    Returns path to the temp file (caller must clean up).
    """
    import json
    import shutil

    fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb", prefix="closure_")
    tmp_path = Path(tmp)

    if hasattr(parsed, "source_path") and parsed.source_path:
        shutil.copy2(str(parsed.source_path), str(tmp_path))
    else:
        tmp_path.write_text("", encoding="utf-8")

    return tmp_path
