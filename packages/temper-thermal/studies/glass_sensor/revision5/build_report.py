"""Build the R5 review page and comparison plot from recorded model results."""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
GAP_LINKS = {
    "spatial_model": (
        "thermal/README.md",
        "Spatial cap and wire model; final CAD dimensions and masses",
    ),
    "sealed_pressure": (
        "safety/README.md",
        "Dry vented fixture selected; blocked path and liquid-head screens",
    ),
    "seal250C": (
        "safety/README.md",
        "Compound candidate retained; custom sealed assembly remains unresolved",
    ),
    "jam_detection": (
        "safety/README.md",
        "Mechanical challenge and optional electrical coupon; residual blind faults explicit",
    ),
    "retention": (
        "mechanical/README.md",
        "Captured head, motion poses, load-path and inspection package",
    ),
    "bond_leads": (
        "mechanical/README.md",
        "Moving bonded covers, weld regions and complete smooth wire routes",
    ),
    "whole_system_accuracy": (
        "validation/README.md",
        "Actual thermal cases plus a declared 1°C planning reserve",
    ),
    "induction": (
        "validation/TEST_PACKAGE.md",
        "CAD-derived roof screen, pickup sensitivities and prepared physical tests",
    ),
    "physical_qualification": (
        "validation/TEST_PACKAGE.md",
        "Raw evidence templates and inherited acquisition tools; no physical measurements",
    ),
}


def rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(newline="") as source:
        return list(csv.DictReader(source))


