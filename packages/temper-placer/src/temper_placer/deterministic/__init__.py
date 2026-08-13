# ruff: noqa: F821  # type-only references to PlacementConstraint, CopperZone, etc.
from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import temper_orchestration as _to

from temper_placer.validation.drc_types import ClearanceRule as _DRCClearanceRule
from temper_placer.validation.drc_types import ComponentPlacement as _DRCCompPlacement
from temper_placer.validation.drc_types import ConstraintSet as _DRCConstraintSet
from temper_placer.validation.drc_types import Placement as _DRCPlacement

from .channels import (
    ALLOWED_SCHEMA_HASHES as ALLOWED_SCHEMA_HASHES,
)
from .channels import (
    ALLOWED_SEVERITIES as ALLOWED_SEVERITIES,
)
from .channels import (
    SEVERITY_WEIGHTS as SEVERITY_WEIGHTS,
)
from .channels import (
    Bottleneck as Bottleneck,
)
from .channels import (
    ChannelMap as ChannelMap,
)
from .channels import (
    ChannelSidecarError as ChannelSidecarError,
)
from .channels import (
    routability_penalty as routability_penalty,
)
from .stages.base import Stage
from .stages.hv_lv_partition import HvLvPartitionStage as HvLvPartitionStage
from .stages.hv_lv_partition import PartitionError as PartitionError
from .state import BoardState

if TYPE_CHECKING:
    from typing import Any

    from shapely.geometry import Polygon

    from temper_placer.core.board import Zone as CopperZone
    from temper_placer.io.config_loader import IsolationSlot
    from temper_placer.validation.drc_fence import DRCFence

    from .io.kicad_metadata import KiCadMetadata

