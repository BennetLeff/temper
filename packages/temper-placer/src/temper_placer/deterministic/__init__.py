from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from .state import BoardState
from .stages.hv_lv_partition import HvLvPartitionStage, PartitionError
from .stages.base import Stage
from .channels import (
    ALLOWED_SCHEMA_HASHES,
    ALLOWED_SEVERITIES,
    SEVERITY_WEIGHTS,
    Bottleneck,
    ChannelMap,
    ChannelSidecarError,
    routability_penalty,
)

if TYPE_CHECKING:
    from temper_drc.core.fence import DRCFence

_LOGGER = logging.getLogger(__name__)


#: Default placer grid cell size, in micrometres. The closure test verifies
#: that any loaded sidecar's ``cell_size_um`` matches this constant; a
#: mismatch raises a hard error so the placer never consumes a misaligned
#: grid.
PLACER_CELL_SIZE_UM: int = 1000


SIDECAR_FILENAME: str = "placement.channels.json"


def load_channel_map_from_sidecar(
    output_dir: Path | str | None, *, source_label: str = "sidecar"
) -> ChannelMap:
    """Load ``placement.channels.json`` from ``output_dir`` once per call.

    Returns :meth:`ChannelMap.empty` when ``output_dir`` is ``None``, the
    file is missing, or the file fails to parse. All non-fatal failures
    log a WARNING rather than raise so the placer can fall back to
    wirelength-only scoring (R4d).

    The caller (``create_drc_aware_pipeline``) tracks how many times this
    succeeds so the per-instance counter can be asserted at end of run.
    """
    if output_dir is None:
        _LOGGER.warning(
            "no output_dir provided for %s; channel_map disabled", source_label
        )
        return ChannelMap.empty()
    sidecar_path = Path(output_dir) / SIDECAR_FILENAME
    if not sidecar_path.exists():
        _LOGGER.warning(
            "no placement.channels.json at %s; channel_map disabled",
            sidecar_path,
        )
        return ChannelMap.empty()
    try:
        cmap = ChannelMap.load_from_sidecar(sidecar_path)
    except ChannelSidecarError as exc:
        _LOGGER.warning("failed to load %s: %s", sidecar_path, exc)
        return ChannelMap.empty()
    if cmap.cell_size_um != PLACER_CELL_SIZE_UM:
        raise ChannelSidecarError(
            f"sidecar cell_size_um {cmap.cell_size_um} does not match "
            f"placer PLACER_CELL_SIZE_UM {PLACER_CELL_SIZE_UM}; "
            f"refusing to consume a misaligned grid"
        )
    return cmap


def _board_state_to_drc_input(
    state: BoardState,
) -> tuple:
    """Convert BoardState to temper_drc Placement and ConstraintSet.

    Bridges the deterministic pipeline's BoardState representation to the
    DRC check input format. Extracts component positions, net assignments,
    and board dimensions from the immutable state.
    """
    from temper_drc.input.placement import Placement as DRCPlacement, ComponentPlacement as DRCCompPlacement
    from temper_drc.input.constraints import ConstraintSet, ClearanceRule
    from ..core.board import side_to_layer_name

    board_width = state.board.width if state.board else 100.0
    board_height = state.board.height if state.board else 100.0

    # Build component ref -> Component lookup from netlist
    comp_map = {}
    netlist = state.netlist
    if netlist and hasattr(netlist, 'components'):
        for comp in netlist.components:
            comp_map[comp.ref] = comp

    # Extract placed positions from placements frozenset
    components = {}
    for item in state.placements:
        if isinstance(item, tuple) and len(item) == 2:
            ref, placement = item
            comp = comp_map.get(ref)
            if comp:
                width, height = comp.bounds
                footprint = comp.footprint
                net_class = comp.net_class
            else:
                width, height = 1.0, 1.0
                footprint = ""
                net_class = "Signal"

            pos = getattr(placement, 'position', (0.0, 0.0))
            if not isinstance(pos, (tuple, list)):
                pos = (0.0, 0.0)
            rot = getattr(placement, 'rotation', 0)
            if not isinstance(rot, (int, float)):
                rot = 0

            side = getattr(comp, 'initial_side', 0) if comp else 0
            layer = side_to_layer_name(side)

            components[ref] = DRCCompPlacement(
                ref=ref,
                footprint=footprint,
                x=float(pos[0]),
                y=float(pos[1]),
                rotation=float(rot),
                layer=layer,
                width=width,
                height=height,
                net_class=net_class,
            )

    # Build nets from netlist
    nets = {}
    if netlist and hasattr(netlist, 'nets'):
        for net in netlist.nets:
            if hasattr(net, 'pins'):
                nets[net.name] = [pin[0] for pin in net.pins]

    # Build zones from board
    zones = {}
    if state.board:
        for zone in state.board.zones:
            zones[zone.name] = zone.bounds

    placement = DRCPlacement(
        components=components,
        nets=nets,
        zones=zones,
        board_width=board_width,
        board_height=board_height,
    )

    constraints = ConstraintSet(
        clearances=[ClearanceRule(from_class="*", to_class="*", min_mm=0.3)],
        board_width=board_width,
        board_height=board_height,
    )

    return placement, constraints


