"""
YAML constraint configuration parser.

This module loads placement constraints from YAML files, defining:
- Zone assignments
- Net class clearances
- Critical nets and loops
- Thermal constraints
- Component groupings
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from temper_placer._constraint_types import (
    AestheticConstraints,
    BleedResistor,
    ClearanceRule,
    ComponentGroup,
    ComponentSpacingRule,
    CriticalLoop,
    CriticalPath,
    DifferentialPairRule,
    EscapeClearance,
    FeedbackConfig,
    GroupSeparation,
    HVExclusionZone,
    IsolationBarrier,
    IsolationSlot,
    LossConfig,
    LossesConfig,
    ManufacturingConstraint,
    ManufacturingConstraints,
    MatchedLengthGroup,
    NetClassRule,
    NoiseDomain,
    NoiseIsolationRule,
    PlacementConstraints,
    PlacementProximityConstraint,
    ProximityRule,
    RoutingCorridor,
    SeedFilterConfig,
    SignalToHVClearance,
    SkinEffectDerating,
    SnubberRequirement,
    StarGroundConfig,
    ThermalConstraint,
    ThermalProperties,
)
from temper_placer.core.board import Board, GroundDomain, LayerStackup, Zone
from temper_placer.core.differential_pair import DifferentialPairConstraint
from temper_placer.core.net_graph import NetGraph, SubNetEdge
from temper_placer.core.net_types import NetClassification

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.netlist import Netlist


class ConfigValidationError(Exception):
    """Wraps Pydantic ValidationError with the config file path context."""

    def __init__(self, config_path: Path, validation_error: ValidationError) -> None:
        self.config_path = config_path
        self.validation_error = validation_error
        super().__init__(f"Invalid config at {config_path}: {validation_error}")


_LOSS_NAMES = [
    "overlap", "boundary", "wirelength", "spread", "edge_avoidance",
    "group_cluster", "thermal", "zone", "clearance", "loop_area", "star_point",
]


def _resolve_bounds(cfg_item: dict, board_width: float, board_height: float) -> tuple[float, ...]:
    """Resolve zone bounds from absolute or ratio-based format."""
    if "bounds_ratio" in cfg_item:
        ratio = cfg_item["bounds_ratio"]
        return (
            ratio[0] * board_width,
            ratio[1] * board_height,
            ratio[2] * board_width,
            ratio[3] * board_height,
        )
    return tuple(cfg_item["bounds"])


def _parse_proximity_rules(group_cfg: dict) -> list[ProximityRule]:
    """Parse proximity rules within a component group config dict."""
    rules: list[ProximityRule] = []
    if "proximity" not in group_cfg:
        return rules
    for prox_cfg in group_cfg["proximity"]:
        if isinstance(prox_cfg, dict):
            pair = prox_cfg.get("pair", prox_cfg.get("components", []))
            max_dist = prox_cfg.get("max_distance_mm", 10.0)
            tier = prox_cfg.get("tier", "soft")
        elif isinstance(prox_cfg, (list, tuple)):
            pair = prox_cfg[0] if len(prox_cfg) > 0 else []
            max_dist = prox_cfg[1] if len(prox_cfg) > 1 else 10.0
            tier = "soft"
        else:
            continue
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            rules.append(
                ProximityRule(component_a=pair[0], component_b=pair[1], max_distance_mm=max_dist, tier=tier)
            )
    return rules


def _preprocess_config(raw: dict) -> dict:
    """Pre-process the raw YAML dict into a dict compatible with PlacementConstraints.model_validate()."""
    processed: dict = {}

    # --- Board geometry ---
    if "board" in raw:
        board = raw["board"]
        processed["board_width_mm"] = board.get("width_mm", 100.0)
        processed["board_height_mm"] = board.get("height_mm", 150.0)
        processed["board_margin_mm"] = board.get("margin_mm", 3.0)
        if "keepouts" in board:
            processed["keepouts"] = [tuple(ko) for ko in board["keepouts"]
                                     if isinstance(ko, (list, tuple)) and len(ko) >= 4]
    else:
        processed["board_width_mm"] = raw.get("board_width_mm", 100.0)
        processed["board_height_mm"] = raw.get("board_height_mm", 150.0)
        processed["board_margin_mm"] = raw.get("board_margin_mm", 3.0)

    bw = processed["board_width_mm"]
    bh = processed["board_height_mm"]

    # --- Zones ---
    if "zones" in raw:
        processed["zones"] = []
        for zone_cfg in raw["zones"]:
            bounds = _resolve_bounds(zone_cfg, bw, bh)
            processed["zones"].append(
                Zone(
                    name=zone_cfg["name"],
                    bounds=bounds,
                    net_classes=zone_cfg.get("net_classes", ["Signal"]),
                    components=zone_cfg.get("components", []),
                    max_size=tuple(zone_cfg["max_size"]) if "max_size" in zone_cfg else None,
                    can_expand=zone_cfg.get("can_expand", ["up", "down", "left", "right"]),
                    zone_type=zone_cfg.get("type", "placement"),
                )
            )

    # --- Copper zones ---
    if "copper_zones" in raw:
        processed.setdefault("copper_zones", [])
        for cz_cfg in raw["copper_zones"]:
            bounds = _resolve_bounds(cz_cfg, bw, bh)
            processed["copper_zones"].append(
                Zone(
                    name=cz_cfg["name"],
                    bounds=bounds,
                    net_classes=cz_cfg.get("net_classes", ["GND"]),
                    layers=cz_cfg.get("layers", ["B.Cu"]),
                )
            )

    # --- Ground domains ---
    if "ground_domains" in raw:
        processed["ground_domains"] = [
            GroundDomain(
                name=dc["name"],
                bounds=tuple(dc["bounds"]),
                star_point=tuple(dc["star_point"]) if "star_point" in dc else None,
            )
            for dc in raw["ground_domains"]
        ]

    # --- PCL constraints ---
    if "constraints" in raw:
        from temper_placer.pcl.parser import parse_constraint_dict
        processed["pcl_constraints"] = [parse_constraint_dict(entry) for entry in raw["constraints"]]

    # --- Net assignments ---
    if "net_assignments" in raw and isinstance(raw["net_assignments"], dict):
        processed.setdefault("net_classes", {})
        for class_name, net_list in raw["net_assignments"].items():
            if isinstance(net_list, list):
                for net_name in net_list:
                    if isinstance(net_name, str) and net_name.strip():
                        processed["net_classes"][net_name.strip()] = class_name

    # --- Feedback ---
    if "feedback" in raw:
        fc = raw["feedback"]
        processed["feedback"] = FeedbackConfig(
            max_iterations=fc.get("max_iterations", 5),
            violation_threshold=fc.get("violation_threshold", 5),
            expansion_per_violation=fc.get("expansion_per_violation", 0.5),
        )

    # --- Clearance rules ---
    if "clearances" in raw:
        processed["clearances"] = [
            ClearanceRule(
                from_class=rc["from"],
                to_class=rc["to"],
                clearance_mm=rc["clearance_mm"],
                description=rc.get("description", ""),
            )
            for rc in raw["clearances"]
        ]
    if "hv_clearance_mm" in raw:
        processed["hv_clearance_mm"] = raw["hv_clearance_mm"]

    # --- Critical loops ---
    if "critical_loops" in raw:
        processed["critical_loops"] = []
        for loop_cfg in raw["critical_loops"]:
            pins_raw = loop_cfg.get("pins")
            pins = [tuple(p) for p in pins_raw if len(p) >= 2] if pins_raw else None
            processed["critical_loops"].append(
                CriticalLoop(
                    name=loop_cfg["name"],
                    nets=loop_cfg.get("nets", []),
                    pins=pins,
                    max_area_mm2=loop_cfg.get("max_area_mm2"),
                    weight=loop_cfg.get("weight", 1.0),
                    description=loop_cfg.get("description", ""),
                )
            )

    # --- Critical paths ---
    if "critical_paths" in raw:
        processed["critical_paths"] = []
        for name, path_cfg in raw["critical_paths"].items():
            pins = path_cfg.get("pins")
            processed["critical_paths"].append(
                CriticalPath(
                    name=name,
                    from_comp=path_cfg["from"],
                    to_comp=path_cfg["to"],
                    pins=tuple(pins) if pins and len(pins) >= 2 else None,
                    max_length_mm=path_cfg.get("max_length_mm", 50.0),
                    priority=path_cfg.get("priority", "normal"),
                    matched_length_group=path_cfg.get("matched_length_group"),
                )
            )

    # --- Matched length groups ---
    if "matched_length_groups" in raw:
        processed["matched_length_groups"] = [
            MatchedLengthGroup(name=name, tolerance_mm=cfg.get("tolerance_mm", 5.0))
            for name, cfg in raw["matched_length_groups"].items()
        ]

    # --- Noise isolation ---
    if "noise_isolation" in raw:
        processed["noise_isolation"] = [
            NoiseIsolationRule(
                name=name,
                sensitive_components=rc["sensitive_components"],
                noise_sources=rc["noise_sources"],
                min_distance_mm=rc.get("min_distance_mm", 10.0),
                weight=rc.get("weight", 1.0),
            )
            for name, rc in raw["noise_isolation"].items()
        ]

    # --- Star grounds ---
    if "star_grounds" in raw:
        processed["star_grounds"] = [
            StarGroundConfig(
                net=sc["net"],
                weight=sc.get("weight", 1.0),
                anchor=tuple(sc["anchor"]) if "anchor" in sc else None,
                description=sc.get("description", ""),
            )
            for sc in raw["star_grounds"]
        ]

    # --- Thermal constraints ---
    if "thermal" in raw:
        processed["thermal_constraints"] = []
        for tc in raw["thermal"]:
            min_spacing = tc.get("min_spacing_mm", tc.get("min_separation_mm", 5.0))
            processed["thermal_constraints"].append(
                ThermalConstraint(
                    components=tc["components"],
                    prefer_edge=tc.get("prefer_edge", True),
                    min_spacing_mm=min_spacing,
                    max_distance_from_edge_mm=tc.get("max_distance_from_edge_mm", 20.0),
                    description=tc.get("description", ""),
                )
            )

    # --- Thermal properties ---
    if "thermal_properties" in raw:
        tp_cfg = raw["thermal_properties"]
        high_power = tp_cfg.get("high_power", {})
        heat_sensitive = tp_cfg.get("heat_sensitive", {})
        thermal_pads = tp_cfg.get("thermal_pads", {})
        processed["thermal_properties"] = ThermalProperties(
            high_power_components=high_power.get("components", []),
            power_dissipation_w=high_power.get("power_dissipation_w", {}),
            min_separation_mm=high_power.get("min_separation_mm", 15.0),
            heat_sensitive_components=heat_sensitive.get("components", []),
            max_temp_rise_c=heat_sensitive.get("max_temp_rise_c", 20.0),
            min_distance_from_heat_sources_mm=heat_sensitive.get("min_distance_from_heat_sources_mm", 20.0),
            thermal_pad_components=thermal_pads.get("components", []),
            prefer_edge=thermal_pads.get("prefer_edge", True),
            preferred_edge_margin_mm=thermal_pads.get("preferred_edge_margin_mm", 10.0),
        )

    # --- Component groups ---
    if "groups" in raw:
        processed.setdefault("component_groups", [])
        for gc in raw["groups"]:
            processed["component_groups"].append(
                ComponentGroup(
                    name=gc["name"],
                    components=gc["components"],
                    max_spread_mm=gc.get("max_spread_mm", 30.0),
                    zone=gc.get("zone"),
                    proximity_rules=_parse_proximity_rules(gc),
                    weight=gc.get("weight", 1.0),
                    description=gc.get("description", ""),
                    template_group=gc.get("template_group"),
                    primary_pin=gc.get("primary_pin"),
                    stacked_layout=gc.get("stacked_layout", False),
                )
            )

    if "component_groups" in raw:
        processed.setdefault("component_groups", [])
        for gc in raw["component_groups"]:
            leader = gc.get("leader")
            followers = gc.get("followers", [])
            comps = [leader] if leader else []
            comps.extend(followers)
            if comps:
                processed["component_groups"].append(
                    ComponentGroup(
                        name=gc["name"],
                        components=comps,
                        max_spread_mm=gc.get("max_distance", 30.0),
                        zone=gc.get("zone"),
                        proximity_rules=[],
                        weight=gc.get("weight", 1.0),
                        description=gc.get("description", ""),
                    )
                )

    # --- Group separation ---
    if "group_separation" in raw:
        processed["group_separations"] = []
        for sc in raw["group_separation"]:
            groups = sc.get("groups", [])
            if len(groups) >= 2:
                processed["group_separations"].append(
                    GroupSeparation(
                        group_a=groups[0],
                        group_b=groups[1],
                        min_distance_mm=sc.get("min_distance_mm", 20.0),
                        description=sc.get("description", ""),
                    )
                )

    # --- Component spacing ---
    if "minimum_spacing" in raw:
        processed["component_spacing_rules"] = []
        for sc in raw["minimum_spacing"]:
            comps = sc.get("components", [])
            if len(comps) >= 2:
                processed["component_spacing_rules"].append(
                    ComponentSpacingRule(
                        component_a=comps[0],
                        component_b=comps[1],
                        min_separation_mm=sc.get("min_separation_mm", 2.0),
                        description=sc.get("description", ""),
                        weight=sc.get("weight", 1.0),
                        tier=sc.get("tier", "soft"),
                    )
                )

    # --- Manufacturing constraints ---
    if "manufacturing_constraints" in raw:
        processed["manufacturing_constraints"] = [
            ManufacturingConstraint(
                components=mc["components"],
                allowed_orientations=mc.get("allowed_orientations"),
                side=mc.get("side"),
                tier=mc.get("tier", "hard"),
                because=mc.get("because", ""),
                weight=mc.get("weight", 1.0),
            )
            for mc in raw["manufacturing_constraints"]
        ]

    # --- Fixed components / positions / zone assignments ---
    if "fixed_components" in raw:
        fc_raw = raw["fixed_components"]
        if isinstance(fc_raw, dict):
            processed["fixed_components"] = list(fc_raw.keys())
            processed.setdefault("fixed_positions", {})
            for ref, pos_cfg in fc_raw.items():
                if isinstance(pos_cfg, dict) and "x" in pos_cfg and "y" in pos_cfg:
                    processed["fixed_positions"][ref] = (float(pos_cfg["x"]), float(pos_cfg["y"]))
        elif isinstance(fc_raw, list):
            processed["fixed_components"] = fc_raw
        else:
            processed["fixed_components"] = []
    if "fixed_positions" in raw:
        fp = dict(processed.get("fixed_positions", {}))
        fc = list(processed.get("fixed_components", []))
        for ref, pos in raw["fixed_positions"].items():
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                fp[ref] = (float(pos[0]), float(pos[1]))
            elif isinstance(pos, dict) and "x" in pos and "y" in pos:
                fp[ref] = (float(pos["x"]), float(pos["y"]))
            if ref not in fc:
                fc.append(ref)
        processed["fixed_positions"] = fp
        processed["fixed_components"] = fc
    if "zone_assignments" in raw:
        processed["zone_assignments"] = raw["zone_assignments"]

    # --- Net config ---
    if "net_classes" in raw:
        processed["net_classes"] = raw["net_classes"]

    if "net_class_rules" in raw:
        processed["net_class_rules"] = {
            name: NetClassRule(
                name=name,
                trace_width_mm=rc.get("trace_width_mm", 0.2),
                clearance_mm=rc.get("clearance_mm", 0.2),
                via_size_mm=rc.get("via_size_mm", 0.6),
                via_drill_mm=rc.get("via_drill_mm", 0.3),
                via_template=rc.get("via_template"),
                creepage_mm=rc.get("creepage_mm", 0.0),
                allow_neckdown=rc.get("allow_neckdown", True),
                description=rc.get("description", ""),
                max_current_rating=rc.get("max_current_rating"),
                routing_strategy=rc.get("routing_strategy"),
                via_cost_multiplier=rc.get("via_cost_multiplier", 1.0),
                target_impedance=rc.get("target_impedance"),
                voltage_v=rc.get("voltage_v", 0.0),
            )
            for name, rc in raw["net_class_rules"].items()
        }

    if "net_priority" in raw:
        processed["net_priority"] = {str(k): int(v) for k, v in raw["net_priority"].items()}

    # --- Differential pairs ---
    if "differential_pairs" in raw:
        processed["differential_pairs"] = []
        for dc in raw["differential_pairs"]:
            pos = dc.get("positive_net") or dc.get("net_pos")
            neg = dc.get("negative_net") or dc.get("net_neg")
            if pos and neg:
                processed["differential_pairs"].append(
                    DifferentialPairRule(
                        net_pos=pos,
                        net_neg=neg,
                        spacing_mm=dc.get("separation_mm") or dc.get("spacing_mm") or 0.2,
                        coupling_tolerance_mm=dc.get("coupling_tolerance_mm", 0.5),
                        impedance_ohm=dc.get("target_impedance_ohm") or dc.get("impedance_ohm"),
                        max_skew_mm=dc.get("max_skew_mm", 0.5),
                        description=dc.get("description", ""),
                    )
                )

    # --- Net topology ---
    if "net_topology" in raw:
        processed.setdefault("net_topologies", [])
        for net_name, topo_cfg in raw["net_topology"].items():
            graph = NetGraph(net_name=net_name)
            if "star_nodes" in topo_cfg:
                graph.star_nodes = set(topo_cfg["star_nodes"])
            if "edges" in topo_cfg:
                for ec in topo_cfg["edges"]:
                    graph.edges.append(
                        SubNetEdge(
                            source_pin=ec["source"],
                            sink_pin=ec["sink"],
                            trace_width_mm=ec.get("width"),
                            clearance_mm=ec.get("clearance"),
                            priority=ec.get("priority", 0),
                        )
                    )
            processed["net_topologies"].append(graph)

    if "kelvin_sensing" in raw:
        processed.setdefault("net_topologies", [])
        for kc in raw["kelvin_sensing"]:
            net_name = kc["net_name"]
            star_pin = kc["star_point_pin"]
            graph = NetGraph(net_name=net_name)
            graph.star_nodes.add(star_pin)
            for fp in kc.get("force_pins", []):
                graph.edges.append(
                    SubNetEdge(
                        source_pin=star_pin, sink_pin=fp,
                        trace_width_mm=kc.get("force_width_mm", 1.0), priority=10,
                    )
                )
            for sp in kc.get("sense_pins", []):
                graph.edges.append(
                    SubNetEdge(
                        source_pin=star_pin, sink_pin=sp,
                        trace_width_mm=kc.get("sense_width_mm", 0.2), priority=5,
                    )
                )
            processed["net_topologies"].append(graph)

    # --- Aesthetics ---
    if "aesthetics" in raw:
        aes = raw["aesthetics"]
        processed["aesthetics"] = AestheticConstraints(
            grid_size_mm=aes.get("grid_size_mm", 0.5),
            grid_weight=aes.get("grid_weight", 1.0),
            alignment_weight=aes.get("alignment_weight", 1.0),
            rotation_consistency_weight=aes.get("rotation_consistency_weight", 1.0),
            align_by_prefix=aes.get("align_by_prefix", True),
            prefix_exceptions=aes.get("prefix_exceptions", []),
            max_wirelength_tax=aes.get("max_wirelength_tax", 2.5),
            consensus_weight=aes.get("consensus_weight", 1.0),
            whitespace_weight=aes.get("whitespace_weight", 0.0),
            grouping_weight=aes.get("grouping_weight", 0.0),
            symmetry_weight=aes.get("symmetry_weight", 0.0),
        )

    # --- Manufacturing ---
    if "manufacturing" in raw:
        mfg = raw["manufacturing"]
        processed["manufacturing"] = ManufacturingConstraints(
            target_margin_mm=mfg.get("target_margin_mm", 0.1),
            margin_weight=mfg.get("margin_weight", 0.0),
            etch_tolerance_mm=mfg.get("etch_tolerance_mm", 0.02),
        )

    # --- Losses ---
    if "losses" in raw:
        processed["losses"] = _build_losses_config(raw["losses"])
    elif "loss_weights" in raw:
        _NAME_MAP = {
            "zone_membership": "zone", "zone": "zone",
            "overlap": "overlap", "boundary": "boundary",
            "wirelength": "wirelength", "spread": "spread",
            "edge_avoidance": "edge_avoidance", "group_cluster": "group_cluster",
            "thermal": "thermal", "clearance": "clearance",
            "loop_area": "loop_area", "star_point": "star_point",
        }
        mapped_weights = {}
        for wkey, wval in raw["loss_weights"].items():
            name = _NAME_MAP.get(wkey, wkey)
            if name in _LOSS_NAMES:
                mapped_weights[name] = float(wval)
        processed["losses"] = _build_losses_config(mapped_weights)

    # --- Routing-aware ---
    if "escape_clearances" in raw:
        processed["escape_clearances"] = [
            EscapeClearance(
                component=ec["component"],
                clearance_mm=ec.get("clearance_mm"),
                priority_sides=ec.get("priority_sides", []),
                tier=ec.get("tier", "soft"),
                description=ec.get("description", ""),
            )
            for ec in raw["escape_clearances"]
        ]

    if "routing_corridors" in raw:
        processed["routing_corridors"] = [
            RoutingCorridor(
                name=rc["name"],
                from_component=rc["from_component"],
                to_component=rc["to_component"],
                width_mm=rc["width_mm"],
                keep_clear=rc.get("keep_clear", True),
                nets=rc.get("nets", []),
                tier=rc.get("tier", "soft"),
                description=rc.get("description", ""),
            )
            for rc in raw["routing_corridors"]
        ]

    # --- HV safety ---
    if "signal_hv_clearances" in raw:
        processed["signal_hv_clearances"] = [
            SignalToHVClearance(
                name=sc["name"],
                signal_component=sc["signal_component"],
                signal_pin=str(sc["signal_pin"]),
                target_component=sc["target_component"],
                target_pin=str(sc["target_pin"]),
                hv_component=sc["hv_component"],
                hv_pins=[str(p) for p in sc["hv_pins"]],
                required_clearance_mm=sc.get("required_clearance_mm", 6.0),
                max_path_length_mm=sc.get("max_path_length_mm", 20.0),
                tier=sc.get("tier", "hard"),
                description=sc.get("description", ""),
            )
            for sc in raw["signal_hv_clearances"]
        ]

    if "placement_proximity" in raw:
        processed["placement_proximity"] = [
            PlacementProximityConstraint(
                name=pc["name"],
                from_component=pc["from_component"],
                from_pin=str(pc["from_pin"]),
                to_component=pc["to_component"],
                to_pin=str(pc["to_pin"]),
                max_distance_mm=pc.get("max_distance_mm", 15.0),
                tier=pc.get("tier", "hard"),
                description=pc.get("description", ""),
            )
            for pc in raw["placement_proximity"]
        ]

    if "hv_exclusion_zones" in raw:
        _NAME_TO_REFDES = {"q1_hv_zone": "Q1", "q2_hv_zone": "Q2", "q1_hv_exclusion": "Q1", "q2_hv_exclusion": "Q2"}
        processed["hv_exclusion_zones"] = []
        for hc in raw["hv_exclusion_zones"]:
            center = hc["center"]
            size = hc["size"]
            processed["hv_exclusion_zones"].append(
                HVExclusionZone(
                    name=hc["name"],
                    center=(float(center[0]), float(center[1])),
                    size=(float(size[0]), float(size[1])),
                    clearance_mm=hc.get("clearance_mm", 6.0),
                    excluded_nets=hc.get("excluded_nets", []),
                    description=hc.get("description", ""),
                    component_refdes=_NAME_TO_REFDES.get(hc["name"]),
                )
            )

    if "isolation_slots" in raw:
        processed["isolation_slots"] = []
        for sc in raw["isolation_slots"]:
            start = sc["start_offset"]
            end = sc["end_offset"]
            processed["isolation_slots"].append(
                IsolationSlot(
                    name=sc["name"],
                    component_ref=sc["component_ref"],
                    start_offset=(float(start[0]), float(start[1])),
                    end_offset=(float(end[0]), float(end[1])),
                    width_mm=sc.get("width_mm", 1.5),
                    lv_pin=sc.get("lv_pin", ""),
                    hv_pin=sc.get("hv_pin", ""),
                    description=sc.get("description", ""),
                )
            )

    # --- U3 extensions ---
    if "noise_domains" in raw:
        processed["noise_domains"] = [
            NoiseDomain(
                emitters=nd.get("emitters", []),
                victims=nd.get("victims", []),
                max_parallel_run_mm=nd.get("max_parallel_run_mm", 5.0),
            )
            for nd in raw["noise_domains"]
        ]

    if "isolation_barriers" in raw:
        processed["isolation_barriers"] = [
            IsolationBarrier(
                name=ib["name"],
                x_mm=ib["x_mm"],
                y_span=tuple(ib["y_span"]),
                layers=ib.get("layers", "all"),
            )
            for ib in raw["isolation_barriers"]
        ]

    if "snubber_requirements" in raw:
        processed["snubber_requirements"] = [
            SnubberRequirement(
                igbt_pair=tuple(sr["igbt_pair"]),
                type=sr.get("type", "RC"),
                across=sr.get("across", "collector_emitter"),
            )
            for sr in raw["snubber_requirements"]
        ]

    if "bleed_resistor" in raw:
        br = raw["bleed_resistor"]
        processed["bleed_resistor"] = BleedResistor(
            bus_voltage_v=br["bus_voltage_v"],
            target_voltage_v=br["target_voltage_v"],
            timeout_s=br.get("timeout_s", 5.0),
        )

    if "skin_effect_derating" in raw:
        sd = raw["skin_effect_derating"]
        processed["skin_effect_derating"] = SkinEffectDerating(
            frequency_hz=sd["frequency_hz"],
            derating_factor=sd.get("derating_factor", 3.0),
        )

    # --- Misc passthrough ---
    if "slot_generation" in raw and isinstance(raw["slot_generation"], dict):
        processed["slot_generation"] = raw["slot_generation"]
    if "placement_priority" in raw:
        processed["placement_priority"] = raw["placement_priority"]
    if "routing_priority" in raw:
        processed["routing_priority"] = raw["routing_priority"]
    if "placer" in raw:
        processed["placer"] = raw["placer"]

    # --- Seed filter ---
    if "seed_filter" in raw and isinstance(raw["seed_filter"], dict):
        sf = raw["seed_filter"]
        processed["seed_filter"] = SeedFilterConfig(
            enabled=bool(sf.get("enabled", True)),
            threshold=float(sf.get("threshold", 0.7)),
            hv_threshold=float(sf.get("hv_threshold", 0.5)),
        )

    return processed


def _build_losses_config(loss_data: dict) -> LossesConfig:
    """Build a LossesConfig from a dict of loss_name -> weight or {weight, enabled}."""
    kwargs = {}
    for loss_name in _LOSS_NAMES:
        if loss_name in loss_data:
            data = loss_data[loss_name]
            if data is None:
                continue
            if isinstance(data, dict):
                kwargs[loss_name] = LossConfig(
                    weight=float(data.get("weight", 1.0)),
                    enabled=data.get("enabled", True),
                    margin=data.get("margin"),
                )
            else:
                kwargs[loss_name] = LossConfig(weight=float(data))
    return LossesConfig(**kwargs)


def _build_net_classification(constraints: PlacementConstraints, net_class_rules_raw: dict) -> None:
    if not constraints.net_classes and not constraints.net_class_rules:
        return
    constraints.net_classification = NetClassification.from_yaml_config(
        net_classes=constraints.net_classes,
        net_class_rules=net_class_rules_raw,
    )
    validation_errors = constraints.net_classification.validate_all()
    if validation_errors:
        import logging
        logger = logging.getLogger(__name__)
        for net_name, errors in validation_errors.items():
            for error in errors:
                logger.error(f"Net '{net_name}' validation error: {error}")


def _emit_keepout_constraints(constraints: PlacementConstraints) -> None:
    """Auto-emit PCL KeepoutConstraint from zones with type='keepout'."""
    for zone in constraints.zones:
        if getattr(zone, "zone_type", "placement") == "keepout":
            from temper_placer.pcl.constraints import ConstraintTier, KeepoutConstraint
            constraints.pcl_constraints.append(
                KeepoutConstraint(
                    zone_name=zone.name,
                    tier=ConstraintTier.HARD,
                    margin_mm=0.0,
                    because=f"Auto-generated from zone '{zone.name}' (type: keepout)",
                )
            )


def _validate_current_capacity(constraints: PlacementConstraints) -> None:
    """Validate that high-current nets have appropriate routing strategies."""
    import logging
    from temper_placer.core.ipc2221 import estimate_current_from_net_class
    logger = logging.getLogger(__name__)
    for net_name, net_class_name in constraints.net_classes.items():
        net_class = constraints.net_class_rules.get(net_class_name)
        if not net_class:
            continue
        if net_class.max_current_rating is not None:
            current_a = net_class.max_current_rating
        else:
            current_a = estimate_current_from_net_class(net_class.trace_width_mm)
        has_zone = any(net_class_name in zone.net_classes for zone in constraints.zones)
        if current_a > 10.0:
            if not has_zone:
                raise ValueError(
                    f"HIGH CURRENT NET '{net_name}' ({current_a:.1f}A) requires zone/pour assignment.\n"
                    f"Traced routing is inadequate for >10A nets. Professional PCB design requires:\n"
                    f"  1. Add zone for net class '{net_class_name}' in zones config, OR\n"
                    f"  2. Assign '{net_class_name}' to existing zone's net_classes list\n"
                    f"Current capacity: {current_a:.1f}A (trace: {net_class.trace_width_mm}mm)\n"
                    f"Reference: IPC-2221A Section 6.2 (Current Capacity)"
                )
        elif current_a > 5.0:
            if net_class.via_template == "Via1x1" or not net_class.via_template:
                logger.warning(
                    f"MEDIUM CURRENT NET '{net_name}' ({current_a:.1f}A) uses single vias.\n"
                    f"Consider via_template: 'Via2x2' or 'Via3x3' for {net_class_name} class.\n"
                    f"Single 0.3mm vias rated ~3-5A; via arrays recommended for >5A."
                )
            if current_a > 8.0 and not has_zone:
                logger.info(
                    f"Net '{net_name}' ({current_a:.1f}A) approaching high-current threshold. "
                    f"Consider zone/pour assignment for better thermal performance."
                )


def load_constraints(config_path: Path) -> PlacementConstraints:
    """Load placement constraints from a YAML configuration file."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    try:
        processed = _preprocess_config(raw)
        constraints = PlacementConstraints.model_validate(processed)
    except ValidationError as e:
        raise ConfigValidationError(config_path, e) from e
    _emit_keepout_constraints(constraints)
    _build_net_classification(constraints, raw.get("net_class_rules", {}))
    _validate_current_capacity(constraints)
    return constraints


