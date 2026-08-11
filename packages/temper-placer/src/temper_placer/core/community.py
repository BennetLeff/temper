"""
Community dataclass for representing detected functional clusters of components.

This module provides the :class:`Community` dataclass which is the public API
type for community detection results. The Louvain detection and Kernighan-Lin
bisection functions were deleted in Spike S6 (2026-08-11) as dead code with
0 production call sites.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Community:
    """A detected functional cluster of components."""

    name: str
    component_refs: list[str]
    modularity_score: float
