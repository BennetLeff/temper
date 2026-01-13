"""
Base classes and interfaces for loss functions.

This module defines the core abstractions for loss functions in temper-placer:
- LossFunction: Abstract base class for individual loss functions
- LossContext: Immutable context passed to all loss functions
- LossResult: Return type with value and optional breakdown
- CompositeLoss: Aggregates multiple weighted loss functions

All loss functions must be JAX-compatible (work with jit, grad, vmap).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import (
    Netlist,
    build_adjacency_matrix,
    compute_eigenvector_centrality,
)
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.losses.types import (
    ClearanceRule,
    CriticalPathConstraint,
    LoopConstraint,
    LossResult,
    MatchedLengthConstraint,
    MountingRule,
    NoiseIsolationConstraint,
    StarGroundConstraint,
    ThermalConstraint,
)
from temper_placer.losses.types import (
    GeometryContext,
    NetlistContext,
    ConstraintContext,
    LossContext as BaseLossContext,
)


@dataclass(frozen=True)
class LossContext(BaseLossContext):
    """
    Immutable context containing all data needed by loss functions.

    Extends BaseLossContext with factory methods.
    """

    @classmethod
    def from_netlist_and_board(
        cls,
        netlist: Netlist,
        board: Board,
        constraints: PlacementConstraints | None = None,
        clearance_rules: list[ClearanceRule] | None = None,
        thermal_constraints: list[ThermalConstraint] | None = None,
        star_ground_constraints: list[StarGroundConstraint] | None = None,
        loop_constraints: list[LoopConstraint] | None = None,
        mounting_rules: list[MountingRule] | None = None,
        path_constraints: list[CriticalPathConstraint] | None = None,
        matched_groups: list[MatchedLengthConstraint] | None = None,
        spatial_penalties: Array | None = None,
        use_centrality_weighting: bool = False,
    ) -> LossContext:
        """
        Create a LossContext from netlist and board with automatic index computation.

        Args:
            netlist: The netlist to use.
            board: The board definition.
            constraints: Optional placement constraints.
            clearance_rules: Optional list of clearance rules.
            thermal_constraints: Optional list of thermal constraints.
            loop_constraints: Optional list of loop constraints.
            mounting_rules: Optional list of mounting rules.
            path_constraints: Optional list of critical path constraints.
            matched_groups: Optional list of matched length constraints.
            spatial_penalties: Optional (K, 3) array of routing failure hotspots.
            use_centrality_weighting: If True, scale weights and step sizes
                by component centrality (hub prioritization).

        Returns:
            A new LossContext with pre-computed arrays.

        Raises:
            ValueError: If constraint references invalid components or pins.
        """
        bounds = netlist.get_bounds_array()
        fixed_mask = netlist.get_fixed_mask()

        # Build net class map from components
        net_class_map = {c.ref: c.net_class for c in netlist.components}

        # Compute HV and LV indices
        hv_indices = []
        lv_indices = []
        net_class_indices_dict: dict[str, list[int]] = {}

        for i, comp in enumerate(netlist.components):
            if comp.net_class == "HighVoltage":
                hv_indices.append(i)
            elif comp.net_class in ("Signal", "LowVoltage"):
                lv_indices.append(i)

            if comp.net_class not in net_class_indices_dict:
                net_class_indices_dict[comp.net_class] = []
            net_class_indices_dict[comp.net_class].append(i)

        # Identify fiducials
        fiducial_indices_list = []
        # Identify component types
        comp_type_map: dict[str, list[int]] = {}
        import re

        for i, comp in enumerate(netlist.components):
            if comp.ref.startswith("FID"):
                fiducial_indices_list.append(i)

            # Component type (first letter or prefix)
            match = re.match(r"^([A-Za-z]+)", comp.ref)
            if match:
                prefix = match.group(1)
                if prefix not in comp_type_map:
                    comp_type_map[prefix] = []
                comp_type_map[prefix].append(i)

        # Convert indices to JAX arrays
        fiducial_indices = jnp.array(fiducial_indices_list, dtype=jnp.int32)
        component_type_indices = {
            t: jnp.array(idxs, dtype=jnp.int32)
            for t, idxs in comp_type_map.items()
        }

        # Convert net class indices to JAX arrays
        net_class_indices = {
            nc: jnp.array(indices, dtype=jnp.int32)
            for nc, indices in net_class_indices_dict.items()
        }

        # Compute centrality (if enabled or needed for weighting)
        if use_centrality_weighting:
            adjacency = build_adjacency_matrix(netlist)
            centrality = compute_eigenvector_centrality(adjacency)
        else:
            centrality = jnp.ones(netlist.n_components) / max(netlist.n_components, 1)

        # Pre-compute net pin arrays for JAX-compatible wirelength
        net_pin_indices, net_pin_offsets, net_pin_mask, net_weights, net_layer_counts, max_pins = (
            cls._precompute_net_arrays(netlist, board, centrality if use_centrality_weighting else None)
        )

        # Pre-compute loop constraint arrays
        loop_constraints = loop_constraints or []
        loop_pin_indices, loop_pin_offsets, loop_pin_mask, loop_max_areas, loop_weights = (
            cls._precompute_loop_arrays(
                netlist, loop_constraints, centrality if use_centrality_weighting else None
            )
        )

        # Pre-compute critical path arrays
        path_constraints = path_constraints or []
        matched_groups = matched_groups or []
        noise_isolation_constraints = []

        # If constraints object provided, extract critical paths
        if constraints:
            for pc in constraints.critical_paths:
                # ... existing pc logic ...
                from_pin = (pc.from_comp, pc.pins[0]) if pc.pins else (pc.from_comp, "1")
                to_pin = (pc.to_comp, pc.pins[1]) if pc.pins else (pc.to_comp, "1")

                weight_map = {"critical": 10.0, "high": 5.0, "normal": 1.0}
                weight = weight_map.get(pc.priority, 1.0)

                path_constraints.append(CriticalPathConstraint(
                    name=pc.name,
                    from_pin=from_pin,
                    to_pin=to_pin,
                    max_length=pc.max_length_mm,
                    weight=weight,
                    matched_group=pc.matched_length_group,
                    because=pc.name  # Use name as a fallback for because
                ))

            # Map matched length groups
            for mlg in constraints.matched_length_groups:
                # ... existing mlg logic ...
                p_indices = [
                    i for i, p in enumerate(path_constraints)
                    if p.matched_group == mlg.name
                ]
                if p_indices:
                    matched_groups.append(MatchedLengthConstraint(
                        name=mlg.name,
                        path_indices=tuple(p_indices),
                        tolerance=mlg.tolerance_mm,
                        weight=1.0 # Default
                    ))

            # Map noise isolation rules
            import fnmatch
            all_refs = [c.ref for c in netlist.components]

            for rule in constraints.noise_isolation:
                # Expand globs for sensitive components
                sensitive = []
                for pattern in rule.sensitive_components:
                    matches = fnmatch.filter(all_refs, pattern)
                    sensitive.extend([netlist.get_component_index(m) for m in matches])

                # Expand globs for noise sources
                sources = []
                for pattern in rule.noise_sources:
                    matches = fnmatch.filter(all_refs, pattern)
                    sources.extend([netlist.get_component_index(m) for m in matches])

                if sensitive and sources:
                    noise_isolation_constraints.append(NoiseIsolationConstraint(
                        name=rule.name,
                        sensitive_indices=tuple(sorted(set(sensitive))),
                        noise_source_indices=tuple(sorted(set(sources))),
                        min_distance=rule.min_distance_mm,
                        weight=rule.weight,
                        because=rule.name
                    ))

            # Map star grounds
            for sg_cfg in constraints.star_grounds:
                star_ground_constraints = star_ground_constraints or []
                star_ground_constraints.append(StarGroundConstraint(
                    net_name=sg_cfg.net,
                    weight=sg_cfg.weight,
                    anchor_position=sg_cfg.anchor,
                    because=sg_cfg.description or f"Star ground for net {sg_cfg.net}"
                ))

            # Map critical loops (PowerSynth: key for switching noise minimization)
            for loop_cfg in constraints.critical_loops:
                loop_constraints = loop_constraints or []
                
                # Convert list of lists to tuple of tuples for JAX compatibility
                if loop_cfg.pins:
                    pins = tuple(tuple(p) for p in loop_cfg.pins)
                else:
                    # Fallback to nets if pins not specified (less precise)
                    # LoopAreaLoss requires pins, so we might need discovery logic here
                    # For now, we assume pins are provided for PowerSynth strategy
                    continue
                
                loop_constraints.append(LoopConstraint(
                    name=loop_cfg.name,
                    pins=pins,
                    max_area=loop_cfg.max_area_mm2 or 100.0,
                    weight=loop_cfg.weight,
                    because=loop_cfg.description or f"EMI loop {loop_cfg.name}"
                ))

        path_pin_indices, path_pin_offsets, path_max_lengths, path_weights = (
            cls._precompute_path_arrays(
                netlist, path_constraints, centrality if use_centrality_weighting else None
            )
        )

        # Validate constraints reference valid components/pins
        validation_errors = cls._validate_constraints(
            netlist, thermal_constraints or [], loop_constraints, path_constraints
        )
        if validation_errors:
            raise ValueError("Invalid constraint references:\n" + "\n".join(validation_errors))

        # Pre-compute star ground constraints
        star_ground_constraints = star_ground_constraints or []
        star_net_indices, star_weights, star_anchor_pos, star_has_anchor = (
            cls._precompute_star_ground_arrays(netlist, star_ground_constraints)
        )

        # Pre-compute ground domain arrays
        domains = board.ground_domains
        if domains:
            domain_bounds = jnp.array([d.bounds for d in domains], dtype=jnp.float32)
            domain_star_points = jnp.array(
                [d.star_point if d.star_point else [0.0, 0.0] for d in domains],
                dtype=jnp.float32
            )
            domain_has_star = jnp.array([d.star_point is not None for d in domains], dtype=jnp.bool_)
        else:
            domain_bounds = jnp.zeros((0, 4), dtype=jnp.float32)
            domain_star_points = jnp.zeros((0, 2), dtype=jnp.float32)
            domain_has_star = jnp.zeros((0,), dtype=jnp.bool_)

        # 1. Create GeometryContext
        geometry_context = GeometryContext(
            bounds=bounds,
            fixed_mask=fixed_mask,
            origin=jnp.array(getattr(board, 'origin', (0.0, 0.0)), dtype=jnp.float32),
            width=float(board.width),
            height=float(board.height),
            board_margin=float(getattr(board, 'board_margin', 0.0))
        )

        # 2. Create NetlistContext
        netlist_context = NetlistContext(
            net_pin_indices=net_pin_indices,
            net_pin_offsets=net_pin_offsets,
            net_pin_mask=net_pin_mask,
            net_weights=net_weights,
            net_layer_counts=net_layer_counts,
            max_pins_per_net=max_pins,
            centrality=centrality,
            hv_indices=jnp.array(hv_indices, dtype=jnp.int32),
            lv_indices=jnp.array(lv_indices, dtype=jnp.int32),
            fiducial_indices=fiducial_indices
        )

        # 3. Create ConstraintContext
        is_star_net = jnp.array([
            n.name in [c.net_name for c in star_ground_constraints]
            for n in [net for net in netlist.nets if len(net.pins) >= 2]
        ], dtype=jnp.bool_)

        constraint_context = ConstraintContext(
            loop_pin_indices=loop_pin_indices,
            loop_pin_offsets=loop_pin_offsets,
            loop_pin_mask=loop_pin_mask,
            loop_max_areas=loop_max_areas,
            loop_weights=loop_weights,
            path_pin_indices=path_pin_indices,
            path_pin_offsets=path_pin_offsets,
            path_max_lengths=path_max_lengths,
            path_weights=path_weights,
            star_net_indices=star_net_indices,
            star_weights=star_weights,
            star_anchor_pos=star_anchor_pos,
            star_has_anchor=star_has_anchor,
            domain_bounds=domain_bounds,
            domain_star_points=domain_star_points,
            domain_has_star=domain_has_star,
            is_star_net=is_star_net,
            spatial_penalties=spatial_penalties,
        )

        # 4. Build PhysicsHypergraph
        # We use default settings for now (filtering global nets > 50 pins)
        hypergraph = netlist_to_hypergraph(
            netlist, 
            ignore_global_nets=True, 
            global_net_threshold=50
        )

        # 5. Build component name to index mapping
        component_name_to_index = {c.ref: i for i, c in enumerate(netlist.components)}

        # 6. Parse component spacing rules from constraints
        component_spacing_rules = []
        if constraints and hasattr(constraints, 'component_spacing_rules'):
            component_spacing_rules = constraints.component_spacing_rules

        return cls(
            netlist=netlist,
            board=board,
            bounds=geometry_context.bounds,
            fixed_mask=geometry_context.fixed_mask,
            geometry=geometry_context,
            netlist_data=netlist_context,
            constraints_data=constraint_context,
            hypergraph=hypergraph,
            constraints_config=constraints,
            thermal_constraints=thermal_constraints or [],
            loop_constraints=loop_constraints or [],
            matched_groups=matched_groups or [],
            clearance_rules=clearance_rules or [],
            star_ground_constraints=star_ground_constraints or [],
            component_spacing_rules=component_spacing_rules,
            component_type_indices=component_type_indices,
            net_class_indices=net_class_indices,
            component_name_to_index=component_name_to_index,
        )

    @staticmethod
    def _precompute_net_arrays(
        netlist: Netlist,
        board: Board,
        centrality: Array | None = None,
    ) -> tuple[Array, Array, Array, Array, Array, int]:
        """
        Pre-compute padded arrays for net pin positions.

        Returns:
            net_pin_indices: (M, P) component indices per net pin
            net_pin_offsets: (M, P, 2) pin offsets per net
            net_pin_mask: (M, P) valid pin mask
            net_weights: (M,) net weights
            max_pins: Maximum pins per net (P)
        """
        # Filter to nets with 2+ pins (required for HPWL)
        valid_nets = [n for n in netlist.nets if len(n.pins) >= 2]

        if not valid_nets:
            return (
                jnp.zeros((0, 0), dtype=jnp.int32),
                jnp.zeros((0, 0, 2), dtype=jnp.float32),
                jnp.zeros((0, 0), dtype=jnp.bool_),
                jnp.zeros((0,), dtype=jnp.float32),
                jnp.zeros((0,), dtype=jnp.int32),
                0,
            )

        max_pins = max(len(n.pins) for n in valid_nets)
        len(valid_nets)
        n_components = netlist.n_components

        # Initialize arrays
        indices = []
        offsets = []
        masks = []
        weights = []
        layer_counts = []

        for net in valid_nets:
            net_indices = []
            net_offsets = []
            net_mask = []

            # For centrality weighting
            net_comp_indices = []

            for comp_ref, pin_name in net.pins:
                comp_idx = netlist.get_component_index(comp_ref)
                comp = netlist.get_component(comp_ref)
                pin = comp.get_pin(pin_name)

                net_indices.append(comp_idx)
                net_comp_indices.append(comp_idx)
                if pin is not None:
                    net_offsets.append(list(pin.position))
                else:
                    net_offsets.append([0.0, 0.0])  # Default to center
                net_mask.append(True)

            # Pad to max_pins
            while len(net_indices) < max_pins:
                net_indices.append(0)  # Dummy index
                net_offsets.append([0.0, 0.0])
                net_mask.append(False)

            indices.append(net_indices)
            offsets.append(net_offsets)
            masks.append(net_mask)

            # Compute effective net weight
            weight = net.weight
            if centrality is not None and centrality.shape[0] > 0:
                # Boost net weight by max centrality of connected components
                # Scale by N to keep average weight consistent (avg centrality is 1/N)
                max_c = jnp.max(centrality[jnp.array(net_comp_indices)])
                weight = weight * (max_c * n_components)

            weights.append(weight)

            # Layer count for RHWL
            if board.layer_stackup:
                lc = len(board.layer_stackup.routable_layers(net.net_class or "Signal"))
            else:
                lc = 1
            layer_counts.append(lc)

        return (
            jnp.array(indices, dtype=jnp.int32),
            jnp.array(offsets, dtype=jnp.float32),
            jnp.array(masks, dtype=jnp.bool_),
            jnp.array(weights, dtype=jnp.float32),
            jnp.array(layer_counts, dtype=jnp.int32),
            max_pins,
        )

    @staticmethod
    def _precompute_loop_arrays(
        netlist: Netlist,
        loop_constraints: list[LoopConstraint],
        centrality: Array | None = None,
    ) -> tuple[Array, Array, Array, Array, Array]:
        """
        Pre-compute padded arrays for loop constraint pin positions.

        Returns:
            loop_pin_indices: (L, Q) component indices per loop
            loop_pin_offsets: (L, Q, 2) pin offsets per loop
            loop_pin_mask: (L, Q) valid pin mask
            loop_max_areas: (L,) max areas per loop
            loop_weights: (L,) weights per loop
        """
        if not loop_constraints:
            return (
                jnp.zeros((0, 0), dtype=jnp.int32),
                jnp.zeros((0, 0, 2), dtype=jnp.float32),
                jnp.zeros((0, 0), dtype=jnp.bool_),
                jnp.zeros((0,), dtype=jnp.float32),
                jnp.zeros((0,), dtype=jnp.float32),
            )

        max_pins = max(len(lc.pins) for lc in loop_constraints)
        n_components = netlist.n_components

        indices = []
        offsets = []
        masks = []
        max_areas = []
        weights = []

        for loop in loop_constraints:
            loop_indices = []
            loop_offsets = []
            loop_mask = []

            # For centrality weighting
            loop_comp_indices = []

            for comp_ref, pin_name in loop.pins:
                try:
                    comp_idx = netlist.get_component_index(comp_ref)
                    comp = netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)

                    loop_indices.append(comp_idx)
                    loop_comp_indices.append(comp_idx)
                    if pin is not None:
                        loop_offsets.append(list(pin.position))
                    else:
                        loop_offsets.append([0.0, 0.0])
                    loop_mask.append(True)
                except KeyError:
                    # Component not found - will be caught in validation
                    loop_indices.append(0)
                    loop_offsets.append([0.0, 0.0])
                    loop_mask.append(False)

            # Pad to max_pins
            while len(loop_indices) < max_pins:
                loop_indices.append(0)
                loop_offsets.append([0.0, 0.0])
                loop_mask.append(False)

            indices.append(loop_indices)
            offsets.append(loop_offsets)
            masks.append(loop_mask)
            max_areas.append(loop.max_area)

            # Compute effective loop weight
            weight = loop.weight
            if centrality is not None and centrality.shape[0] > 0 and loop_comp_indices:
                # Boost loop weight by max centrality of involved components
                max_c = jnp.max(centrality[jnp.array(loop_comp_indices)])
                weight = weight * (max_c * n_components)

            weights.append(weight)

        return (
            jnp.array(indices, dtype=jnp.int32),
            jnp.array(offsets, dtype=jnp.float32),
            jnp.array(masks, dtype=jnp.bool_),
            jnp.array(max_areas, dtype=jnp.float32),
            jnp.array(weights, dtype=jnp.float32),
        )

    @staticmethod
    def _precompute_path_arrays(
        netlist: Netlist,
        path_constraints: list[CriticalPathConstraint],
        centrality: Array | None = None,
    ) -> tuple[Array, Array, Array, Array]:
        """
        Pre-compute arrays for critical path constraints.

        Returns:
            path_pin_indices: (C, 2) component indices per path
            path_pin_offsets: (C, 2, 2) pin offsets per path
            path_max_lengths: (C,) max lengths per path
            path_weights: (C,) weights per path
        """
        if not path_constraints:
            return (
                jnp.zeros((0, 2), dtype=jnp.int32),
                jnp.zeros((0, 2, 2), dtype=jnp.float32),
                jnp.zeros((0,), dtype=jnp.float32),
                jnp.zeros((0,), dtype=jnp.float32),
            )

        indices = []
        offsets = []
        max_lengths = []
        weights = []

        n_components = netlist.n_components

        for path in path_constraints:
            try:
                # From pin
                from_ref, from_pin_name = path.from_pin
                from_idx = netlist.get_component_index(from_ref)
                from_comp = netlist.get_component(from_ref)
                from_pin = from_comp.get_pin(from_pin_name)
                from_offset = list(from_pin.position) if from_pin else [0.0, 0.0]

                # To pin
                to_ref, to_pin_name = path.to_pin
                to_idx = netlist.get_component_index(to_ref)
                to_comp = netlist.get_component(to_ref)
                to_pin = to_comp.get_pin(to_pin_name)
                to_offset = list(to_pin.position) if to_pin else [0.0, 0.0]

                indices.append([from_idx, to_idx])
                offsets.append([from_offset, to_offset])
                max_lengths.append(path.max_length)

                # Weight
                weight = path.weight
                if centrality is not None and centrality.shape[0] > 0:
                    max_c = jnp.max(centrality[jnp.array([from_idx, to_idx])])
                    weight = weight * (max_c * n_components)
                weights.append(weight)

            except KeyError:
                # Component not found - will be caught in validation
                indices.append([0, 0])
                offsets.append([[0.0, 0.0], [0.0, 0.0]])
                max_lengths.append(path.max_length)
                weights.append(0.0)

        return (
            jnp.array(indices, dtype=jnp.int32),
            jnp.array(offsets, dtype=jnp.float32),
            jnp.array(max_lengths, dtype=jnp.float32),
            jnp.array(weights, dtype=jnp.float32),
        )

    @staticmethod
    def _validate_constraints(
        netlist: Netlist,
        thermal_constraints: list[ThermalConstraint],
        loop_constraints: list[LoopConstraint],
        path_constraints: list[CriticalPathConstraint],
    ) -> list[str]:
        """
        Validate that all constraint references are valid.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []
        valid_refs = {c.ref for c in netlist.components}

        # Validate thermal constraints
        for tc in thermal_constraints:
            if tc.component_ref not in valid_refs:
                errors.append(f"ThermalConstraint references unknown component: {tc.component_ref}")

        # Validate loop constraints
        for lc in loop_constraints:
            for comp_ref, pin_name in lc.pins:
                if comp_ref not in valid_refs:
                    errors.append(
                        f"LoopConstraint '{lc.name}' references unknown component: {comp_ref}"
                    )
                else:
                    comp = netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)
                    if pin is None:
                        # Warn but don't fail - will use component center
                        pass

        # Validate path constraints
        for pc in path_constraints:
            for comp_ref, pin_name in [pc.from_pin, pc.to_pin]:
                if comp_ref not in valid_refs:
                    errors.append(
                        f"CriticalPathConstraint '{pc.name}' references unknown component: {comp_ref}"
                    )
                else:
                    comp = netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)
                    if pin is None:
                        # Warn but don't fail
                        pass

        return errors

    @staticmethod
    def _precompute_star_ground_arrays(
        netlist: Netlist,
        constraints: list[StarGroundConstraint],
    ) -> tuple[Array, Array, Array, Array]:
        """
        Pre-compute arrays for star ground constraints.

        Returns:
            star_net_indices: (S,) net indices
            star_weights: (S,) weights
            star_anchor_pos: (S, 2) anchor positions
            star_has_anchor: (S,) boolean mask
        """
        if not constraints:
            return (
                jnp.zeros((0,), dtype=jnp.int32),
                jnp.zeros((0,), dtype=jnp.float32),
                jnp.zeros((0, 2), dtype=jnp.float32),
                jnp.zeros((0,), dtype=jnp.bool_),
            )

        indices = []
        weights = []
        anchors = []
        has_anchors = []

        # Build net name map for fast lookup
        net_map = {n.name: i for i, n in enumerate(netlist.nets)}

        for sc in constraints:
            if sc.net_name not in net_map:
                # Skip invalid nets (would be caught by validation ideally)
                continue

            indices.append(net_map[sc.net_name])
            weights.append(sc.weight)

            if sc.anchor_position is not None:
                anchors.append(list(sc.anchor_position))
                has_anchors.append(True)
            else:
                anchors.append([0.0, 0.0])
                has_anchors.append(False)

        return (
            jnp.array(indices, dtype=jnp.int32),
            jnp.array(weights, dtype=jnp.float32),
            jnp.array(anchors, dtype=jnp.float32),
            jnp.array(has_anchors, dtype=jnp.bool_),
        )

    def get_component_index(self, ref: str) -> int:
        """Get array index for a component by reference."""
        return self.netlist.get_component_index(ref)


