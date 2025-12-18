"""Report generation for ablation study results."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from temper_placer.ablation.analysis import AblationAnalyzer, ComponentImportance, SynergyPair
from temper_placer.ablation.metrics import AggregatedMetrics
from temper_placer.ablation.visualization import AblationVisualizer

logger = logging.getLogger(__name__)

class AblationReportGenerator:
    """Generates HTML reports for ablation studies."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.visualizer = AblationVisualizer(output_dir / "plots")

    def generate(
        self,
        study_name: str,
        results: list[AggregatedMetrics],
        analyzer: AblationAnalyzer,
        experiment_histories: dict[str, list[dict[str, Any]]] | None = None
    ) -> Path:
        """Generate a complete HTML report."""
        importances = analyzer.rank_components_by_importance()
        synergies = analyzer.detect_synergies()

        # 1. Generate all plots
        self.visualizer.save_all_plots(results, analyzer, experiment_histories)

        # 2. Build HTML sections
        header = self._generate_header(study_name)
        summary = self._generate_summary(results, importances, synergies)
        plots_section = self._generate_plots_section()
        table_section = self._generate_table(results)
        footer = self._generate_footer()

        # 3. Combine and save
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ablation Study: {study_name}</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body>
    <div class="container">
        {header}
        {summary}
        {plots_section}
        {table_section}
        {footer}
    </div>
</body>
</html>
"""
        report_path = self.output_dir / "ablation_report.html"
        report_path.write_text(html_content)
        logger.info(f"Ablation report generated at {report_path}")
        return report_path

    def _generate_header(self, study_name: str) -> str:
        return f"""
        <header>
            <h1>Ablation Study Report: {study_name}</h1>
            <p class="timestamp">Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </header>
        """

    def _generate_summary(
        self,
        results: list[AggregatedMetrics],
        importances: list[ComponentImportance],
        synergies: list[SynergyPair]
    ) -> str:
        top_3 = importances[:3]
        top_findings = "".join([
            f"<li><strong>{i.component_name}</strong> ({i.component_type}): "
            f"Impact score {i.importance_score:.1f}, "
            f"p-value {i.p_value:.4f}</li>" for i in top_3
        ])

        significant_synergies = [s for s in synergies if s.is_significant]
        synergy_findings = "".join([
            f"<li><strong>{s.component_a} + {s.component_b}</strong>: "
            f"{s.interaction_type} (score {s.interaction_score:.4f})</li>"
            for s in significant_synergies[:3]
        ]) or "<li>No significant synergies detected.</li>"

        return f"""
        <section class="summary">
            <h2>Executive Summary</h2>
            <div class="summary-grid">
                <div class="summary-card">
                    <h3>Scope</h3>
                    <ul>
                        <li>Total Experiments: {len(results)}</li>
                        <li>Total Runs: {sum(r.n_seeds for r in results)}</li>
                    </ul>
                </div>
                <div class="summary-card">
                    <h3>Top 3 Components</h3>
                    <ul>{top_findings}</ul>
                </div>
                <div class="summary-card">
                    <h3>Top Interactions</h3>
                    <ul>{synergy_findings}</ul>
                </div>
            </div>
        </section>
        """

    def _generate_plots_section(self) -> str:
        plot_files = [
            ("metric_comparison.html", "Metric Comparison"),
            ("importance_ranking.html", "Component Importance"),
            ("drc_pass_rate.html", "DRC Pass Rate"),
            ("synergy_heatmap.html", "Interaction Heatmap"),
            ("pareto_frontier.html", "Pareto Frontier (WL vs Loss)"),
            ("seed_stability.html", "Seed Stability"),
            ("convergence_comparison.html", "Convergence Curves"),
        ]

        plot_cards = ""
        for filename, title in plot_files:
            if (self.output_dir / "plots" / filename).exists():
                plot_cards += f"""
                <div class="plot-card">
                    <h3>{title}</h3>
                    <iframe src="plots/{filename}" width="100%" height="500px" frameborder="0"></iframe>
                </div>
                """

        return f"""
        <section class="plots">
            <h2>Visualization</h2>
            <div class="plots-grid">
                {plot_cards}
            </div>
        </section>
        """

    def _generate_table(self, results: list[AggregatedMetrics]) -> str:
        rows = ""
        for r in results:
            rows += f"""
            <tr>
                <td>{r.experiment_name}</td>
                <td>{r.final_loss_mean:.4f} ± {r.final_loss_std:.4f}</td>
                <td>{r.drc_pass_rate*100:.1f}%</td>
                <td>{r.wirelength_mean:.1f}</td>
                <td>{r.convergence_epoch_mean:.0f}</td>
                <td>{r.elapsed_time_mean:.1f}s</td>
            </tr>
            """

        return f"""
        <section class="details">
            <h2>Experiment Details</h2>
            <table>
                <thead>
                    <tr>
                        <th>Experiment</th>
                        <th>Final Loss</th>
                        <th>DRC Pass</th>
                        <th>Wirelength</th>
                        <th>Conv. Epoch</th>
                        <th>Runtime</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </section>
        """

    def _generate_footer(self) -> str:
        return """
        <footer>
            <p>Ablation Study Framework | Temper Project</p>
        </footer>
        """

    def _get_css(self) -> str:
        return """
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #333; background: #f5f7f9; margin: 0; padding: 0; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header { text-align: center; margin-bottom: 40px; padding-bottom: 20px; border-bottom: 2px solid #ddd; }
        h1 { margin: 0; color: #2c3e50; }
        .timestamp { color: #7f8c8d; font-size: 0.9em; }
        section { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 30px; }
        h2 { border-left: 5px solid #3498db; padding-left: 15px; margin-top: 0; color: #2c3e50; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .summary-card { background: #fcfcfc; border: 1px solid #eee; padding: 15px; border-radius: 6px; }
        .summary-card h3 { margin-top: 0; font-size: 1.1em; color: #34495e; }
        .plots-grid { display: grid; grid-template-columns: 1fr; gap: 30px; }
        .plot-card { border: 1px solid #eee; border-radius: 8px; padding: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; color: #7f8c8d; font-weight: 600; text-transform: uppercase; font-size: 0.8em; }
        tr:hover { background: #f9f9f9; }
        footer { text-align: center; color: #bdc3c7; font-size: 0.8em; margin-top: 50px; padding-bottom: 30px; }
        """