_SIDE_TO_LAYER: dict[int, str] = {0: "F.Cu", 1: "B.Cu"}
_DEFAULT_CLEARANCES = [_DRCClearanceRule(from_class="*", to_class="*", min_mm=0.3)]

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
        _LOGGER.warning("no output_dir provided for %s; channel_map disabled", source_label)
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
) -> tuple[_DRCPlacement, _DRCConstraintSet]:
    """Convert BoardState to temper_drc Placement and ConstraintSet."""
    board_width = state.board.width if state.board else 100.0
    board_height = state.board.height if state.board else 100.0

    netlist = state.netlist
    comp_map = {comp.ref: comp for comp in (netlist.components if netlist else ())}

    components: dict[str, _DRCCompPlacement] = {}
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

            pos = getattr(placement, "position", (0.0, 0.0))
            if not isinstance(pos, (tuple, list)):
                pos = (0.0, 0.0)
            rot = getattr(placement, "rotation", 0)
            if not isinstance(rot, (int, float)):
                rot = 0

            side = getattr(comp, "initial_side", 0) if comp else 0
            layer = _SIDE_TO_LAYER.get(side, "F.Cu")

            components[ref] = _DRCCompPlacement(
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

    nets: dict[str, list[str]] = {}
    if netlist:
        for net in netlist.nets:
            if net.pins:
                nets[net.name] = [pin[0] for pin in net.pins]

    zones: dict[str, tuple] = {}
    if state.board:
        for zone in state.board.zones:
            zones[zone.name] = zone.bounds

    placement = _DRCPlacement(
        components=components,
        nets=nets,
        zones=zones,
        board_width=board_width,
        board_height=board_height,
    )

    constraints = _DRCConstraintSet(
        clearances=_DEFAULT_CLEARANCES,
        board_width=board_width,
        board_height=board_height,
    )

    return placement, constraints


class DeterministicPipeline:
    def __init__(self, stages: Sequence[Stage] | None = None, fence: DRCFence | None = None):
        self.stages: list[Stage] = list(stages) if stages else []
        self.fence = fence

    def run(self, initial_state: BoardState | None = None) -> BoardState:
        """Sequence the stages, threading the BoardState through.

        Orchestration-port unit U-E (Rust Orchestration Engine plan
        2026-08-09-001): the sequencing loop (including the per-stage fence
        invocation) is implemented in Rust (``temper-orchestration``'s
        ``DeterministicPipeline`` pyclass), which drives the stages through
        the Rust ``PipelineRunner<BoardState>``. The Python ``BoardState``
        object is threaded through the loop with object identity preserved
        for untouched fields; a stage that raises halts the run and
        re-raises the ORIGINAL exception. An empty stage list runs nothing
        (the state is returned unchanged). The per-stage compute is the
        shared shim stages (pinned individually by the D1..D7
        differentials); this method pins the LOOP.
        """
        return _to.DeterministicPipeline().run(
            self.stages or None, self.fence, initial_state
        )


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
    metadata: KiCadMetadata | None = None,
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

    # Build zone config from YAML config if available
    zone_config = None
    slot_spacing = 10.0  # Default: larger spacing to avoid overlaps
    max_clearance = 2.5  # Default: conservative for HV boards
    net_class_clearances = {}
    fixed_placements: dict[str, dict] = {}
    yaml_copper_zones: list[CopperZone] = []
    yaml_isolation_slots: list[IsolationSlot] = []  # @req(2026-06-23-007, R1)
    config_rules = None  # @req(2026-06-23-007, R2)
    net_priority = {}  # EXP-6: Explicit net routing priority
    placement_constraints = {}  # EXP-12: Placement validation constraints
    hv_exclusion_zones: list[Polygon] = []  # EXP-13: HV zones that signals must route around

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

    # R4a/R4c/R4d: Look for placement.channels.json in the run output dir.
    # Load once per pipeline run; record the count on the wrapper.
    channel_map: ChannelMap | None = load_channel_map_from_sidecar(output_dir)

    # U-E (Rust Orchestration Engine plan 2026-08-09-001): the ORDER is now
    # Rust. The factory's stage-list construction -- the D1->D7 ordered
    # construction of the 23 shim stages, the zone-aware / standard
    # slot-stage selection, the phased / standard component-stage selection
    # and the R4c sidecar injection (``channel_map`` into the phased stage
    # when it has a grid) -- is implemented in ``temper-orchestation``'s
    # ``DeterministicPipeline.create_drc_aware_pipeline_stages``. The
    # parameter EXTRACTION above (config/design_rules getattr chains, the
    # ``max(...) + 0.3`` margin, the DesignRules conversion, the PadInfo
    # conversion) stays Python; the extracted values feed the Rust factory.
    stages = _to.DeterministicPipeline.create_drc_aware_pipeline_stages(
        metadata=metadata,
        config=config,
        zone_aware=zone_aware,
        parsed_pads=parsed_pads,
        channel_map=channel_map,
        zone_config=zone_config,
        slot_spacing=slot_spacing,
        max_clearance=max_clearance,
        net_class_clearances=net_class_clearances,
        net_priority=net_priority,
        placement_constraints=placement_constraints,
        hv_exclusion_zones=hv_exclusion_zones,
        net_classes=config.net_classes if config else None,
        pad_sizes_for_stage=pad_sizes_for_stage,
        fixed_placements=fixed_placements,
        yaml_copper_zones=yaml_copper_zones,
        yaml_isolation_slots=yaml_isolation_slots,
        config_rules=config_rules,
        resolved_design_rules=design_rules,
    )

    pipeline = DeterministicPipeline(stages=stages)

    # Wrap in SidecarAwarePipeline so the per-instance sidecar load counter
    # can be asserted at end of run (R7e). The wrapper delegates everything
    # else to the underlying DeterministicPipeline.
    wrapper = SidecarAwarePipeline(
        stages=pipeline.stages,
        fence=pipeline.fence,
        channel_map=channel_map if (channel_map is not None and channel_map.has_grid()) else None,
    )
    if channel_map is not None and channel_map.has_grid():
        # Bump the counter exactly once per successful load.
        wrapper.record_sidecar_load()
    return wrapper


def create_legacy_pipeline():
    """Create legacy pipeline without DRC oracle integration."""
    from .stages import (
        ApplyPlacementsStage,
        ClearanceGridStage,
        ComponentAssignmentStage,
        ConnectivityValidationStage,
        DRCValidationStage,
        LayerAssignmentStage,
        NetOrderingStage,
        SlotGenerationStage,
        TrackDeduplicationStage,
        ViaDeduplicationStage,
        ViaValidationStage,
        ZoneAssignmentStage,
        ZoneGeometryStage,
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
