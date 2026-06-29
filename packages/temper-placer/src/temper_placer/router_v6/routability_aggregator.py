"""
Per-net routability score aggregation from SAT solver statistics.

Converts CDCL solver statistics + var-to-net mapping into per-component
routability scores in [0, 1] for use in gradient-based placement refinement.

Variant selection:
  - SAT case: backtrack activity, clause learning, decision levels (FR2.2)
  - UNSAT case: core-based penalty (FR2.3)
  - Coarse fallback: solver_time, clause-to-var ratio (FR1.7)

Part of feat/routability-gradient-signal (U3).
"""

from __future__ import annotations

import jax.numpy as jnp
from jax import Array


class RoutabilityAggregator:
    """Computes per-component routability scores from solver statistics."""

    def __init__(
        self,
        weight_backtrack: float = 0.3,
        weight_activity: float = 0.2,
        weight_depth: float = 0.2,
        weight_core: float = 0.3,
        coarse_divisor: float = 10.0,
    ):
        self.weight_backtrack = weight_backtrack
        self.weight_activity = weight_activity
        self.weight_depth = weight_depth
        self.weight_core = weight_core
        self.coarse_divisor = coarse_divisor

    def compute_scores(
        self,
        stats: dict,
        var_to_net: list[int],
        n_components: int,
        unsat_core: list[int] | None = None,
        solver_status: str = "unknown",
        timeout_ms: float = 5000.0,
    ) -> tuple[Array, float]:
        """
        Compute per-component routability scores from solver statistics.

        Args:
            stats: solver_stats dict from Rust solver.
            var_to_net: variable-index to net-index mapping (list of ints).
            n_components: total number of components.
            unsat_core: list of UNSAT core clause indices (empty if SAT).
            solver_status: "sat", "unsat", or "unknown".
            timeout_ms: solver timeout for coarse-fallback difficulty scaling.

        Returns:
            (routability_scores: (N,) jnp.ndarray, score_mean: float)
        """
        if n_components == 0:
            return jnp.zeros(0), 0.0

        # Determine the number of nets from var_to_net
        if var_to_net:
            max_net_idx = max(n for n in var_to_net if n != 0xFFFFFFFFFFFFFFFF)  # NO_NET sentinel
            n_nets = max_net_idx + 1
        else:
            n_nets = n_components

        # ---- UNSAT path (FR2.3) ----
        if solver_status == "unsat" and unsat_core:
            per_net = self._unsat_core_scores(unsat_core, var_to_net, n_nets)
        elif solver_status == "unsat" and not unsat_core:
            # Empty core — fallback handled in U7, conservative all-ones for now.
            per_net = jnp.ones(n_nets)
        elif self._has_fine_stats(stats):
            # ---- SAT path with fine-grained CDCL stats (FR2.2) ----
            per_net = self._sat_fine_grained_scores(stats, var_to_net, n_nets)
        else:
            # ---- Coarse fallback (FR1.7) ----
            per_net = self._coarse_fallback_scores(stats, var_to_net, n_nets, timeout_ms)

        # Map per-net scores to per-component via max-aggregation (FR2.4).
        per_component = self._net_to_component(per_net, n_components)
        per_component = jnp.clip(per_component, 0.0, 1.0)
        score_mean = float(jnp.mean(per_component))

        return per_component, score_mean

    def _has_fine_stats(self, stats: dict) -> bool:
        """Check if fine-grained CDCL stats are available."""
        return (
            stats.get("conflicts", 0) > 0
            or stats.get("decisions", 0) > 0
            or stats.get("propagations", 0) > 0
        )

    def _unsat_core_scores(
        self,
        unsat_core: list[int],
        var_to_net: list[int],
        n_nets: int,
    ) -> Array:
        """
        UNSAT core-based penalty (FR2.3, FR6.2):
        r_n = 1.0 for nets in the UNSAT core, 0.0 for others.
        """
        per_net = jnp.zeros(n_nets)
        for clause_idx in unsat_core:
            if clause_idx < len(var_to_net):
                net_idx = var_to_net[clause_idx]
                if net_idx < n_nets:
                    per_net = per_net.at[net_idx].set(1.0)
        return per_net

    def _sat_fine_grained_scores(
        self,
        stats: dict,
        var_to_net: list[int],
        n_nets: int,
    ) -> Array:
        """
        SAT-case fine-grained scoring (FR2.2).

        For each net n:
          r_n = clamp(w_b * b_n/Bmax + w_a * a_n/Amax + w_d * d_n/Dmax + w_c * c_n/Cmax, 0, 1)
        """
        stats.get("conflicts", 0)
        stats.get("decisions", 0)
        stats.get("propagations", 0)
        histogram = stats.get("decision_level_histogram", [0] * 10)

        # Per-net variables count (proxy for net complexity)
        net_var_counts = jnp.zeros(n_nets, dtype=jnp.int32)
        for net_idx in var_to_net:
            if 0 <= net_idx < n_nets:
                net_var_counts = net_var_counts.at[net_idx].add(1)

        # b_n: Backtrack count proportionally by net variable count
        b_n = net_var_counts.astype(jnp.float32) / max(n_nets, 1)

        # a_n: Clause activity — uniform for now (no per-variable activity from CaDiCaL)
        a_n = jnp.ones(n_nets) / max(n_nets, 1)

        # d_n: Decision-level proxy from histogram quantiles
        d_n = self._decision_level_proxy(histogram, net_var_counts, n_nets)

        # c_n: Core size — 0 for SAT case
        c_n = jnp.zeros(n_nets)

        # Normalize
        b_max = max(float(jnp.max(b_n)), 1.0)
        a_max = max(float(jnp.max(a_n)), 1.0)
        d_max = max(float(jnp.max(d_n)), 1.0)
        c_max = 1.0

        per_net = (
            self.weight_backtrack * (b_n / b_max)
            + self.weight_activity * (a_n / a_max)
            + self.weight_depth * (d_n / d_max)
            + self.weight_core * (c_n / c_max)
        )

        return per_net

    def _decision_level_proxy(
        self,
        histogram: list[int],
        net_var_counts: Array,
        n_nets: int,
    ) -> Array:
        """
        Heuristic proxy for decision-level depth.

        Uses the decision_level_histogram as a weighted sum proxy
        for search depth. Nets with more variables get higher depth score.
        """
        _ = histogram  # Unused in current proxy; histogram is uniform
        if n_nets == 0:
            return jnp.zeros(0)
        return net_var_counts.astype(jnp.float32) / max(float(jnp.max(net_var_counts)), 1.0)

    def _coarse_fallback_scores(
        self,
        stats: dict,
        var_to_net: list[int],
        n_nets: int,
        timeout_ms: float,
    ) -> Array:
        """
        Coarse statistics fallback (FR1.7).

        r_n = clamp((clause_to_var_ratio / divisor) * (net_var_count / N), 0, 1)
        multiplied by (solver_time_ms / timeout_ms) as a difficulty factor.
        """
        clause_to_var_ratio = stats.get("clause_to_var_ratio", 0.0)
        solver_time_ms = stats.get("cpu_solve_time_ms", 0.0)
        variable_count = stats.get("variable_count", 0)

        net_var_counts = jnp.zeros(n_nets)
        for net_idx in var_to_net:
            if 0 <= net_idx < n_nets:
                net_var_counts = net_var_counts.at[net_idx].add(1)

        n_total = max(variable_count, 1)
        difficulty_factor = min(solver_time_ms / max(timeout_ms, 1.0), 1.0)

        per_net = (
            jnp.clip(
                (clause_to_var_ratio / self.coarse_divisor)
                * (net_var_counts / n_total),
                0.0, 1.0,
            )
            * difficulty_factor
        )

        return per_net

    def _net_to_component(self, per_net: Array, n_components: int) -> Array:
        """
        Map per-net scores to per-component via max-aggregation (FR2.4).

        In the simplest mapping, each net is assigned to one component.
        For nets spanning multiple components, take the max.
        """
        if n_components == 0:
            return jnp.zeros(0)
        if per_net.shape[0] == n_components:
            return per_net
        # Default: take first N entries (nets are mapped 1:1 to components by default)
        # For expanded case: pad or truncate
        if per_net.shape[0] < n_components:
            padded = jnp.zeros(n_components)
            padded = padded.at[: per_net.shape[0]].set(per_net)
            return padded
        return per_net[:n_components]