def main() -> None:
    comparisons = rows("thermal/results/comparison.csv")
    nominal = [
        r
        for r in comparisons
        if abs(float(r["force_N"]) - 0.218182) < 1e-8 and float(r["href_W_m2K"]) == 2000
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.5), layout="constrained")
    labels = ["Uniform", "Central patch", "Outer rim"]
    for ax, field, title in zip(
        axes,
        ["t90_pan_s", "bias200_C"],
        ["90% of pan step · seconds", "Steady thermal underread at 200°C · °C"],
        strict=True,
    ):
        for offset, variant, color in [(-0.18, "D8", "#6e8b99"), (0.18, "D6", "#a56640")]:
            points = [
                next(r for r in nominal if r["variant"] == variant and r["pattern"] == pattern)
                for pattern in ["Uniform", "Center", "Rim"]
            ]
            values = [abs(float(r[field])) for r in points]
            ax.bar(
                [i + offset for i in range(3)],
                values,
                width=0.34,
                label=f"{variant[1:]} mm",
                color=color,
            )
            for i, value in enumerate(values):
                ax.text(i + offset, value + 0.16, f"{value:.2f}", ha="center", fontsize=9)
        ax.axhline(2, color="#666", linestyle="--", linewidth=1)
        ax.set_xticks(range(3), labels)
        ax.set_title(title, loc="left", fontsize=12)
        ax.set_ylim(0, 12)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False)
    fig.suptitle(
        "Complete modeled cartridge: smaller is faster, contact still dominates", fontsize=14
    )
    fig.supxlabel(
        "Simulation only · same 0.218 N force and uncalibrated contact law · geometry-dependent conductance",
        fontsize=9,
    )
    fig.savefig(ROOT / "thermal-comparison.png", dpi=170)
    plt.close(fig)
    table_rows = []
    for variant in ["D8", "D6"]:
        r = next(r for r in nominal if r["variant"] == variant and r["pattern"] == "Uniform")
        table_rows.append(
            f"<tr><td>{variant[1:]} mm</td><td>{float(r['t90_pan_s']):.2f} s</td>"
            f"<td>{abs(float(r['bias200_C'])):.2f}°C</td></tr>"
        )
    gaps = json.loads((ROOT / "validation/gaps.json").read_text())["gaps"]
    gap_rows = []
    for gap in gaps:
        link, progress = GAP_LINKS[gap["id"]]
        gap_rows.append(
            f"<tr><td>{escape(gap['id'].replace('_', ' '))}</td><td>{escape(progress)}</td>"
            f'<td>{escape(gap["physical_result"])}</td><td><a href="{link}">Review evidence</a></td></tr>'
        )
    html = (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Temper sensor · R5 cartridge</title><style>body{font:17px/1.55 system-ui,sans-serif;max-width:1080px;margin:42px auto;padding:0 24px;background:#f8f7f3;color:#263533}h1{font-size:38px;line-height:1.15}h2{margin-top:34px}a{color:#25665a}img{max-width:100%;height:auto;background:white;border:1px solid #deded7}table{border-collapse:collapse;width:100%;font-size:15px}td,th{padding:12px;text-align:left;border-bottom:1px solid #ccd1ca}.tag{font-weight:650;color:#9b4d31}.callout{background:#e6ede7;padding:20px;border-radius:8px}.muted{color:#596660}.links{line-height:2}</style>
<p class="tag">R5 · CAD + SIMULATION + TEST PREPARATION · PHYSICAL NOT_RUN</p>
<h1>A complete modeled dry cartridge, with explicit release limits.</h1>
<p>Both the 8 mm reference and 6 mm comparison head now include protected cap-moving joins, attachment films, the hot anchor and full formed wire routes. The model reads the exported CAD properties, and an independent STEP check verifies cap volume and contact-face area.</p>
<div class="callout"><b>Decision:</b> use the 6 mm head as the next dry comparison coupon, retain 8 mm as its control. Neither meets the complete development targets under nominal assumptions. Sealed autonomous cooking remains blocked.</div>
<h2>CAD matching the model</h2><img src="cad-heads.png" alt="Direct STEP render comparing the 8 mm and 6 mm retained heads">
<p class="links"><a href="mechanical/R5-D6-rest.step">6 mm full assembly STEP</a> · <a href="mechanical/R5-D6-cap.step">6 mm cap STEP</a> · <a href="mechanical/R5-D8-rest.step">8 mm reference STEP</a> · <a href="mechanical/README.md">Motion poses and assembly details</a> · <a href="cad-parity.json">STEP/model parity checks</a></p>
<p class="muted">Geometry supports prototype preparation. Seal shapes and weld regions carry their stated qualification limits; the STEP is not a supplier-approved manufacturing release.</p>
<h2>What the complete model predicts</h2><table><thead><tr><th>Face</th><th>t90 of pan step</th><th>Steady thermal underread at 200°C</th></tr></thead><tbody>"""
        + "".join(table_rows)
        + """</tbody></table>
<p>These uniform-contact cases use the same force and contact-law assumptions. Smaller area changes contact conductance; it is not given the same heat transfer for free. The full wire, cover and support masses explain why these results are slower than earlier simplified models.</p>
<img src="thermal-comparison.png" alt="Response and thermal underread comparing both heads across uniform, center and rim contact">
<p class="muted">Thermal bias excludes the additional 1°C proposed calibration/readout/reference reserve. Contact coefficients, losses and material properties are uncalibrated. Central and rim patterns are hypotheses, not measured cookware populations. <a href="thermal/README.md">Model scope and finite-ramp results</a>.</p>
<h2>All remaining gaps addressed at the simulation/preparation stage</h2><table><thead><tr><th>Gap</th><th>R5 work</th><th>Physical evidence</th><th>Details</th></tr></thead><tbody>"""
        + "".join(gap_rows)
        + """</tbody></table>
<h2>The limiting design decisions</h2><p>The pressure study selects a remote open dry reference for the bench. It does not provide a spill seal. Mechanical challenge and pan-cap impedance experiments reduce some blind spots, but conductive contamination and correlated faults prevent treating them as proven local thermal-contact detection. Production control remains inhibited.</p>
<p>A complete supplier-reviewed liquid boundary and a demonstrable independent contact method are required before advancing this into a sealed cooker cartridge. Retention, forming, bond, weld and insulation qualification still need the physical evidence specified in the build/test package.</p>
<h2>Reproduce and inspect</h2><p class="links"><a href="README.md">R5 overview</a> · <a href="verification.md">Executed verification</a> · <a href="mechanical/thermal_geometry.csv">CAD scalar contract</a> · <a href="thermal/results/comparison.csv">Thermal results</a> · <a href="validation/results/current_thermal_budget.csv">Current whole-system planning budget</a> · <a href="validation/gaps.json">Nine-gap evidence ledger</a> · <a href="source-provenance.json">Full artifact identities</a></p></html>"""
    )
    (ROOT / "report.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