def infer_rjc(package_type: str | None) -> float:
    """Infer Rjc (K/W) from package type string."""
    if not package_type:
        return _DEFAULT_RJC
    for key, value in _RJC_PACKAGE_LOOKUP.items():
        if key.lower() in package_type.lower():
            return value
    return _DEFAULT_RJC


_RJC_PACKAGE_LOOKUP: dict[str, float] = {
    "TO-247": 0.6,
    "TO-220": 1.0,
    "DPAK": 2.0,
    "D2PAK": 1.5,
    "SOT-223": 15.0,
    "SOIC-8": 50.0,
    "TO-263": 1.5,
    "TO-252": 2.0,
    "QFN-48": 5.0,
}

_DEFAULT_RJC: float = 0.6


def constraints_to_design_rules(constraints: PlacementConstraints) -> DesignRules:
    """Convert placement constraints to routing design rules."""
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.design_rules import NetClassRules as CoreNetClassRules
    rules = DesignRules()
    rules.net_class_assignments = constraints.net_classes.copy()
    for name, rule in constraints.net_class_rules.items():
        rules.net_classes[name] = CoreNetClassRules(
            name=rule.name,
            trace_width=rule.trace_width_mm,
            clearance=rule.clearance_mm,
            via_diameter=rule.via_size_mm,
            via_drill=rule.via_drill_mm,
            via_template=rule.via_template or "Via1x1",
            creepage_mm=rule.creepage_mm,
            voltage_v=rule.voltage_v,
            routing_strategy=rule.routing_strategy,
            via_cost_multiplier=rule.via_cost_multiplier,
            dru_priority=0,
        )
    for pair_rule in constraints.differential_pairs:
        rules.differential_pairs.append(DifferentialPairConstraint(
            net_pos=pair_rule.net_pos, net_neg=pair_rule.net_neg,
            spacing_mm=pair_rule.spacing_mm, coupling_tolerance_mm=pair_rule.coupling_tolerance_mm,
            impedance_ohm=pair_rule.impedance_ohm, max_skew_mm=pair_rule.max_skew_mm,
        ))
    for graph in constraints.net_topologies:
        rules.net_topologies[graph.net_name] = graph
    return rules