class LossFunction(ABC):
    """
    Abstract base class for loss functions.

    All loss functions must inherit from this class and implement:
    - name property: A unique identifier for the loss
    - __call__: Compute the loss given positions, rotations, and context

    Loss functions should be stateless and JAX-compatible. Any configuration
    should be passed in __init__ and stored as instance attributes.

    Example:
        >>> class MyLoss(LossFunction):
        ...     @property
        ...     def name(self) -> str:
        ...         return "my_loss"
        ...
        ...         value = jnp.sum(positions ** 2)
        ...         return LossResult(value=value)
    """
    @property
    def supports_virtual_nodes(self) -> bool:
        """Whether this loss function accepts net_virtual_nodes as an argument."""
        return False


    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this loss function."""
        ...

    @abstractmethod
    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute the loss value.

        Args:
            positions: (N, 2) array of component center positions in mm.
            rotations: (N, 4) soft one-hot rotation indicators from Gumbel-Softmax.
            context: LossContext with netlist, board, and constraints.
            net_virtual_nodes: Optional (M, 2) array of net virtual nodes.

        Returns:
            LossResult with scalar loss value and optional breakdown.
        """
        ...

    def weight_schedule(self, _epoch: int, _total_epochs: int) -> float:
        """
        Get the weight multiplier for this loss at a given epoch.

        Override this method to implement curriculum learning. The default
        implementation returns 1.0 (constant weight).

        Args:
            epoch: Current training epoch (0-indexed).
            total_epochs: Total number of training epochs.

        Returns:
            Weight multiplier for this loss (typically 0.0 to 1.0).
        """
        return 1.0


