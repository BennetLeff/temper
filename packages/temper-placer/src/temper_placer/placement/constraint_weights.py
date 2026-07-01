"""
Constraint-to-Laplacian-weight mapping for spectral initialization.

This module resolves PCL constraint component references to netlist nets
and computes per-edge weight contributions from five derivation strategies:
proximity, group coherence, critical loop, HV/LV repulsion, and clearance.

@req(2026-07-01-002, U1): ConstraintMapper class with (c1,c2)->[Net] mapping
@req(2026-07-01-002, U2): Five weight-derivation strategies
@req(2026-07-01-002, K5): Per-edge constraint_weight dict separate from Net.weight
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Net, Netlist
    from temper_placer.io.config_loader import CriticalLoop, PlacementConstraints
    from temper_placer.pcl.parser import ConstraintCollection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Calibration constants — defaults set from the grid-search in U5.
# Per-design overrides available via placer.initialization.calibration YAML.
# ---------------------------------------------------------------------------
K_HARD: float = 100.0
K_STRONG: float = 10.0
K_SOFT: float = 1.0
C_ISO: float = 21600.0
ALPHA_COHERENCE: float = 2.0
PSD_SHIFT_MAX_RATIO: float = 0.5

# Board-diagonal fallback for unconstrained nets (mm)
_BOARD_DIAGONAL_DEFAULT: float = 500.0
# Voltage normalization reference (V)
_V_REF: float = 400.0


# =============================================================================
# U1: ConstraintMapper
# =============================================================================


@dataclass
class ConstraintMapper:
    """Precompute (component_ref_a, component_ref_b) -> list[Net] for
    adjacency constraints, and loop_name -> list[component_ref] for
    loop-area constraints.

    This is a one-time O(N_nets * avg_pins²) precompute consumed by all
    weight-derivation strategies.
    """

    adjacency_nets: dict[tuple[str, str], list["Net"]] = field(default_factory=dict)
    loop_components: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        pcl_collection: "ConstraintCollection | None",
        placement_constraints: "PlacementConstraints | None",
        netlist: "Netlist",
    ) -> "ConstraintMapper":
        """Construct the mapper from PCL constraints and placement constraints.

        Args:
            pcl_collection: Optional PCL ConstraintCollection (adjacent/separated/loop).
            placement_constraints: Optional PlacementConstraints (component_groups, critical_loops).
            netlist: Netlist with nets and components.

        Returns:
            ConstraintMapper with precomputed mappings.
        """
        mapper = cls()

        if pcl_collection is not None:
            mapper._build_adjacency_from_pcl(pcl_collection, netlist)
            mapper._build_loop_from_pcl(pcl_collection, placement_constraints, netlist)

        if placement_constraints is not None:
            mapper._build_loop_from_critical_loops(placement_constraints, netlist)

        return mapper

    def _build_adjacency_from_pcl(
        self,
        pcl_collection: "ConstraintCollection",
        netlist: "Netlist",
    ) -> None:
        from temper_placer.pcl.constraints import AdjacentConstraint

        comp_to_nets: dict[str, set[int]] = {}
        for i, net in enumerate(netlist.nets):
            for ref, _ in net.pins:
                comp_to_nets.setdefault(ref, set()).add(i)

        for constraint in pcl_collection.constraints:
            if not isinstance(constraint, AdjacentConstraint):
                continue
            a, b = constraint.a, constraint.b
            a_nets = comp_to_nets.get(a, set())
            b_nets = comp_to_nets.get(b, set())
            shared = a_nets & b_nets
            if not shared:
                logger.warning(
                    "AdjacentConstraint %s-%s: no shared nets found in netlist", a, b
                )
                continue
            nets = [netlist.nets[i] for i in shared]
            key = (a, b) if a < b else (b, a)
            self.adjacency_nets[key] = nets

    def _build_loop_from_pcl(
        self,
        pcl_collection: "ConstraintCollection",
        placement_constraints: "PlacementConstraints | None",
        netlist: "Netlist",
    ) -> None:
        from temper_placer.pcl.constraints import LoopAreaConstraint

        for constraint in pcl_collection.constraints:
            if not isinstance(constraint, LoopAreaConstraint):
                continue
            comps = self._resolve_loop_components(
                constraint.loop_name, placement_constraints, netlist
            )
            if comps is not None:
                self.loop_components[constraint.loop_name] = comps
            else:
                logger.warning(
                    "LoopAreaConstraint '%s': no component references resolvable",
                    constraint.loop_name,
                )

    def _build_loop_from_critical_loops(
        self,
        placement_constraints: "PlacementConstraints",
        netlist: "Netlist",
    ) -> None:
        for cl in placement_constraints.critical_loops:
            comps = self._resolve_critical_loop_components(cl, netlist)
            if comps:
                self.loop_components[cl.name] = comps
            else:
                logger.warning(
                    "CriticalLoop '%s': no components resolvable from nets list", cl.name
                )

    @staticmethod
    def _resolve_loop_components(
        loop_name: str,
        placement_constraints: "PlacementConstraints | None",
        netlist: "Netlist",
    ) -> list[str] | None:
        if placement_constraints is None:
            return None

        for cg in placement_constraints.component_groups:
            if cg.name == loop_name and cg.components:
                return list(cg.components)

        for cl in placement_constraints.critical_loops:
            if cl.name == loop_name:
                comps = ConstraintMapper._resolve_critical_loop_components(cl, netlist)
                if comps:
                    return comps

        return None

    @staticmethod
    def _resolve_critical_loop_components(
        cl: "CriticalLoop",
        netlist: "Netlist",
    ) -> list[str] | None:
        comps: set[str] = set()
        for net_name in cl.nets:
            try:
                net = netlist.get_net(net_name)
                for ref, _ in net.pins:
                    comps.add(ref)
            except Exception:
                logger.warning(
                    "CriticalLoop '%s': net '%s' not found in netlist", cl.name, net_name
                )
        return sorted(comps) if comps else None


# =============================================================================
# U2: Weight Derivation Strategies
# =============================================================================


def _tier_k(tier_value: int, k_hard: float, k_strong: float, k_soft: float) -> float:
    """Map ConstraintTier value (1=HARD, 2=STRONG, 3=SOFT) to spring constant."""
    if tier_value == 1:
        return k_hard
    elif tier_value == 2:
        return k_strong
    return k_soft


# -- U2.1: Proximity -----------------------------------------------------------


def proximity_weight(
    max_distance_mm: float,
    tier: int = 3,
    k_hard: float = K_HARD,
    k_strong: float = K_STRONG,
    k_soft: float = K_SOFT,
) -> float:
    """Compute proximity edge weight from an AdjacentConstraint.

    w_proximity(i,j) = k_tier / max_distance_mm
    """
    if max_distance_mm <= 0:
        return 0.0
    k = _tier_k(tier, k_hard, k_strong, k_soft)
    return k / max_distance_mm


def _apply_proximity_weights(
    weights: dict[tuple[int, int], float],
    ref_to_idx: dict[str, int],
    k_hard: float,
    k_strong: float,
    k_soft: float,
    pcl_collection: "ConstraintCollection | None",
) -> None:
    if pcl_collection is None:
        return
    from temper_placer.pcl.constraints import AdjacentConstraint

    for constraint in pcl_collection.constraints:
        if not isinstance(constraint, AdjacentConstraint):
            continue
        a, b = constraint.a, constraint.b
        if a not in ref_to_idx or b not in ref_to_idx:
            continue
        idx_a, idx_b = ref_to_idx[a], ref_to_idx[b]
        key = (min(idx_a, idx_b), max(idx_a, idx_b))
        w = proximity_weight(
            constraint.max_distance_mm,
            tier=constraint.tier.value,
            k_hard=k_hard,
            k_strong=k_strong,
            k_soft=k_soft,
        )
        weights[key] = weights.get(key, 0.0) + w


# -- U2.2: Group Coherence ----------------------------------------------------


def group_coherence_weight(
    w_base: float,
    group_fraction: float,
    alpha_coherence: float = ALPHA_COHERENCE,
) -> float:
    """Compute group coherence weight boost.

    w_coherence(i,j) = w_base * (1 + alpha_coherence * group_fraction)
    """
    return w_base * (1.0 + alpha_coherence * group_fraction)


def _apply_group_coherence_weights(
    weights: dict[tuple[int, int], float],
    netlist: "Netlist",
    placement_constraints: "PlacementConstraints",
    ref_to_idx: dict[str, int],
    alpha_coherence: float,
) -> None:
    if not placement_constraints.component_groups:
        return

    comp_nets: dict[str, set[str]] = {}
    for net in netlist.nets:
        for ref, _ in net.pins:
            comp_nets.setdefault(ref, set()).add(net.name)

    processed: set[tuple[int, int]] = set()

    for cg in placement_constraints.component_groups:
        comps_in_group = [r for r in cg.components if r in ref_to_idx]
        group_refs = set(cg.components)

        # Precompute nets that touch any component in this group (O(N_nets)
        # once per group, instead of O(N_nets) per pair).
        group_nets: set[str] = set()
        for net in netlist.nets:
            net_refs = {r for r, _ in net.pins}
            if net_refs & group_refs:
                group_nets.add(net.name)

        for i in range(len(comps_in_group)):
            for j in range(i + 1, len(comps_in_group)):
                a, b = comps_in_group[i], comps_in_group[j]
                idx_a, idx_b = ref_to_idx[a], ref_to_idx[b]
                key = (min(idx_a, idx_b), max(idx_a, idx_b))
                if key in processed:
                    continue
                processed.add(key)

                a_nets = comp_nets.get(a, set())
                if not a_nets:
                    continue

                intra = a_nets & group_nets
                group_fraction = len(intra) / len(a_nets) if a_nets else 0.0

                w_base = 1.0
                w_boost = group_coherence_weight(w_base, group_fraction, alpha_coherence)
                delta = w_boost - w_base
                weights[key] = weights.get(key, 0.0) + delta


# -- U2.3: Critical Loop ------------------------------------------------------


def critical_loop_weight(
    w_base: float,
    max_area_mm2: float,
    i_rms: float = 1.0,
    f_switching: float = 1.0,
) -> float:
    """Compute critical loop edge weight.

    w_loop(i,j) = w_base * I_rms^2 * f_switching / max_area_mm2
    """
    if max_area_mm2 <= 0:
        return w_base
    return w_base * (i_rms**2) * f_switching / max_area_mm2


def _apply_critical_loop_weights(
    weights: dict[tuple[int, int], float],
    mapper: "ConstraintMapper",
    ref_to_idx: dict[str, int],
    placement_constraints: "PlacementConstraints | None",
) -> None:
    if not mapper.loop_components:
        return

    loop_meta: dict[str, tuple[float | None, float]] = {}
    if placement_constraints is not None:
        for cl in placement_constraints.critical_loops:
            loop_meta[cl.name] = (cl.max_area_mm2, cl.weight)

    for loop_name, comp_refs in mapper.loop_components.items():
        meta = loop_meta.get(loop_name)
        max_area = meta[0] if meta else None

        if max_area is None or max_area <= 0:
            logger.warning(
                "LoopAreaConstraint '%s': max_area_mm2 missing or zero, "
                "skipping weight derivation",
                loop_name,
            )
            continue

        idxs = [ref_to_idx[r] for r in comp_refs if r in ref_to_idx]
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                key = (min(idxs[i], idxs[j]), max(idxs[i], idxs[j]))
                w = critical_loop_weight(1.0, max_area, i_rms=1.0, f_switching=1.0)
                weights[key] = weights.get(key, 0.0) + w


# -- U2.4: HV/LV Repulsion ----------------------------------------------------


def hv_lv_repulsion_weight(
    clearance_mm: float,
    v_diff: float,
    c_iso: float = C_ISO,
    v_ref: float = _V_REF,
) -> float:
    """Compute HV/LV repulsion (negative) edge weight.

    w_repulsion(i,j) = -C_iso / clearance_mm^2 * (V_diff / V_ref)
    """
    if clearance_mm <= 0:
        return 0.0
    return -c_iso / (clearance_mm**2) * (v_diff / v_ref)


def _build_net_rules_map(
    netlist: "Netlist",
) -> "dict[str, object]":
    """Build net_name -> NetClassRules mapping from net class names."""
    from temper_placer.core.design_rules import TEMPER_NET_CLASSES

    result: dict[str, object] = {}
    for net in netlist.nets:
        rules = TEMPER_NET_CLASSES.get(net.net_class)
        if rules is not None and rules.safety_category:
            result[net.name] = rules
    return result


def _apply_hv_lv_repulsion_weights(
    weights: dict[tuple[int, int], float],
    netlist: "Netlist",
    ref_to_idx: dict[str, int],
    c_iso: float,
) -> None:
    net_rules = _build_net_rules_map(netlist)
    if not net_rules:
        return

    comp_nets: dict[str, set[str]] = {}
    for net in netlist.nets:
        for ref, _ in net.pins:
            comp_nets.setdefault(ref, set()).add(net.name)

    processed: set[tuple[int, int]] = set()
    for net in netlist.nets:
        rules = net_rules.get(net.name)
        if rules is None:
            continue
        comp_refs = [ref for ref, _ in net.pins if ref in ref_to_idx]
        for i in range(len(comp_refs)):
            for j in range(i + 1, len(comp_refs)):
                a, b = comp_refs[i], comp_refs[j]
                a_nets = comp_nets.get(a, set())
                b_nets = comp_nets.get(b, set())
                a_cats = {net_rules[n].safety_category for n in a_nets if n in net_rules}  # type: ignore[union-attr]
                b_cats = {net_rules[n].safety_category for n in b_nets if n in net_rules}  # type: ignore[union-attr]

                if not a_cats or not b_cats:
                    continue
                cross = a_cats - b_cats
                if not cross:
                    continue

                idx_a, idx_b = ref_to_idx[a], ref_to_idx[b]
                key = (min(idx_a, idx_b), max(idx_a, idx_b))
                if key in processed:
                    continue
                processed.add(key)

                all_rules: list = [net_rules[n] for n in (a_nets | b_nets) if n in net_rules]
                if not all_rules:
                    continue

                max_clearance = max(
                    max(float(r.clearance), float(r.creepage_mm))  # type: ignore[arg-type]
                    for r in all_rules
                )
                v_vals = [float(r.voltage_v) for r in all_rules]  # type: ignore[arg-type]
                v_max = max(v_vals, default=0.0)
                v_min = min(v_vals, default=0.0)
                v_diff = v_max - v_min if v_max > v_min else 1.0

                w = hv_lv_repulsion_weight(max_clearance, v_diff, c_iso)
                weights[key] = weights.get(key, 0.0) + w


# -- U2.5: Clearance (Generalized Net-Class Pair) ------------------------------


def clearance_weight(
    clearance_mm: float,
    c_iso: float = C_ISO,
    is_cross_domain: bool = True,
) -> float:
    """Compute clearance-based edge weight for net-class cross-product.

    Cross-domain pairs get -C_iso / clearance_mm^2.
    Same-domain pairs get no modification.
    """
    if not is_cross_domain or clearance_mm <= 0:
        return 0.0
    return -c_iso / (clearance_mm**2)


def _apply_clearance_weights(
    weights: dict[tuple[int, int], float],
    netlist: "Netlist",
    ref_to_idx: dict[str, int],
    c_iso: float,
) -> None:
    net_rules = _build_net_rules_map(netlist)
    if not net_rules:
        return

    processed: set[tuple[int, int]] = set()
    for net in netlist.nets:
        rules = net_rules.get(net.name)
        if rules is None:
            continue
        comp_refs = [ref for ref, _ in net.pins if ref in ref_to_idx]
        for i in range(len(comp_refs)):
            for j in range(i + 1, len(comp_refs)):
                a, b = comp_refs[i], comp_refs[j]
                idx_a, idx_b = ref_to_idx[a], ref_to_idx[b]
                key = (min(idx_a, idx_b), max(idx_a, idx_b))
                if key in processed:
                    continue

                a_nets = set(netlist.get_component_nets(a))
                b_nets = set(netlist.get_component_nets(b))
                a_cats = {net_rules[n].safety_category for n in a_nets if n in net_rules}  # type: ignore[union-attr]
                b_cats = {net_rules[n].safety_category for n in b_nets if n in net_rules}  # type: ignore[union-attr]

                is_cross = bool(a_cats - b_cats) or bool(b_cats - a_cats)
                if not is_cross or not a_cats or not b_cats:
                    continue

                processed.add(key)

                all_rules: list = [net_rules[n] for n in (a_nets | b_nets) if n in net_rules]
                if not all_rules:
                    continue

                max_clearance = max(
                    max(float(r.clearance), float(r.creepage_mm))  # type: ignore[arg-type]
                    for r in all_rules
                )
                w = clearance_weight(max_clearance, c_iso, is_cross_domain=True)
                weights[key] = weights.get(key, 0.0) + w


# =============================================================================
# U2: compute_constraint_weight_dict entry point
# =============================================================================


def compute_constraint_weight_dict(
    mapper: "ConstraintMapper",
    placement_constraints: "PlacementConstraints | None",
    netlist: "Netlist",
    pcl_collection: "ConstraintCollection | None",
    strategies: dict[str, bool] | None = None,
    calibration: dict[str, float] | None = None,
) -> dict[tuple[int, int], float]:
    """Compute per-edge constraint weight contributions from enabled strategies.

    Args:
        mapper: Precomputed constraint-to-net mapping.
        placement_constraints: PlacementConstraints with component_groups etc.
        netlist: Netlist with component and net data.
        pcl_collection: PCL constraint collection for proximity.
        strategies: Dict of strategy_name -> bool enabling/disabling.
        calibration: Dict of calibration constant overrides.

    Returns:
        dict[(comp_idx_i, comp_idx_j), weight] for all component pairs
        that receive non-zero constraint-derived contributions.
    """
    if strategies is None:
        strategies = {
            "proximity": True,
            "group_coherence": True,
            "critical_loop": True,
            "hv_lv_repulsion": False,
            "clearance": False,
        }
    if calibration is None:
        calibration = {}

    k_hard = calibration.get("k_HARD", K_HARD)
    k_strong = calibration.get("k_STRONG", K_STRONG)
    k_soft = calibration.get("k_SOFT", K_SOFT)
    c_iso = calibration.get("C_iso", C_ISO)
    alpha_coherence = calibration.get("alpha_coherence", ALPHA_COHERENCE)

    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
    weights: dict[tuple[int, int], float] = {}

    # U2.1: Proximity
    if strategies.get("proximity", True):
        _apply_proximity_weights(
            weights, ref_to_idx, k_hard, k_strong, k_soft, pcl_collection
        )

    # U2.2: Group Coherence
    if strategies.get("group_coherence", True) and placement_constraints is not None:
        _apply_group_coherence_weights(
            weights, netlist, placement_constraints, ref_to_idx, alpha_coherence
        )

    # U2.3: Critical Loop
    if strategies.get("critical_loop", True):
        _apply_critical_loop_weights(
            weights, mapper, ref_to_idx, placement_constraints
        )

    # U2.4: HV/LV Repulsion
    if strategies.get("hv_lv_repulsion", False):
        _apply_hv_lv_repulsion_weights(weights, netlist, ref_to_idx, c_iso)

    # U2.5: Clearance
    if strategies.get("clearance", False):
        _apply_clearance_weights(weights, netlist, ref_to_idx, c_iso)

    return weights


# =============================================================================
# U3: PSD Stabilization
# =============================================================================


def compute_gershgorin_lambda_min_bound(
    laplacian: "np.ndarray",
) -> float:
    """Compute Gershgorin lower bound on minimum eigenvalue.

    For each row i of Laplacian L:
        center_i = L[i,i]
        radius_i = sum(|L[i,j]| for j != i)
        lambda_min_bound = min_i(center_i - radius_i)

    This is O(n^2) and requires no eigendecomposition.
    """
    import numpy as np

    n = laplacian.shape[0]
    if n <= 1:
        return 0.0

    min_bound = float("inf")
    for i in range(n):
        center = laplacian[i, i]
        radius = float(np.sum(np.abs(laplacian[i, :]))) - abs(center)
        bound = center - radius
        min_bound = min(min_bound, bound)

    return float(min_bound)


def apply_psd_shift(
    laplacian: "np.ndarray",
    adjacency: "np.ndarray | None" = None,
    max_shift_ratio: float = PSD_SHIFT_MAX_RATIO,
) -> "tuple[np.ndarray, float, bool]":
    """Apply PSD stabilization via Gershgorin circle theorem.

    Args:
        laplacian: Normalized Laplacian (N, N).
        adjacency: Optional adjacency for fallback (attraction-only).
        max_shift_ratio: Max allowed shift as fraction of spectral radius.

    Returns:
        (L_stable, shift_amount, was_overdamped)
    """
    import numpy as np

    n = laplacian.shape[0]
    if n <= 1:
        return laplacian, 0.0, False

    bound = compute_gershgorin_lambda_min_bound(laplacian)

    if bound >= -1e-6:
        return laplacian, 0.0, False

    shift = abs(bound)

    # Estimate spectral radius via Gershgorin
    max_upper = float(-np.inf)
    for i in range(n):
        center = laplacian[i, i]
        radius = float(np.sum(np.abs(laplacian[i, :]))) - abs(center)
        max_upper = max(max_upper, center + radius)
    spectral_radius = max_upper if max_upper > 0 else 1.0

    if shift > max_shift_ratio * spectral_radius:
        logger.warning(
            "PSD shift %.2f exceeds %.0f%% of spectral radius (%.2f). "
            "Falling back to attraction-only Laplacian.",
            shift,
            max_shift_ratio * 100,
            spectral_radius,
        )
        if adjacency is not None:
            adj_pos = np.maximum(adjacency, 0.0)
            degrees = np.sum(adj_pos, axis=1)
            d_inv_sqrt = np.where(
                degrees > 0, 1.0 / np.sqrt(degrees + 1e-10), 0.0
            )
            D_inv_sqrt = np.diag(d_inv_sqrt)
            L_stable = np.eye(n) - D_inv_sqrt @ adj_pos @ D_inv_sqrt
            return L_stable, shift, True
        return laplacian, shift, True

    L_stable = laplacian + shift * np.eye(n)
    return L_stable, shift, False


# =============================================================================
# Laplacian construction from weighted adjacency
# =============================================================================


def compute_laplacian_from_weights(
    netlist: "Netlist",
    constraint_weights: dict[tuple[int, int], float] | None = None,
    normalized: bool = True,
) -> "tuple[np.ndarray, np.ndarray]":
    """Build Laplacian from netlist connectivity with optional constraint weights.

    Edge weight: w_ij = w_base_net * (1/(k-1)) + constraint_weight.get((i,j), 0)

    Args:
        netlist: Netlist with components and nets.
        constraint_weights: Optional per-edge constraint weight contributions.
        normalized: If True, return normalized Laplacian.

    Returns:
        (adjacency, laplacian) as numpy arrays.
    """
    import numpy as np

    n = len(netlist.components)
    if n == 0:
        return np.zeros((0, 0)), np.zeros((0, 0))

    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
    adj = np.zeros((n, n), dtype=np.float64)

    for net in netlist.nets:
        comp_indices = []
        for ref, _ in net.pins:
            if ref in ref_to_idx:
                comp_indices.append(ref_to_idx[ref])
        comp_indices = list(set(comp_indices))
        k = len(comp_indices)
        if k < 2:
            continue
        w_base = 1.0 / (k - 1)
        for i in range(k):
            for j in range(i + 1, k):
                u, v = comp_indices[i], comp_indices[j]
                adj[u, v] += w_base
                adj[v, u] += w_base

    if constraint_weights:
        for (i, j), w in constraint_weights.items():
            if 0 <= i < n and 0 <= j < n:
                adj[i, j] += w
                adj[j, i] += w

    if normalized:
        degrees = np.sum(adj, axis=1)
        safe_degrees = np.maximum(degrees, 1e-10)
        d_inv_sqrt = np.where(
            degrees > 0, 1.0 / np.sqrt(safe_degrees), 0.0
        )
        D_inv_sqrt = np.diag(d_inv_sqrt)
        L = np.eye(n) - D_inv_sqrt @ adj @ D_inv_sqrt
    else:
        degrees = np.sum(adj, axis=1)
        D = np.diag(degrees)
        L = D - adj

    return adj, L
