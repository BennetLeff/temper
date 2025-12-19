"""
Routing feedback loss function with caching.

This module provides:
- RoutingLoss: Loss function that wraps an autorouter to get real routing metrics
- Caching to avoid running expensive routing on every epoch
- Metrics tracking (wirelength, via count, completion %)

Routing is non-differentiable and very expensive, so this loss function 
returns a cached penalty value based on real routing results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult
from temper_placer.routing.freerouting import FreeRoutingWrapper, RoutingMetrics


@dataclass
class RoutingCacheEntry:
    """Cached routing results."""
    penalty: float
    epoch: int
    metrics: Optional[RoutingMetrics] = None
    elapsed_s: float = 0.0

class RoutingLoss(LossFunction):
    """
    Loss function that evaluates real routing periodically and caches results.
    
    Attributes:
        router: FreeRoutingWrapper instance.
        pcb_exporter: Function to export current placement to KiCad PCB.
        eval_interval: Epochs between routing evaluations.
        base_penalty: Default penalty when routing is not available.
        weight_wirelength: Multiplier for total routed wirelength in penalty.
        weight_vias: Multiplier for via count in penalty.
        weight_unrouted: Multiplier for unrouted nets in penalty.
    """

    def __init__(
        self,
        router: FreeRoutingWrapper,
        pcb_exporter: Optional[Callable[[Array, Array, LossContext], Path]] = None,
        eval_interval: int = 200,
        base_penalty: float = 0.0,
        weight_wirelength: float = 0.1,
        weight_vias: float = 5.0,
        weight_unrouted: float = 50.0,
    ):
        self._router = router
        self._pcb_exporter = pcb_exporter
        self._eval_interval = eval_interval
        self._base_penalty = base_penalty
        self._weight_wirelength = weight_wirelength
        self._weight_vias = weight_vias
        self._weight_unrouted = weight_unrouted

        self._cache: Optional[RoutingCacheEntry] = None
        self._last_eval_epoch: int = -1
        self.history: List[Tuple[int, RoutingMetrics]] = []

    @property
    def name(self) -> str:
        return "routing_loss"

    def should_evaluate(self, epoch: int) -> bool:
        if self._pcb_exporter is None:
            return False
        if self._cache is None:
            return True
        return (epoch - self._last_eval_epoch) >= self._eval_interval

    def evaluate(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
    ) -> RoutingCacheEntry:
        if self._pcb_exporter is None:
            return RoutingCacheEntry(self._base_penalty, epoch)

        start_time = time.time()
        try:
            # 1. Export to KiCad PCB
            pcb_path = self._pcb_exporter(positions, rotations, context)
            
            # 2. Run Router
            routed_pcb, metrics = self._router.route_pcb(pcb_path)
            
            # 3. Compute Penalty
            if metrics.success:
                # Penalty = w_l * length + w_v * vias + w_u * unrouted
                penalty = (
                    self._weight_wirelength * metrics.wirelength_mm +
                    self._weight_vias * metrics.via_count +
                    self._weight_unrouted * metrics.unrouted_count
                )
            else:
                penalty = 1000.0  # High penalty for total failure
                
            elapsed_s = time.time() - start_time
            entry = RoutingCacheEntry(penalty, epoch, metrics, elapsed_s)
            
            self._cache = entry
            self._last_eval_epoch = epoch
            self.history.append((epoch, metrics))
            
            return entry
            
        except Exception as e:
            print(f"Routing evaluation failed: {e}")
            return RoutingCacheEntry(1000.0, epoch)

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        penalty = self._cache.penalty if self._cache else self._base_penalty
        
        breakdown = {
            "routing_penalty": jnp.array(penalty),
            "routing_cached_epoch": jnp.array(self._last_eval_epoch, dtype=jnp.float32)
        }
        
        if self._cache and self._cache.metrics:
            m = self._cache.metrics
            breakdown["routed_wirelength"] = jnp.array(m.wirelength_mm)
            breakdown["routed_vias"] = jnp.array(m.via_count, dtype=jnp.float32)
            breakdown["unrouted_nets"] = jnp.array(m.unrouted_count, dtype=jnp.float32)

        return LossResult(jnp.array(penalty), breakdown)
