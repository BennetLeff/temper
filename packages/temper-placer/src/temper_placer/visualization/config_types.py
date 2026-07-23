"""Configuration types for visualization functions with long parameter lists.

These dataclasses group logically related parameters that travel together,
reducing function signature complexity from 8-12 parameters to 3-4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BoardRenderOptions:
    """Rendering display options for render_board.

    Groups the 9 display-related keyword arguments that previously
    inflated render_board's signature to 12 parameters.
    """

    title: str | None = None
    show_refs: bool = True
    show_status_colors: bool = True
    show_zones: bool = True
    show_grid: bool = True
    show_traces: bool = True
    show_pads: bool = True
    show_legend: bool = True
    width: int = 800
    height: int = 600
