"""Statistical analysis for ablation study results."""

from dataclasses import dataclass

import numpy as np
from scipy import stats

from temper_placer.ablation.metrics import AggregatedMetrics


@dataclass
class ComponentImportance:
    """Importance ranking for a single component."""

    # Identifiers
    component_name: str
    """Name of the component (e.g., 'spectral_init', 'overlap')"""

    component_type: str
    """Type of component: 'heuristic', 'loss', or 'technique'"""

    # Impact metrics (ablation vs baseline)
    loss_delta: float
    """Absolute change in final loss (positive = removal hurts)"""

    loss_delta_pct: float
    """Percentage change in final loss"""

    drc_pass_rate_delta: float
    """Change in DRC pass rate (-1.0 to 1.0)"""

    wirelength_delta_pct: float
    """Percentage change in wirelength"""

    loop_area_delta_pct: float
    """Percentage change in loop area violations"""

    convergence_delta_pct: float
    """Percentage change in convergence epoch"""

    # Statistical significance
    p_value: float
    """p-value from Welch's t-test (0.0 to 1.0)"""

    is_significant: bool
    """Whether p < 0.05 (statistically significant)"""

    effect_size: float
    """Cohen's d effect size"""

    effect_magnitude: str
    """Effect magnitude: 'negligible', 'small', 'medium', 'large'"""

    # Ranking
    importance_score: float
    """Composite importance score (higher = more important)"""

    rank: int
    """Ranking position (1 = most important)"""

    # Metadata
    n_seeds: int
    """Number of seeds used in computation"""

    test_cases: list[str]
    """Test cases analyzed"""


@dataclass
class SynergyPair:
    """Detected synergy or conflict between two components."""

    # Identifiers
    component_a: str
    """First component name"""

    component_b: str
    """Second component name"""

    interaction_type: str
    """Type of interaction: 'synergy' or 'conflict'"""

    # Interaction metrics
    interaction_score: float
    """Interaction strength (positive = synergy, negative = conflict)"""

    interaction_magnitude: str
    """Magnitude: 'weak', 'moderate', 'strong'"""

    # Evidence
    baseline_loss: float
    """Loss with neither component"""

    a_only_loss: float
    """Loss with only component A"""

    b_only_loss: float
    """Loss with only component B"""

    both_loss: float
    """Loss with both components"""

    expected_both: float
    """Expected loss if additive (no interaction)"""

    # Statistical
    p_value: float
    """p-value for interaction significance"""

    is_significant: bool
    """Whether p < 0.05"""

    # Interpretation
    description: str
    """Human-readable explanation of synergy/conflict"""


