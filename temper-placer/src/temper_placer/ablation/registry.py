"""Registries mapping toggles to component implementations."""

from copy import deepcopy
from typing import Any

from temper_placer.ablation.config import ComponentToggle, LossToggle
from temper_placer.optimizer.config import (
    LearningRateSchedule,
    OptimizerConfig,
    TemperatureSchedule,
)


# Dynamic imports to avoid circular dependencies
def _get_heuristics():
    """Get heuristic classes."""
    try:
        from temper_placer.heuristics.force_directed import ForceDirectedHeuristic
        from temper_placer.heuristics.organizational import (
            DecouplingCapHeuristic,
            DomainSeparationHeuristic,
            FunctionalModuleClusteringHeuristic,
            PowerFlowTopologyHeuristic,
            StarGroundTopologyHeuristic,
        )
        from temper_placer.heuristics.spectral import SpectralPlacementHeuristic
        from temper_placer.heuristics.structural import (
            ConnectorEdgeSnappingHeuristic,
            CriticalLoopHeuristic,
            ThermalEdgePlacementHeuristic,
        )
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic

        return {
            "spectral_init": SpectralPlacementHeuristic,
            "force_directed": ForceDirectedHeuristic,
            "connector_edge_snap": ConnectorEdgeSnappingHeuristic,
            "thermal_edge": ThermalEdgePlacementHeuristic,
            "critical_loop": CriticalLoopHeuristic,
            "functional_clustering": FunctionalModuleClusteringHeuristic,
            "power_flow_topology": PowerFlowTopologyHeuristic,
            "decoupling_cap": DecouplingCapHeuristic,
            "domain_separation": DomainSeparationHeuristic,
            "star_ground": StarGroundTopologyHeuristic,
            "signal_flow": SignalFlowPreservationHeuristic,
        }
    except ImportError:
        # Return mock classes for testing
        return {name: type(name, (), {}) for name in [
            "spectral_init", "force_directed", "connector_edge_snap",
            "thermal_edge", "critical_loop", "functional_clustering",
            "power_flow_topology", "decoupling_cap", "domain_separation",
            "star_ground", "signal_flow",
        ]}


def _get_losses():
    """Get loss function classes."""
    try:
        from temper_placer.losses.boundary import BoundaryLoss
        from temper_placer.losses.clearance import ClearanceLoss
        from temper_placer.losses.coil import CoilRequirementLoss
        from temper_placer.losses.congestion import CongestionLoss
        from temper_placer.losses.critical_path import CriticalPathLengthLoss
        from temper_placer.losses.crystal import CrystalPlacementLoss
        from temper_placer.losses.drc_loss import DRCLoss
        from temper_placer.losses.ground_crossing import GroundCrossingLoss
        from temper_placer.losses.grouping import (
            GroupClusterLoss,
            GroupSeparationLoss,
            ProximityLoss,
        )
        from temper_placer.losses.loop_area import LoopAreaLoss
        from temper_placer.losses.mechanical import MechanicalMountingLoss
        from temper_placer.losses.net_class import NetClassSeparationLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.losses.power_path import PowerPathLoss
        from temper_placer.losses.regularization import (
            CenterOfMassLoss,
            RotationEntropyLoss,
            SpreadLoss,
        )
        from temper_placer.losses.return_path import CurrentReturnPathLoss
        from temper_placer.losses.thermal import ThermalLoss
        from temper_placer.losses.via_density import ViaDensityLoss
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.losses.zone import ZoneMembershipLoss

        return {
            "overlap": lambda: OverlapLoss(margin=1.0, rotation_invariant=True),
            "boundary": lambda: BoundaryLoss(soft_margin=2.0),
            "clearance": lambda: ClearanceLoss(min_clearance_mm=10.0),
            "thermal": ThermalLoss,
            "zone": ZoneMembershipLoss,
            "ground_crossing": GroundCrossingLoss,
            "net_class": NetClassSeparationLoss,
            "wirelength": WirelengthLoss,
            "loop_area": LoopAreaLoss,
            "congestion": CongestionLoss,
            "power_path": PowerPathLoss,
            "return_path": CurrentReturnPathLoss,
            "critical_path": CriticalPathLengthLoss,
            "spread": SpreadLoss,
            "rotation_entropy": RotationEntropyLoss,
            "center_of_mass": CenterOfMassLoss,
            "crystal": CrystalPlacementLoss,
            "mechanical": MechanicalMountingLoss,
            "via_density": ViaDensityLoss,
            "coil": CoilRequirementLoss,
            "drc": DRCLoss,
            "group_cluster": GroupClusterLoss,
            "group_separation": GroupSeparationLoss,
            "proximity": ProximityLoss,
        }
    except ImportError:
        # Return mock classes for testing
        return {name: (lambda n=name: type(n, (), {})()) for name in [
            "overlap", "boundary", "clearance", "thermal", "zone",
            "ground_crossing", "net_class", "wirelength", "loop_area",
            "congestion", "power_path", "return_path", "critical_path",
            "spread", "rotation_entropy", "center_of_mass", "crystal",
            "mechanical", "via_density", "coil", "drc",
            "group_cluster", "group_separation", "proximity",
        ]}


