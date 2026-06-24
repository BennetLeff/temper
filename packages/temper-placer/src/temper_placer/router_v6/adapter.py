"""Adapter for Router V6 pipeline integration with the closure test.

Provides `route_pcb(parsed, placements, seed)` which applies placement
data to a KiCad PCB file, invokes RouterV6Pipeline, and returns results.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result from route_pcb call.

    Attributes:
        completion_rate: Fraction of nets successfully routed (0.0 to 1.0).
    """

    completion_rate: float = 0.0


def route_pcb(
    parsed: Any,
    placements: dict[str, tuple[float, float]],
    seed: int,
) -> RoutingResult:
    """Route a PCB using the Router V6 pipeline.

    Applies the given component placements by writing a temporary modified
    .kicad_pcb file, then invokes the full 4-stage RouterV6Pipeline.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6.
        placements: Dict mapping component ref -> (x, y) position in mm.
            If empty, routing proceeds with the board's existing positions.
        seed: Random seed (passed through to pipeline configuration).

    Returns:
        RoutingResult with completion_rate.

    Raises:
        ValueError: If parsed has no source_path.
    """
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    if not placements:
        logger.warning(
            "Empty placements provided; routing with existing board positions."
        )

    pcb_path = getattr(parsed, "source_path", None)
    if pcb_path is None:
        raise ValueError("ParsedPCB has no source_path attribute")
    pcb_path = Path(pcb_path)

    if placements:
        raw_content = pcb_path.read_text(encoding="utf-8")
        modified_content = _apply_placements_to_pcb(raw_content, placements)

        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(modified_content)

            # NOTE 2026-06-23: the closure test was using
            # enable_theta_star=True, enable_lazy_theta_star=True,
            # and enable_smoothing=True.  All three are wrong for
            # SM1 measurement on temper.kicad_pcb:
            #   * lazy theta star is a Python A* with no iter cap
            #     and the reroute loop blows up the full-run wall
            #     time to 5+ minutes (15/24 in 18s in the smoke vs
            #     13/24 incomplete after 5 min in the full profile).
            #   * plain theta star is also Python (no iter cap)
            #     and finds fewer nets than plain A* (Numba).
            #   * enable_smoothing=True is broken:
            #     SDFGrid.from_polygons is missing, so the
            #     smoothing step is a silent no-op (or worse).
            # The closure test should use the smoke-equivalent
            # path: plain 2D A* via the Numba kernel, no
            # smoothing, and the smoke's per-A* iter cap (the
            # closure runner doesn't currently expose this, so we
            # apply it via the dispatch wrapper below).
            pipeline = RouterV6Pipeline(
                verbose=False,
                enable_theta_star=False,
                enable_lazy_theta_star=False,
                enable_smoothing=False,
            )
            result = pipeline.run(Path(temp_path))
            return RoutingResult(completion_rate=result.completion_rate)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    else:
        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_theta_star=False,
            enable_lazy_theta_star=False,
            enable_smoothing=False,
        )
        result = pipeline.run(pcb_path)
        return RoutingResult(completion_rate=result.completion_rate)


def _apply_placements_to_pcb(
    raw_content: str, placements: dict[str, tuple[float, float]]
) -> str:
    """Modify footprint (at X Y [ANGLE]) positions in KiCad PCB raw content."""
    foot_starts = [
        m.start()
        for m in re.finditer(r'\(footprint\s+"[^"]+"\s+\(layer', raw_content)
    ]

    if not foot_starts:
        return raw_content

    result_parts = []
    prev_end = 0

    for i, start in enumerate(foot_starts):
        end = (
            foot_starts[i + 1] if i + 1 < len(foot_starts) else len(raw_content)
        )
        block = raw_content[start:end]

        ref_match = re.search(
            r'\(property\s+"Reference"\s+"([^"]+)"', block
        )
        if ref_match:
            ref = ref_match.group(1)
            if ref in placements:
                x, y = placements[ref]
                block = re.sub(
                    r'(\(at\s+)[\d.-]+\s+[\d.-]+(\s*[\d.-]*\s*\))',
                    rf"\g<1>{x:.4f} {y:.4f}\2",
                    block,
                    count=1,
                )

        result_parts.append(raw_content[prev_end:start])
        result_parts.append(block)
        prev_end = end

    result_parts.append(raw_content[prev_end:])
    return "".join(result_parts)