class DeterministicPipeline:
    """Simple pipeline that runs stages sequentially with optional DRC fence."""

    def __init__(self, stages: List[Stage] = None, fence: "DRCFence | None" = None):
        self.stages = stages or []
        self.fence = fence

    def run(self, initial_state: BoardState = None) -> BoardState:
        from temper_drc.core.fence import _issue_fingerprint

        state = initial_state or BoardState()
        previous_violations: frozenset[str] | None = None
        for stage in self.stages:
            t0 = time.time()
            state = stage.run(state)
            stage_time = (time.time() - t0) * 1000

            if self.fence and stage.invariants:
                invariants = stage.invariants
                modified_regions = stage.last_modified_regions
                placement, constraints = _board_state_to_drc_input(state)

                result = self.fence.check(
                    stage_name=stage.name,
                    invariants=invariants,
                    placement=placement,
                    constraints=constraints,
                    modified_regions=modified_regions,
                    previous_violations=previous_violations,
                    stage_wall_time_ms=stage_time,
                )
                previous_violations = frozenset(
                    _issue_fingerprint(v.issue) for v in result.violations
                )
        return state


class SidecarAwarePipeline(DeterministicPipeline):
    """Pipeline wrapper that owns a per-instance sidecar load counter.

    The counter starts at 0 and is incremented each time a sidecar is
    successfully read from disk. Storing the counter on the instance keeps
    the loader thread-safe under pytest-xdist and avoids the trap of a
    module-level global that would double-count across pipeline runs in
    the same process.
    """

    def __init__(self, *args, channel_map: ChannelMap | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._sidecar_load_count: int = 0
        self.channel_map: ChannelMap | None = channel_map

    def record_sidecar_load(self) -> int:
        """Increment and return the per-instance sidecar load counter."""
        self._sidecar_load_count += 1
        return self._sidecar_load_count


def create_drc_aware_pipeline(
    design_rules=None,
    config=None,
    metadata: "KiCadMetadata | None" = None,
    zone_aware=True,
    parsed_pads=None,
    output_dir: Path | str | None = None,
    parsed_pcb: Any = None,
):
    """Create pipeline with full DRC integration.

    Args:
        design_rules: Design rules for DRC validation
        config: Pipeline configuration
        metadata: KiCad metadata (courtyards, pad sizes, board dimensions) - REQUIRED
        zone_aware: If True, use zone-aware slot generation that avoids copper zones (default: True)
        parsed_pads: Optional list of PadData from kicad_parser.parse_kicad_pcb().pads.
            If provided, DRC oracle uses these exact positions instead of computing
            from component placements. This ensures DRC validates against actual
            KiCad positions, not optimizer-generated positions.
        output_dir: Optional directory searched for ``placement.channels.json``
            (R4a). If present, the sidecar is loaded once and injected into
            the :class:`PhasedComponentAssignmentStage` (R4c). On any error
            the placer falls back to wirelength-only scoring and a WARNING is
            logged (R4d).
        parsed_pcb: Optional :class:`temper_placer.router_v6.stage0_data.ParsedPCB`
            (or any object with a ``source_path: Path`` attribute). When supplied
            AND ``output_dir`` is ``None``, the pipeline derives ``output_dir``
            from ``parsed_pcb.source_path.parent``. This is the canonical
            end-to-end wiring path: the closure test runs channel analysis
            (which writes ``placement.channels.json`` next to the PCB) and
            then calls the pipeline, which now finds the sidecar without
            the caller having to thread ``output_dir`` through the protocol.

    Raises:
        TypeError: If metadata is not provided
        ChannelSidecarError: If the sidecar exists but its ``cell_size_um``
            does not match :data:`PLACER_CELL_SIZE_UM` (refusing to consume
            a misaligned grid).
    """
    if metadata is None:
        raise TypeError("create_drc_aware_pipeline() requires 'metadata' parameter (KiCadMetadata)")

    # R4c end-to-end: if the caller didn't pass output_dir explicitly but did
    # pass a parsed PCB, default to the parent of the PCB source file. The
    # closure test's _run_channel_analysis writes the sidecar next to the
    # PCB, so this is the only plumbing needed to wire it through.
    if output_dir is None and parsed_pcb is not None:
        source_path = getattr(parsed_pcb, "source_path", None)
        if source_path is not None:
            output_dir = Path(source_path).parent

    from .stages import (
        ZoneGeometryStage,
        ZoneAssignmentStage,
        SlotGenerationStage,
        ZoneAwareSlotGenerationStage,
        ComponentAssignmentStage,
        PhasedComponentAssignmentStage,
        HvLvPartitionStage,
        ApplyPlacementsStage,
        CourtyardCheckStage,
        NetClassSetupStage,
        DRCOracleSetupStage,
        ClearanceGridStage,
        NetOrderingStage,
        LayerAssignmentStage,
        PowerPlaneStage,
        FinePitchEscapeStage,
        DRCValidationStage,
        ConnectivityValidationStage,
        ViaValidationStage,
        ViaDeduplicationStage,
        TrackDeduplicationStage,
        ShortCircuitDetectionStage,
        PlacementValidationStage,
    )
    from .stages.config_attach import ConfigAttachStage

    # Build zone config from YAML config if available
    zone_config = None
    slot_spacing = 10.0  # Default: larger spacing to avoid overlaps
    max_clearance = 2.5  # Default: conservative for HV boards
    net_class_clearances = {}
    fixed_placements = {}
    yaml_copper_zones = []
    yaml_isolation_slots = []  # @req(2026-06-23-007, R1)
    config_rules = None  # @req(2026-06-23-007, R2)
    net_priority = {}  # EXP-6: Explicit net routing priority
    placement_constraints = {}  # EXP-12: Placement validation constraints
    hv_exclusion_zones = []  # EXP-13: HV zones that signals must route around

    # Extract net class clearances from design_rules if available
    if design_rules and hasattr(design_rules, "net_classes"):
        for name, rules in design_rules.net_classes.items():
            net_class_clearances[name] = rules.clearance

    # Extract/override from config if available
    if config:
        zone_config = getattr(config, "zones", None)
        slot_config = getattr(config, "slot_generation", None)
        fixed_placements = getattr(config, "fixed_positions", {})
        yaml_copper_zones = getattr(config, "copper_zones", [])
        config_rules = getattr(config, "net_class_rules", None)  # @req(2026-06-23-007, R2)
        # @req(2026-06-23-007, R1): Thread isolation_slots from Constraints
        # to the slot-generation stage so the cutouts can be honored during
        # slot filtering (U2) and the reclaim dict can be exposed to the
        # DRC oracle (U3). Degrade to [] when the field is absent so older
        # configs and test fixtures that don't set isolation_slots still work.
        yaml_isolation_slots = getattr(config, "isolation_slots", [])
        if slot_config and "spacing_mm" in slot_config:
            slot_spacing = slot_config["spacing_mm"]

        # Get net class rules from config
        if config_rules:
            for name, rules in config_rules.items():
                if hasattr(rules, "clearance_mm"):
                    net_class_clearances[name] = rules.clearance_mm
                elif isinstance(rules, dict):
                    net_class_clearances[name] = rules.get("clearance_mm", 0.2)

        if net_class_clearances:
            max_clearance = max(net_class_clearances.values()) + 0.3  # Add margin for trace width

        # EXP-6: Extract net priority from config
        config_net_priority = getattr(config, "net_priority", None)
        if config_net_priority:
            net_priority = dict(config_net_priority)

        # EXP-12: Extract placement validation constraints
        signal_hv = getattr(config, "signal_hv_clearances", None) or []
        proximity = getattr(config, "placement_proximity", None) or []
        # feat/hv-lv-guard-strip: PlacementValidationStage always reads
        # ``self.constraints.get(...)`` even when no constraints were
        # declared, so the dict must be non-empty to survive the
        # ``constraints or []`` fallback in the stage.
        placement_constraints = {
            "signal_hv_clearances": signal_hv,
            "placement_proximity": proximity,
        }

        # EXP-13: Extract HV exclusion zones for routing
        hv_exclusion_zones = getattr(config, "hv_exclusion_zones", [])

        # Create DesignRules from config if not explicitly provided
        if design_rules is None and config_rules:
            from temper_placer.core.design_rules import DesignRules, NetClassRules

            # Convert config NetClassRule objects to core NetClassRules
            converted_net_classes = {}
            for name, rule in config_rules.items():
                converted_net_classes[name] = NetClassRules(
                    name=name,
                    trace_width=getattr(rule, "trace_width_mm", 0.25),
                    clearance=getattr(rule, "clearance_mm", 0.2),
                    via_diameter=getattr(rule, "via_size_mm", 0.6),
                    via_drill=getattr(rule, "via_drill_mm", 0.3),
                    via_template=getattr(rule, "via_template", None),
                    creepage_mm=getattr(rule, "creepage_mm", 0.0),
                    dru_priority=getattr(rule, "dru_priority", 0),
                )

            # Get net class assignments from config
            net_class_assignments = getattr(config, "net_classes", {})

            design_rules = DesignRules(
                net_classes=converted_net_classes,
                net_class_assignments=net_class_assignments,
            )

    # Select slot generation stage based on zone_aware flag
    if zone_aware:
        slot_stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=slot_spacing,
            copper_zone_margin=2.0,
            min_routing_channel=3.0,
            yaml_copper_zones=yaml_copper_zones,
            yaml_isolation_slots=yaml_isolation_slots,  # @req(2026-06-23-007, R1)
            net_class_rules=config_rules,  # @req(2026-06-23-007, R2)
        )
    else:
        slot_stage = SlotGenerationStage(slot_spacing_mm=slot_spacing)

    # Convert metadata pad_sizes to format expected by stages
    # Stage expects Dict[(ref, pad_num), pad_object] but we have Dict[(ref, pad_num), PadSize]
    pad_sizes_for_stage = {}
    for key, pad_size in metadata.pad_sizes.items():
        # Create a simple object with the attributes that stages need
        class PadInfo:
            def __init__(self, pad_size_obj):
                self.size = type("Size", (), {"X": pad_size_obj.width, "Y": pad_size_obj.height})()
                self.number = pad_size_obj.pad_number
                self.shape = getattr(pad_size_obj, "shape", "rect")
                self.rotation = getattr(pad_size_obj, "rotation", 0.0)

        pad_sizes_for_stage[key] = PadInfo(pad_size)

    # Select component assignment stage based on constraint config
    # Use PhasedComponentAssignmentStage if config has placement_priority or constraint rules
    use_phased_placement = config is not None and (
        getattr(config, "placement_priority", None)
        or getattr(config, "component_spacing_rules", None)
        or getattr(config, "component_groups", None)
    )

    if use_phased_placement:
        # U1: pass design_rules so PhasedComponentAssignmentStage can inject
        # 6mm ghost-pad reservations around HV pins before the placement
        # loop runs.  U2: use_isolation_slots toggles creepage reduction
        # against the `isolation_slots` table (default off, NFR4 parity).
        placer_cfg = getattr(config, "placer", None) or {}
        component_stage = PhasedComponentAssignmentStage(
            constraints=config,
            slot_spacing=slot_spacing,
            fixed_placements=fixed_placements,
            design_rules=design_rules,
            use_isolation_slots=bool(placer_cfg.get("use_isolation_slots", False)),
        )
    else:
        component_stage = ComponentAssignmentStage(
            slot_spacing=slot_spacing,
            fixed_placements=fixed_placements,
        )

    # R4a/R4c/R4d: Look for placement.channels.json in the run output dir.
    # Load once per pipeline run; record the count on the wrapper.
    channel_map: ChannelMap | None = load_channel_map_from_sidecar(output_dir)
    if channel_map.has_grid():
        # Sidecar loaded successfully -> thread it into the placement stage.
        if isinstance(component_stage, PhasedComponentAssignmentStage):
            component_stage.channel_map = channel_map

    pipeline = DeterministicPipeline(
        stages=[
            # feat/hv-lv-guard-strip: attach the parsed config to state so
            # downstream stages (HvLvPartitionStage in particular) can read
            # their own block from ``state.config``.
            ConfigAttachStage(config),
            # Setup - apply net class mapping early
            NetClassSetupStage(net_classes=config.net_classes if config else None),
            # Placement stages
            ZoneGeometryStage(zone_config=zone_config),
            ZoneAssignmentStage(),
            # feat/hv-lv-guard-strip: HV/LV domain map MUST run before
            # component assignment so phased_component_assignment (and the
            # standard fallback) can filter slots by domain.
            HvLvPartitionStage(),
            slot_stage,  # Use zone-aware or standard slot generation
            component_stage,  # Use phased or standard component assignment
            ApplyPlacementsStage(),
            # DRC-FIX-4: Resolve courtyard overlaps and clamp to board bounds
            CourtyardCheckStage(
                courtyards=metadata.courtyards,
                board_width=metadata.board_width,
                board_height=metadata.board_height,
                margin=5.0,
            ),
            # DRC-FIX-5: Re-apply placements after clamping to sync component.initial_position
            ApplyPlacementsStage(),
            # EXP-12: Validate placement constraints before routing
            PlacementValidationStage(
                constraints=placement_constraints,
                fail_on_hard_violations=False,  # Log warnings, don't abort
                parsed_pads=parsed_pads,
            ),
            # DRC setup - use parsed_pads for correct KiCad positions
            DRCOracleSetupStage(
                design_rules=config if config else design_rules,
                parsed_pads=parsed_pads,
            ),
            # Routing
            ClearanceGridStage(
                cell_size_mm=0.25,
                layer_count=4,
                max_clearance_mm=max_clearance,
                net_class_clearances=net_class_clearances,
                net_classes=config.net_classes if config else None,
                pad_sizes=pad_sizes_for_stage,  # Inject pad sizes for accurate blocking
                hv_exclusion_zones=hv_exclusion_zones,  # EXP-13: Block zones for signal nets
            ),
            NetOrderingStage(net_priority=net_priority),  # EXP-6: Pass explicit priorities
            LayerAssignmentStage(net_classes=config.net_classes if config else None),
            PowerPlaneStage(),  # Mark plane nets (GND, power rails, ACMains) before routing
            FinePitchEscapeStage(
                pin_pitch_threshold_mm=0.65,
                escape_layer=1,
            ),  # Place escape vias for fine-pitch ICs before main routing
            # Post-routing cleanup (order matters!)
            TrackDeduplicationStage(),  # Remove duplicate tracks first
            ShortCircuitDetectionStage(),  # Remove tracks that short
            ViaDeduplicationStage(),  # Remove duplicate vias
            ViaValidationStage(),  # Remove dangling vias
            # Validation
            DRCValidationStage(),
            ConnectivityValidationStage(),
        ]
    )

    # Wrap in SidecarAwarePipeline so the per-instance sidecar load counter
    # can be asserted at end of run (R7e). The wrapper delegates everything
    # else to the underlying DeterministicPipeline.
    wrapper = SidecarAwarePipeline(
        stages=pipeline.stages,
        fence=pipeline.fence,
        channel_map=channel_map if channel_map.has_grid() else None,
    )
    if channel_map.has_grid():
        # Bump the counter exactly once per successful load.
        wrapper.record_sidecar_load()
    return wrapper