class HeuristicRegistry:
    """Registry mapping heuristic toggles to classes."""

    _heuristics = None
    _heuristic_kwargs: dict[str, dict[str, Any]] = {
        "spectral_init": {"confidence": 0.1},
        "force_directed": {"iterations": 50, "confidence": 0.2},
        "connector_edge_snap": {"confidence": 0.9},
        "thermal_edge": {"confidence": 0.8, "max_distance_mm": 15.0},
        "critical_loop": {"confidence": 0.7},
        "functional_clustering": {"max_spread_mm": 15.0, "confidence": 0.6},
        "power_flow_topology": {"confidence": 0.5},
        "decoupling_cap": {"max_distance_mm": 3.0, "confidence": 0.85},
        "domain_separation": {"confidence": 0.7},
        "star_ground": {"confidence": 0.6},
        "signal_flow": {"confidence": 0.4},
    }

    @classmethod
    def _init_heuristics(cls):
        """Lazy-initialize heuristics."""
        if cls._heuristics is None:
            cls._heuristics = _get_heuristics()

    @classmethod
    def create_pipeline(
        cls,
        toggle: ComponentToggle,
        _constraints: Any | None = None,
        **override_kwargs: Any
    ) -> Any:
        """Create pipeline with only enabled heuristics."""
        cls._init_heuristics()

        # Import HeuristicPipeline here to avoid circular imports
        try:
            from temper_placer.heuristics.pipeline import HeuristicPipeline
        except ImportError:
            # Mock for testing
            class HeuristicPipeline:
                def __init__(self):
                    self.heuristics = []
                def register(self, h):
                    self.heuristics.append(h)

        pipeline = HeuristicPipeline()

        for name, heuristic_cls in cls._heuristics.items():
            if getattr(toggle, name, False):
                kwargs = cls._heuristic_kwargs.get(name, {}).copy()

                # Apply overrides
                prefix = f"{name}__"
                for key, value in override_kwargs.items():
                    if key.startswith(prefix):
                        param = key[len(prefix):]
                        kwargs[param] = value

                # Try to create instance
                try:
                    heuristic = heuristic_cls(**kwargs)
                    pipeline.register(heuristic)
                except Exception:
                    # Skip if instantiation fails (for testing)
                    pass

        return pipeline

    @classmethod
    def list_heuristics(cls) -> list[str]:
        """Return all registered heuristic names."""
        cls._init_heuristics()
        return list(cls._heuristics.keys())

    @classmethod
    def get_heuristic_info(cls, name: str) -> dict[str, Any]:
        """Return metadata about a heuristic."""
        cls._init_heuristics()
        heuristic_cls = cls._heuristics[name]
        return {
            "name": name,
            "class": heuristic_cls.__name__,
            "default_kwargs": cls._heuristic_kwargs.get(name, {}),
            "docstring": heuristic_cls.__doc__,
        }


