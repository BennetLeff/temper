"""Visualization tools for ablation study results."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

from temper_placer.ablation.analysis import AblationAnalyzer, ComponentImportance, SynergyPair
from temper_placer.ablation.metrics import AggregatedMetrics

logger = logging.getLogger(__name__)

def check_plotly():
    """Check if plotly is available."""
    if not PLOTLY_AVAILABLE:
        raise ImportError("Plotly is required for ablation visualization. Install with 'pip install plotly'.")

class AblationVisualizer:
    """Generates plots for ablation study analysis."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        check_plotly()

    def plot_metric_comparison(
        self,
        results: list[AggregatedMetrics],
        metric_name: str = "final_loss",
        title: str | None = None
    ) -> go.Figure:
        """Compare a metric across all experiments.

        Args:
            results: Aggregated metrics for all experiments.
            metric_name: Field name in AggregatedMetrics (e.g., 'final_loss_mean').
            title: Plot title.
        """
        data = []
        for r in results:
            mean_val = getattr(r, f"{metric_name}_mean", getattr(r, metric_name, 0.0))
            std_val = getattr(r, f"{metric_name}_std", 0.0)
            data.append({
                "Experiment": r.experiment_name,
                "Value": mean_val,
                "Error": std_val
            })

        df = pd.DataFrame(data).sort_values("Value")

        fig = px.bar(
            df, x="Value", y="Experiment",
            error_x="Error",
            title=title or f"Comparison: {metric_name.replace('_', ' ').title()}",
            orientation='h',
            color="Value",
            color_continuous_scale="Viridis"
        )

        fig.update_layout(height=max(400, len(results) * 30))
        return fig

    def plot_importance_ranking(
        self,
        importances: list[ComponentImportance],
        title: str = "Component Importance Ranking"
    ) -> go.Figure:
        """Plot component importance scores.

        Args:
            importances: List of importance metrics from AblationAnalyzer.
        """
        df = pd.DataFrame([
            {
                "Component": i.component_name,
                "Type": i.component_type,
                "Importance": i.importance_score,
                "Significant": i.is_significant
            } for i in importances
        ]).sort_values("Importance", ascending=True)

        fig = px.bar(
            df, x="Importance", y="Component",
            color="Type",
            pattern_shape="Significant",
            title=title,
            orientation='h',
            category_orders={"Type": ["heuristic", "loss", "technique"]}
        )

        fig.update_layout(height=max(400, len(importances) * 30))
        return fig

    def plot_convergence_comparison(
        self,
        experiment_histories: dict[str, list[dict[str, Any]]],
        title: str = "Convergence Comparison"
    ) -> go.Figure:
        """Compare loss curves across experiments.

        Args:
            experiment_histories: Map of experiment name to list of run histories.
        """
        fig = go.Figure()

        for exp_name, histories in experiment_histories.items():
            if not histories:
                continue

            # Aggregate histories across seeds
            # Assuming all histories have same epochs
            all_losses = []
            epochs = histories[0].get("epochs", [])
            for h in histories:
                all_losses.append(h.get("losses", []))

            all_losses = np.array(all_losses, dtype=object)
            mean_loss = np.mean(all_losses, axis=0)
            std_loss = np.std(all_losses, axis=0)

            # Add mean line
            fig.add_trace(go.Scatter(
                x=epochs, y=mean_loss,
                mode='lines',
                name=exp_name,
                line={"width": 2}
            ))

            # Add shaded CI area
            fig.add_trace(go.Scatter(
                x=np.concatenate([epochs, epochs[::-1]]),
                y=np.concatenate([mean_loss + std_loss, (mean_loss - std_loss)[::-1]]),
                fill='toself',
                fillcolor='rgba(0,100,80,0.2)',
                line={"color": 'rgba(255,255,255,0)'},
                hoverinfo="skip",
                showlegend=False
            ))

        fig.update_layout(
            title=title,
            xaxis_title="Epoch",
            yaxis_title="Loss",
            yaxis_type="log",
            hovermode="x unified"
        )
        return fig

    def plot_drc_pass_rate(
        self,
        results: list[AggregatedMetrics],
        title: str = "DRC Pass Rate by Experiment"
    ) -> go.Figure:
        """Plot DRC pass rates across experiments."""
        df = pd.DataFrame([
            {
                "Experiment": r.experiment_name,
                "Pass Rate": r.drc_pass_rate * 100
            } for r in results
        ]).sort_values("Pass Rate")

        fig = px.bar(
            df, x="Pass Rate", y="Experiment",
            title=title,
            orientation='h',
            range_x=[0, 100],
            color="Pass Rate",
            color_continuous_scale="RdYlGn"
        )
        return fig

    def plot_synergy_heatmap(
        self,
        synergies: list[SynergyPair],
        title: str = "Component Interaction (Synergy) Heatmap"
    ) -> go.Figure:
        """Plot synergy/conflict heatmap between components."""
        # Get unique components
        comps = sorted(set(
            [s.component_a for s in synergies] + [s.component_b for s in synergies]
        ))

        if not comps:
            # Empty plot
            return go.Figure().update_layout(title="No synergy data available")

        n = len(comps)
        matrix = np.zeros((n, n))
        comp_map = {c: i for i, c in enumerate(comps)}

        for s in synergies:
            i, j = comp_map[s.component_a], comp_map[s.component_b]
            matrix[i, j] = s.interaction_score
            matrix[j, i] = s.interaction_score # Symmetric

        fig = px.imshow(
            matrix,
            x=comps, y=comps,
            color_continuous_scale="RdBu_r",
            color_continuous_midpoint=0,
            title=title,
            labels={"color": "Interaction Score"}
        )
        return fig

    def plot_pareto_frontier(
        self,
        results: list[AggregatedMetrics],
        x_metric: str = "wirelength_mean",
        y_metric: str = "final_loss_mean",
        title: str = "Pareto Frontier (Wirelength vs Loss)"
    ) -> go.Figure:
        """Scatter plot of two metrics to show trade-offs."""
        df = pd.DataFrame([
            {
                "Experiment": r.experiment_name,
                "X": getattr(r, x_metric),
                "Y": getattr(r, y_metric),
                "DRC Pass Rate": r.drc_pass_rate
            } for r in results
        ])

        fig = px.scatter(
            df, x="X", y="Y",
            text="Experiment",
            color="DRC Pass Rate",
            size_max=15,
            title=title,
            labels={"X": x_metric.replace("_", " ").title(), "Y": y_metric.replace("_", " ").title()}
        )

        fig.update_traces(textposition='top center')
        return fig

    def plot_seed_stability(
        self,
        results: list[AggregatedMetrics],
        metric_name: str = "final_loss",
        title: str = "Seed Stability (Distribution)"
    ) -> go.Figure:
        """Box plot showing distribution across seeds for each experiment."""
        data = []
        for r in results:
            values = r.seed_values.get(metric_name, [])
            for v in values:
                data.append({
                    "Experiment": r.experiment_name,
                    "Value": v
                })

        if not data:
            return go.Figure().update_layout(title="No seed data available")

        df = pd.DataFrame(data)

        fig = px.box(
            df, x="Experiment", y="Value",
            color="Experiment",
            title=title,
            points="all" # Show all points
        )

        fig.update_layout(xaxis_tickangle=-45)
        return fig

    def save_all_plots(self,
                       results: list[AggregatedMetrics],
                       analyzer: AblationAnalyzer,
                       experiment_histories: dict[str, list[dict[str, Any]]] | None = None):
        """Generate and save all plots to output directory."""
        if not self.output_dir:
            logger.warning("No output directory specified, not saving plots.")
            return

        importances = analyzer.rank_components_by_importance()
        synergies = analyzer.detect_synergies()

        plots = [
            ("metric_comparison.html", self.plot_metric_comparison(results)),
            ("importance_ranking.html", self.plot_importance_ranking(importances)),
            ("drc_pass_rate.html", self.plot_drc_pass_rate(results)),
            ("synergy_heatmap.html", self.plot_synergy_heatmap(synergies)),
            ("pareto_frontier.html", self.plot_pareto_frontier(results)),
            ("seed_stability.html", self.plot_seed_stability(results)),
        ]

        if experiment_histories:
            plots.append(("convergence_comparison.html", self.plot_convergence_comparison(experiment_histories)))

        for filename, fig in plots:
            fig.write_html(self.output_dir / filename)
            logger.info(f"Saved plot to {self.output_dir / filename}")