def create_board_from_constraints(constraints: PlacementConstraints) -> Board:
    """Create a Board object from constraints configuration."""
    return Board(
        width=constraints.board_width_mm,
        height=constraints.board_height_mm,
        origin=(0.0, 0.0),
        zones=constraints.zones,
        ground_domains=constraints.ground_domains,
        keepouts=constraints.keepouts,
        layer_stackup=constraints.layer_stackup or LayerStackup.default_4layer(),
    )


def apply_zones_to_netlist(netlist: Netlist, constraints: PlacementConstraints) -> None:
    """Apply zone assignments from component groups to components."""
    for group in constraints.component_groups:
        if group.zone:
            for comp_ref in group.components:
                comp = next((c for c in netlist.components if c.ref == comp_ref), None)
                if comp:
                    comp.zone = group.zone


def apply_fixed_components_to_netlist(netlist, constraints: PlacementConstraints) -> None:
    """Apply fixed_components list from constraints to netlist."""
    if not constraints.fixed_components and not constraints.fixed_positions:
        return
    fixed_set = set(constraints.fixed_components)
    for comp in netlist.components:
        if comp.ref in fixed_set:
            comp.fixed = True
        if comp.ref in constraints.fixed_positions:
            pos = constraints.fixed_positions[comp.ref]
            comp.initial_position = pos
            comp.fixed = True