def create_legacy_pipeline():
    """Create legacy pipeline without DRC oracle integration."""
    from .stages import (
        ZoneGeometryStage,
        ZoneAssignmentStage,
        SlotGenerationStage,
        ComponentAssignmentStage,
        HvLvPartitionStage,
        ApplyPlacementsStage,
        ClearanceGridStage,
        NetOrderingStage,
        LayerAssignmentStage,
        DRCValidationStage,
        ConnectivityValidationStage,
        ViaValidationStage,
        ViaDeduplicationStage,
        TrackDeduplicationStage,
    )

    return DeterministicPipeline(
        stages=[
            # Placement stages
            ZoneGeometryStage(),
            ZoneAssignmentStage(),
            # feat/hv-lv-guard-strip: HV/LV domain map MUST run before
            # component assignment so the domain filter is applied.
            HvLvPartitionStage(),
            SlotGenerationStage(slot_spacing_mm=7.5),  # Balanced spacing
            ComponentAssignmentStage(),
            ApplyPlacementsStage(),
            # Routing
            ClearanceGridStage(cell_size_mm=0.25, layer_count=4),
            NetOrderingStage(),
            LayerAssignmentStage(),
            # Post-routing cleanup
            TrackDeduplicationStage(),
            ViaDeduplicationStage(),
            ViaValidationStage(),
            # Validation
            DRCValidationStage(),
            ConnectivityValidationStage(),
        ]
    )