def smooth_step(x: Array, edge0: float = 0.0, edge1: float = 1.0) -> Array:
    """
    Smooth step function (Hermite interpolation) for curriculum learning.

    Returns 0 for x <= edge0, 1 for x >= edge1, and smoothly interpolates
    between using 3x² - 2x³.

    Args:
        x: Input value (typically epoch / total_epochs).
        edge0: Lower edge (returns 0).
        edge1: Upper edge (returns 1).

    Returns:
        Smoothly interpolated value in [0, 1].
    """
    t = jnp.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass
class WeightedLoss:
    """
    A loss function with its base weight, optional schedule, and normalization.

    Attributes:
        loss_fn: The loss function instance.
        weight: Base weight multiplier.
        schedule_start: Epoch fraction when this loss starts ramping up (0.0-1.0).
        schedule_end: Epoch fraction when this loss reaches full weight.
        normalize_by: Normalization mode:
            - None: No normalization (raw loss value)
            - "components": Divide by number of components
            - "pairs": Divide by number of component pairs (N*(N-1)/2)
            - "board_area": Divide by board area (mm²)
            - "nets": Divide by number of nets (for wirelength)
            - float: Divide by a custom constant
    """

    loss_fn: LossFunction
    weight: float = 1.0
    schedule_start: float = 0.0  # Start at epoch 0
    schedule_end: float = 0.0  # Full weight from epoch 0
    normalize_by: str | float | None = None

    def get_weight(self, epoch: int, total_epochs: int) -> float:
        """Get effective weight at given epoch."""
        # Apply schedule from loss function
        fn_weight = self.loss_fn.weight_schedule(epoch, total_epochs)

        # Apply curriculum schedule
        if self.schedule_end > self.schedule_start:
            progress = jnp.array(epoch / max(total_epochs, 1))
            curriculum = smooth_step(progress, self.schedule_start, self.schedule_end)
        else:
            curriculum = 1.0

        return self.weight * fn_weight * curriculum

    def get_normalizer(self, context: LossContext) -> float:
        """
        Get the normalization factor for this loss.

        Args:
            context: LossContext with component/board info.

        Returns:
            Normalization divisor (1.0 if no normalization).
        """
        if self.normalize_by is None:
            return 1.0

        if isinstance(self.normalize_by, (int, float)):
            return float(self.normalize_by)

        n = context.netlist.n_components

        if self.normalize_by == "components":
            return max(n, 1.0)
        elif self.normalize_by == "pairs":
            return max(n * (n - 1) / 2, 1.0)
        elif self.normalize_by == "board_area":
            return max(context.board.width * context.board.height, 1.0)
        elif self.normalize_by == "nets":
            return max(context.netlist.n_nets, 1.0)
        else:
            return 1.0  # Unknown mode, no normalization