class AblationAnalyzer:
    """Statistical analysis of ablation study results."""

    def __init__(self, aggregated_results: list[AggregatedMetrics]):
        """Initialize analyzer with aggregated metrics.

        Args:
            aggregated_results: List of AggregatedMetrics from MetricAggregator
        """
        self.results = aggregated_results
        self._baseline = None
        self._ablations = {}
        self._minimal = None
        self._additions = {}
        self._combinations = {}

        # Organize results by type
        for result in aggregated_results:
            if result.experiment_name == "baseline":
                self._baseline = result
            elif result.experiment_name == "minimal":
                self._minimal = result
            elif result.experiment_name.startswith("add_"):
                comp_name = result.experiment_name.replace("add_", "")
                self._additions[comp_name] = result
            elif result.experiment_name.startswith("ablate_"):
                comp_name = result.experiment_name.replace("ablate_", "")
                self._ablations[comp_name] = result
            elif "_and_" in result.experiment_name:
                self._combinations[result.experiment_name] = result

    def _get_component_type(self, component_name: str) -> str:
        """Determine component type from name.

        Args:
            component_name: Name of component

        Returns:
            'heuristic', 'loss', or 'technique'
        """
        heuristics = {
            "spectral_init",
            "force_directed",
            "connector_edge_snap",
            "thermal_edge",
            "critical_loop",
            "functional_clustering",
            "power_flow_topology",
            "decoupling_cap",
            "domain_separation",
            "star_ground",
            "signal_flow",
        }

        losses = {
            "overlap",
            "boundary",
            "clearance",
            "thermal",
            "zone",
            "ground_crossing",
            "net_class",
            "wirelength",
            "loop_area",
            "congestion",
            "power_path",
            "return_path",
            "critical_path",
            "spread",
            "rotation_entropy",
            "center_of_mass",
            "crystal",
            "mechanical",
            "via_density",
            "coil",
            "drc",
            "group_cluster",
            "group_separation",
            "proximity",
        }

        techniques = {
            "curriculum_learning",
            "gumbel_softmax_rotation",
            "adaptive_overlap_weighting",
            "stochastic_perturbation",
            "centrality_gradient_scaling",
            "temperature_annealing",
            "learning_rate_annealing",
            "gradient_clipping",
        }

        if component_name in heuristics:
            return "heuristic"
        elif component_name in losses:
            return "loss"
        elif component_name in techniques:
            return "technique"
        else:
            return "unknown"

    def _compute_importance(
        self,
        component_name: str,
        ablated: AggregatedMetrics,
        baseline: AggregatedMetrics,
        weights: dict[str, float] | None = None,
    ) -> ComponentImportance:
        """Compute importance for a single component.

        Args:
            component_name: Name of component
            ablated: Metrics with component ablated
            baseline: Baseline metrics
            weights: Weights for different metrics

        Returns:
            ComponentImportance with all statistics
        """
        if weights is None:
            weights = {
                "loss": 0.4,
                "drc": 0.2,
                "wirelength": 0.15,
                "loop_area": 0.15,
                "convergence": 0.1,
            }

        # Loss delta
        loss_delta = ablated.final_loss_mean - baseline.final_loss_mean
        loss_delta_pct = (
            (loss_delta / baseline.final_loss_mean * 100)
            if baseline.final_loss_mean != 0
            else 0
        )

        # DRC delta
        drc_delta = (
            ablated.drc_pass_rate - baseline.drc_pass_rate
        )

        # Wirelength delta
        wl_delta = ablated.wirelength_mean - baseline.wirelength_mean
        wl_delta_pct = (
            (wl_delta / baseline.wirelength_mean * 100)
            if baseline.wirelength_mean != 0
            else 0
        )

        # Loop area delta
        loop_delta = (
            ablated.loop_area_violation_mean - baseline.loop_area_violation_mean
        )
        loop_delta_pct = (
            (loop_delta / max(baseline.loop_area_violation_mean, 0.01) * 100)
            if baseline.loop_area_violation_mean > 0
            else 0
        )

        # Convergence delta
        conv_delta = (
            ablated.convergence_epoch_mean - baseline.convergence_epoch_mean
        )
        conv_delta_pct = (
            (conv_delta / baseline.convergence_epoch_mean * 100)
            if baseline.convergence_epoch_mean > 0
            else 0
        )

        # Statistical test (Welch's t-test)
        baseline_vals = np.array(
            baseline.seed_values.get("final_loss", [baseline.final_loss_mean])
        )
        ablated_vals = np.array(
            ablated.seed_values.get("final_loss", [ablated.final_loss_mean])
        )

        try:
            t_stat, p_value = stats.ttest_ind(baseline_vals, ablated_vals, equal_var=False)
        except Exception:
            p_value = 1.0  # Default to not significant on error

        # Effect size (Cohen's d)
        pooled_std = np.sqrt(
            (baseline.final_loss_std**2 + ablated.final_loss_std**2) / 2
        )
        effect_size = (
            abs(loss_delta) / pooled_std if pooled_std > 0 else 0
        )

        # Effect magnitude thresholds (Cohen's conventions)
        if effect_size < 0.2:
            effect_magnitude = "negligible"
        elif effect_size < 0.5:
            effect_magnitude = "small"
        elif effect_size < 0.8:
            effect_magnitude = "medium"
        else:
            effect_magnitude = "large"

        # Composite importance score
        importance_score = (
            weights["loss"] * max(0, loss_delta_pct)
            + weights["drc"] * max(0, -drc_delta * 100)
            + weights["wirelength"] * max(0, wl_delta_pct)
            + weights["loop_area"] * max(0, loop_delta_pct)
            + weights["convergence"] * max(0, conv_delta_pct)
        )

        return ComponentImportance(
            component_name=component_name,
            component_type=self._get_component_type(component_name),
            loss_delta=loss_delta,
            loss_delta_pct=loss_delta_pct,
            drc_pass_rate_delta=drc_delta,
            wirelength_delta_pct=wl_delta_pct,
            loop_area_delta_pct=loop_delta_pct,
            convergence_delta_pct=conv_delta_pct,
            p_value=p_value,
            is_significant=p_value < 0.05,
            effect_size=effect_size,
            effect_magnitude=effect_magnitude,
            importance_score=importance_score,
            rank=0,  # Set after sorting
            n_seeds=baseline.n_seeds,
            test_cases=[baseline.test_case],
        )

    def rank_components_by_importance(
        self,
        metric_weights: dict[str, float] | None = None,
    ) -> list[ComponentImportance]:
        """Rank all components by importance (vs baseline).

        Args:
            metric_weights: Weights for different metrics

        Returns:
            List of ComponentImportance sorted by importance descending
        """
        if self._baseline is None:
            raise ValueError("No baseline experiment found in results")

        importances = []

        # Compute importance for each ablation
        for component, ablated in self._ablations.items():
            importance = self._compute_importance(
                component, ablated, self._baseline, metric_weights
            )
            importances.append(importance)

        # Sort by importance score (descending)
        importances.sort(key=lambda x: x.importance_score, reverse=True)

        # Assign ranks
        for rank, importance in enumerate(importances, 1):
            importance.rank = rank

        return importances

    def detect_synergies(
        self, significance_threshold: float = 0.05
    ) -> list[SynergyPair]:
        """Detect synergistic and conflicting component pairs.

        Args:
            significance_threshold: p-value threshold for significance

        Returns:
            List of SynergyPair objects
        """
        if self._minimal is None or not self._additions or not self._combinations:
            return []

        synergies = []

        # Iterate through combinations
        for combo_name, combo_result in self._combinations.items():
            # Parse component names from combo name
            # Format: "add_comp_a_and_comp_b"
            parts = (
                combo_name.replace("add_", "").split("_and_")
            )
            if len(parts) != 2:
                continue

            comp_a, comp_b = parts

            # Get addition results
            if comp_a not in self._additions or comp_b not in self._additions:
                continue

            a_only = self._additions[comp_a]
            b_only = self._additions[comp_b]

            # Effects of adding each component individually
            a_effect = self._minimal.final_loss_mean - a_only.final_loss_mean
            b_effect = self._minimal.final_loss_mean - b_only.final_loss_mean

            # Expected effect if additive (no interaction)
            expected_both = self._minimal.final_loss_mean - (a_effect + b_effect)

            # Actual combined effect
            actual_both = combo_result.final_loss_mean

            # Interaction: positive = synergy, negative = conflict
            interaction = expected_both - actual_both

            # Magnitude
            base_effect = abs(a_effect) + abs(b_effect)
            if base_effect > 0:
                interaction_ratio = abs(interaction) / base_effect
                if interaction_ratio < 0.1:
                    magnitude = "weak"
                elif interaction_ratio < 0.3:
                    magnitude = "moderate"
                else:
                    magnitude = "strong"
            else:
                magnitude = "weak"

            # Statistical test
            try:
                combo_vals = np.array(
                    combo_result.seed_values.get(
                        "final_loss", [combo_result.final_loss_mean]
                    )
                )
                expected_vals = np.array([expected_both] * len(combo_vals))
                _, p_value = stats.ttest_ind(combo_vals, expected_vals, equal_var=False)
            except Exception:
                p_value = 1.0

            # Description
            if interaction > 0:
                desc = (
                    f"{comp_a} and {comp_b} together perform better than expected "
                    "(synergy)"
                )
                interaction_type = "synergy"
            else:
                desc = (
                    f"{comp_a} and {comp_b} have redundant or conflicting effects "
                    "(conflict)"
                )
                interaction_type = "conflict"

            synergy = SynergyPair(
                component_a=comp_a,
                component_b=comp_b,
                interaction_type=interaction_type,
                interaction_score=interaction,
                interaction_magnitude=magnitude,
                baseline_loss=self._minimal.final_loss_mean,
                a_only_loss=a_only.final_loss_mean,
                b_only_loss=b_only.final_loss_mean,
                both_loss=actual_both,
                expected_both=expected_both,
                p_value=p_value,
                is_significant=p_value < significance_threshold,
                description=desc,
            )

            synergies.append(synergy)

        return synergies