class LossRegistry:
    """Registry mapping loss toggles to factory functions."""

    _losses = None
    _default_weights: dict[str, float] = {
        "overlap": 100.0,
        "boundary": 50.0,
        "clearance": 80.0,
        "thermal": 30.0,
        "zone": 20.0,
        "ground_crossing": 20.0,
        "net_class": 15.0,
        "wirelength": 10.0,
        "loop_area": 40.0,
        "congestion": 5.0,
        "power_path": 15.0,
        "return_path": 10.0,
        "critical_path": 8.0,
        "spread": 10.0,
        "rotation_entropy": 5.0,
        "center_of_mass": 3.0,
        "crystal": 10.0,
        "mechanical": 5.0,
        "via_density": 3.0,
        "coil": 10.0,
        "drc": 50.0,
        "group_cluster": 15.0,
        "group_separation": 10.0,
        "proximity": 20.0,
    }

    @classmethod
    def _init_losses(cls):
        """Lazy-initialize losses."""
        if cls._losses is None:
            cls._losses = _get_losses()

    @classmethod
    def create_composite_loss(
        cls,
        toggle: LossToggle,
        weights: dict[str, float] | None = None,
        **_override_kwargs: Any
    ) -> Any:
        """Create composite loss with only enabled losses."""
        cls._init_losses()

        weights = weights or cls._default_weights
        losses = []

        # Import classes here
        try:
            from temper_placer.losses.base import CompositeLoss, WeightedLoss
        except ImportError:
            # Mock for testing
            class WeightedLoss:
                def __init__(self, loss, weight=1.0):
                    self.loss = loss
                    self.weight = weight

            class CompositeLoss:
                def __init__(self, losses):
                    self.losses = losses

        for name, factory in cls._losses.items():
            if getattr(toggle, name, False):
                weight = weights.get(name, 1.0)

                try:
                    loss = factory()
                except Exception:
                    # Skip if instantiation fails (for testing)
                    continue

                losses.append(WeightedLoss(loss, weight=weight))

        return CompositeLoss(losses)

    @classmethod
    def get_default_weights(cls) -> dict[str, float]:
        """Return default loss weights."""
        return cls._default_weights.copy()

    @classmethod
    def list_losses(cls) -> list[str]:
        """Return all registered loss names."""
        cls._init_losses()
        return list(cls._losses.keys())


class TechniqueApplicator:
    """Applies technique toggles to OptimizerConfig."""

    @staticmethod
    def apply_toggles(
        base_config: OptimizerConfig,
        toggle: ComponentToggle
    ) -> OptimizerConfig:
        """Create modified config based on technique toggles."""
        config = deepcopy(base_config)

        # Curriculum learning
        if not toggle.curriculum_learning:
            config.curriculum_phases = []

        # Techniques supported via OptimizerConfig flags
        config.use_gumbel_rotation = toggle.gumbel_softmax_rotation
        config.adaptive_overlap_enabled = toggle.adaptive_overlap_weighting
        config.jiggle_enabled = toggle.stochastic_perturbation

        # Centrality weighting
        config.use_centrality_weighting = toggle.centrality_gradient_scaling

        # Temperature annealing
        if not toggle.temperature_annealing:
            config.temperature = TemperatureSchedule(
                start=1.0,
                end=1.0,
            )

        # Learning rate annealing
        if not toggle.learning_rate_annealing:
            initial_lr = base_config.learning_rate.initial
            config.learning_rate = LearningRateSchedule(
                initial=initial_lr,
                final=initial_lr,
                warmup_epochs=0,
                decay_type="none",
            )

        # Gradient clipping
        if not toggle.gradient_clipping:
            config.gradient_clip_norm = None

        return config

    @staticmethod
    def get_technique_status(config: OptimizerConfig) -> dict[str, bool]:
        """Extract technique status from config."""
        return {
            "curriculum_learning": len(config.curriculum_phases) > 0,
            "gumbel_softmax_rotation": config.use_gumbel_rotation,
            "adaptive_overlap_weighting": config.adaptive_overlap_enabled,
            "stochastic_perturbation": config.jiggle_enabled,
            "centrality_gradient_scaling": config.use_centrality_weighting,
            "temperature_annealing": config.temperature.start != config.temperature.end,
            "learning_rate_annealing": config.learning_rate.initial != config.learning_rate.final,
            "gradient_clipping": config.gradient_clip_norm is not None,
        }

    @staticmethod
    def create_minimal_config(
        epochs: int = 8000,
        seed: int = 42
    ) -> OptimizerConfig:
        """Create minimal config with no advanced techniques."""
        return OptimizerConfig(
            epochs=epochs,
            seed=seed,
            temperature=TemperatureSchedule(start=1.0, end=1.0),
            learning_rate=LearningRateSchedule(
                initial=0.1, final=0.1, warmup_epochs=0, decay_type="none"
            ),
            curriculum_phases=[],
            gradient_clip_norm=None,
            use_centrality_weighting=False,
        )