class CompositeLoss(LossFunction):
    """
    Aggregates multiple weighted loss functions.

    This is the main loss function used during optimization. It combines
    multiple individual loss functions with weights and supports curriculum
    learning through weight scheduling.

    Supports optional normalization to make loss values more comparable
    across different board sizes and component counts. Use the `normalize_by`
    parameter in WeightedLoss for per-loss normalization.

    Example:
        >>> composite = CompositeLoss([
        ...     WeightedLoss(OverlapLoss(), weight=100.0, normalize_by="pairs"),
        ...     WeightedLoss(WirelengthLoss(), weight=1.0, normalize_by="nets"),
        ...     WeightedLoss(ClearanceLoss(), weight=50.0, schedule_start=0.2),
        ... ])
        >>> result = composite(positions, rotations, context, epoch=500, total_epochs=1000)
    """

    def __init__(self, losses: list[WeightedLoss]):
        """
        Initialize with list of weighted losses.

        Args:
            losses: List of WeightedLoss instances to aggregate.
        """
        self.losses = losses

    @property
    def name(self) -> str:
        """Name of the composite loss."""
        return "composite"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        weight_overrides: Array | None = None,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute total loss as weighted sum of individual losses.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext with all data.
            epoch: Current epoch for weight scheduling.
            total_epochs: Total epochs for weight scheduling.
            weight_overrides: Optional (L,) array of weights to use instead of base weights.
            net_virtual_nodes: Optional (M, 2) net virtual nodes.

        Returns:
            LossResult with total value and breakdown by loss name.
        """
        total = jnp.array(0.0)
        breakdown: dict[str, Array] = {}

        for i, wloss in enumerate(self.losses):
            if weight_overrides is not None:
                weight = weight_overrides[i]
            else:
                weight = wloss.get_weight(epoch, total_epochs)

            # Conditionally pass net_virtual_nodes if the loss function supports it
            if wloss.loss_fn.supports_virtual_nodes:
                result = wloss.loss_fn(
                    positions,
                    rotations,
                    context,
                    epoch,
                    total_epochs,
                    net_virtual_nodes=net_virtual_nodes
                )
            else:
                result = wloss.loss_fn(
                    positions,
                    rotations,
                    context,
                    epoch,
                    total_epochs
                )

            # Apply normalization
            normalizer = wloss.get_normalizer(context)
            normalized_value = result.value / normalizer

            # NaN/Inf guard: prevent one loss from poisoning the entire sum
            normalized_value = jnp.nan_to_num(normalized_value, nan=1e6, posinf=1e6, neginf=1e6)

            weighted_value = weight * normalized_value
            total = total + weighted_value

            # Store both raw and normalized values in breakdown
            breakdown[wloss.loss_fn.name] = result.value
            breakdown[f"{wloss.loss_fn.name}_normalized"] = normalized_value
            breakdown[f"{wloss.loss_fn.name}_weighted"] = weighted_value

            # Merge sub-breakdowns (e.g., per-component metrics)
            if result.breakdown:
                for sub_key, sub_val in result.breakdown.items():
                    breakdown[f"{wloss.loss_fn.name}_{sub_key}"] = sub_val

        return LossResult(value=total, breakdown=breakdown)

    def trace(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> tuple[Array, Trace]:
        """
        Evaluate all losses and collect a natural language trace.
        
        This is a non-differentiable method intended for use after optimization
        to generate an explanation of the final result.
        
        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft rotations.
            context: LossContext with PCL constraints.
            epoch: Final epoch.
            total_epochs: Total epochs.
            net_virtual_nodes: Optional (M, 2) virtual nodes.
            
        Returns:
            (total_loss, combined_trace)
        """
        from temper_placer.explainability.trace import Trace
        from temper_placer.explainability.traced_loss import TracedLossContext

        with TracedLossContext() as ctx:
            for wloss in self.losses:
                weight = wloss.get_weight(epoch, total_epochs)

                # Evaluate sub-loss with tracing if supported
                if hasattr(wloss.loss_fn, "trace"):
                    if wloss.loss_fn.supports_virtual_nodes:
                        val, sub_trace = wloss.loss_fn.trace(
                            positions, rotations, context, epoch, total_epochs, net_virtual_nodes
                        )
                    else:
                        val, sub_trace = wloss.loss_fn.trace(
                            positions, rotations, context, epoch, total_epochs
                        )
                else:
                    # Fallback: standard call
                    if wloss.loss_fn.supports_virtual_nodes:
                        result = wloss.loss_fn(
                            positions, rotations, context, epoch, total_epochs, net_virtual_nodes
                        )
                    else:
                        result = wloss.loss_fn(
                            positions, rotations, context, epoch, total_epochs
                        )
                    val = result.value
                    sub_trace = Trace.empty().add(
                        wloss.loss_fn.name,
                        float(val),
                        f"Weighted component of {wloss.loss_fn.name} loss"
                    )

                # Apply normalization and weight to the value
                normalizer = wloss.get_normalizer(context)
                weighted_val = weight * (val / normalizer)

                # Add to context (ctx.add handles the aggregation)
                ctx.add(weighted_val, sub_trace)

        total_loss, combined_trace = ctx.result()
        return total_loss, combined_trace

    def get_loss_fn(self, name: str) -> LossFunction | None:
        """Get a loss function by name."""
        for wloss in self.losses:
            if wloss.loss_fn.name == name:
                return wloss.loss_fn
        return None

    @property
    def loss_names(self) -> list[str]:
        """Get names of all loss functions."""
        return [wloss.loss_fn.name for wloss in self.losses]

    def record_timings(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        net_virtual_nodes: Array | None = None,
    ) -> dict[str, float]:
        """
        Record wall-clock execution time for each sub-loss.
        
        Note: This executes sub-losses synchronously with block_until_ready()
        to ensure accurate timing for JAX async dispatch.
        """
        import time
        timings = {}

        for weighted in self.losses:
            name = weighted.loss_fn.name
            start = time.perf_counter()
            # We call the loss function directly to avoid the overhead of CompositeLoss logic
            res = weighted.loss_fn(
                positions,
                rotations,
                context,
                net_virtual_nodes=net_virtual_nodes
            )
            # Explicitly block to wait for JAX async dispatch
            res.value.block_until_ready()
            end = time.perf_counter()
            timings[name] = (end - start) * 1000.0 # ms

        return timings


def create_jit_loss_fn(composite: CompositeLoss, context: LossContext):
    """
    Create a JIT-compiled loss function for optimization.

    This returns a function that takes only (positions, rotations, key)
    and is suitable for use with JAX optimizers.

    Args:
        composite: The CompositeLoss to compile.
        context: The LossContext (captured in closure).

    Returns:
        JIT-compiled function: (positions, rotations, epoch, total_epochs, weight_overrides) -> scalar
    """

    @jax.jit
    def loss_fn(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> Array:
        result = composite(positions, rotations, context, epoch, total_epochs, weight_overrides)
        return result.value

    return loss_fn


def create_value_and_grad_fn(
    composite: CompositeLoss,
    context: LossContext,
    apply_fixed_mask: bool = True,
):
    """
    Create a JIT-compiled function that returns both loss and gradients.

    This is the main function used in the optimization loop.

    Fixed components (connectors, mounting holes, etc.) will have their
    gradients zeroed out if apply_fixed_mask is True.

    Args:
        composite: The CompositeLoss to compile.
        context: The LossContext (captured in closure).
        apply_fixed_mask: If True, zero gradients for fixed components.

    Returns:
        JIT-compiled function: (positions, rotations, epoch, total_epochs, weight_overrides) -> (loss, (grad_pos, grad_rot))
    """
    fixed_mask = context.fixed_mask  # (N,) boolean array

    def loss_fn(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> Array:
        result = composite(positions, rotations, context, epoch, total_epochs, weight_overrides)
        return result.value

    def value_and_grad_fn(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> tuple[Array, tuple[Array, Array]]:
        # Compute gradients w.r.t. both positions and rotations
        (loss, (grad_pos, grad_rot)) = jax.value_and_grad(loss_fn, argnums=(0, 1))(
            positions, rotations, epoch, total_epochs, weight_overrides
        )

        # Ensure types for mypy
        loss = jax.lax.stop_gradient(loss)  # Just to ensure it's an Array

        # Zero out gradients for fixed components
        if apply_fixed_mask:
            # fixed_mask is (N,), expand to (N, 2) for positions and (N, 4) for rotations
            grad_pos = jnp.where(fixed_mask[:, None], 0.0, grad_pos)
            grad_rot = jnp.where(fixed_mask[:, None], 0.0, grad_rot)

        return loss, (cast(Array, grad_pos), cast(Array, grad_rot))

    return jax.jit(value_and_grad_fn)


def create_value_and_grad_fn_with_breakdown(
    composite: CompositeLoss,
    context: LossContext,
    apply_fixed_mask: bool = True,
):
    """
    Create a JIT-compiled function that returns loss, breakdown, and gradients.

    This version returns the loss breakdown alongside the gradients, avoiding
    the need to recompute the loss for logging purposes.

    Args:
        composite: The CompositeLoss to compile.
        context: The LossContext (captured in closure).
        apply_fixed_mask: If True, zero gradients for fixed components.

    Returns:
        JIT-compiled function: (positions, rotations, net_virtual_nodes, epoch, total_epochs, weight_overrides) ->
            ((loss, breakdown_dict), (grad_pos, grad_rot, grad_vn))

        The breakdown_dict maps loss term names to their values.
    """
    fixed_mask = context.fixed_mask  # (N,) boolean array

    def loss_fn_with_aux(
        positions: Array,
        rotations: Array,
        net_virtual_nodes: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> tuple[Array, dict[str, Array]]:
        result = composite(
            positions,
            rotations,
            context,
            epoch,
            total_epochs,
            weight_overrides,
            net_virtual_nodes
        )
        # Convert breakdown to dict of arrays for JIT compatibility
        breakdown = result.breakdown or {}
        return result.value, breakdown

    def value_and_grad_fn(
        positions: Array,
        rotations: Array,
        net_virtual_nodes: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> tuple[tuple[Array, dict[str, Array]], tuple[Array, Array, Array]]:
        # Compute gradients w.r.t. both positions, rotations and virtual nodes (indices 0, 1, 2)
        # has_aux=True means the function returns (loss, aux) and we differentiate loss only
        ((loss, breakdown), (grad_pos, grad_rot, grad_vn)) = jax.value_and_grad(
            loss_fn_with_aux, argnums=(0, 1, 2), has_aux=True
        )(positions, rotations, net_virtual_nodes, epoch, total_epochs, weight_overrides)

        # Zero out gradients for fixed components
        if apply_fixed_mask:
            grad_pos = jnp.where(fixed_mask[:, None], 0.0, grad_pos)
            grad_rot = jnp.where(fixed_mask[:, None], 0.0, grad_rot)

        return (loss, breakdown), (cast(Array, grad_pos), cast(Array, grad_rot), cast(Array, grad_vn))

    return jax.jit(value_and_grad_fn)


def apply_fixed_mask_to_gradients(
    grad_pos: Array,
    grad_rot: Array,
    fixed_mask: Array,
) -> tuple[Array, Array]:
    """
    Zero out gradients for fixed components.

    This utility function can be used when manually computing gradients
    outside of create_value_and_grad_fn.

    Args:
        grad_pos: (N, 2) position gradients.
        grad_rot: (N, 4) rotation gradients.
        fixed_mask: (N,) boolean mask where True = fixed component.

    Returns:
        Tuple of masked (grad_pos, grad_rot) arrays.
    """
    grad_pos = jnp.where(fixed_mask[:, None], 0.0, grad_pos)
    grad_rot = jnp.where(fixed_mask[:, None], 0.0, grad_rot)
    return grad_pos, grad_rot
