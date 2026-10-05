"""Render recorded R4 Rust results; no physics or acceptance logic lives here."""

import csv
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def read_rows(name: str) -> list[dict[str, str]]:
    with (ROOT / "results" / name).open(newline="") as source:
        return list(csv.DictReader(source))


def main() -> None:
    rows = [
        row
        for row in read_rows("spatial.csv")
        if row["case"] == "R3_target"
        and float(row["radial_k_W_mK"]) == 15
        and float(row["cap_mm"]) == 0.15
    ]
    labels = ["Uniform Ø8 mm", "Center Ø4 mm", "Rim r3–4 mm"]
    colors = ["#4778a4", "#357862", "#b26045"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), layout="constrained")
    for ax, field, title in zip(
        axes,
        ["t90_pan_s", "bias200_C"],
        ["90% of pan step · seconds", "Steady underread at 200°C · °C"],
        strict=True,
    ):
        values = [abs(float(row[field])) for row in rows]
        ax.bar(labels, values, color=colors, width=0.64)
        ax.axhline(2, color="#5c6065", linestyle="--", linewidth=1)
        ax.set_title(title, loc="left", fontsize=12, pad=14)
        ax.set_ylim(0, 8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=9)
        for i, value in enumerate(values):
            ax.text(i, value + 0.16, f"{value:.2f}", ha="center", fontsize=12)
    fig.suptitle(
        "The same conductance can give different sensor performance", fontsize=15
    )
    fig.supxlabel(
        "Simulation only · G = 0.08083 W/K · 0.15 mm steel cap · R3 loss targets",
        fontsize=10,
    )
    fig.savefig(ROOT / "comparison.png", dpi=170)
    plt.close(fig)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(row[key])}</td>"
            for key in ["gap", "status", "required_evidence"]
        )
        + "</tr>"
        for row in read_rows("closure_gates.csv")
    )
    html = (
        """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Temper sensor · R4</title>
<style>body{font:17px/1.55 system-ui,sans-serif;max-width:1060px;margin:50px auto;padding:0 24px;color:#253333;background:#faf9f5}h1{font-size:38px;line-height:1.15}h2{margin-top:34px}a{color:#22675a}img{width:100%;height:auto;background:white;border:1px solid #ddd}table{border-collapse:collapse;font-size:14px;width:100%}td,th{padding:10px 12px;text-align:left;border-bottom:1px solid #ccc;overflow-wrap:anywhere}.tag{color:#9a4933;font-weight:650}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}.card{padding:18px;background:#e9efea;border-radius:8px}.muted{color:#5d6563}code{font-size:90%}</style>
<p class="tag">SIMULATION &amp; TEST PREPARATION · HARDWARE NOT_RUN</p>
<h1>Close the model gaps before freezing the cartridge.</h1>
<p>R4 resolves heat spreading across the thin cap and exposes pressure loading from a sealed cavity. It also defines the remaining mechanical, assembly and detector acceptance gates.</p>
<div class="cards"><div class="card"><b>2.79 s / 2.29°C</b><br>Refined uniform-contact target. The former 1.89 s / 1.92°C result assumed an isothermal cap.</div><div class="card"><b>Contact location matters</b><br>Rim-only contact gives about 6.8 s / 5.3°C at the same total conductance.</div><div class="card"><b>Pressure must be designed</b><br>5 K gas heating over 50 mm² can impose 85 mN, versus the existing 10 mN parasitic budget.</div></div>
<h2>The thermal comparison</h2><img src="comparison.png" alt="Bar charts of pan-step response and steady underread for uniform, central and rim contact">
<p class="muted">These are controlled spatial hypotheses, not measured cookware results. The old 0.13 W/K scalar screen is insufficient for general contact. A thinner cap can make rim-contact response worse.</p>
<h2>The design consequence</h2><p>Keep the 0.15 mm cap for the next coupon. Establish contact near the RTD and reduce lead loss before selecting a thinner face. Define the complete pressure/liquid boundary before adding a seal. A jammed island still needs an independent diagnostic; fresh readings alone cannot establish contact.</p>
<h2>What remains open</h2><table><thead><tr><th>Gap</th><th>Status</th><th>Required evidence</th></tr></thead><tbody>"""
        + body
        + """</tbody></table>
<h2>Review and reproduce</h2><p><a href="README.md">Model and decisions</a> · <a href="CLOSURE.md">Full closure contract</a> · <a href="verification.md">Verification</a> · <a href="SOURCES.md">Sources and assumptions</a> · <a href="results/spatial.csv">Spatial results</a> · <a href="results/requirements.csv">Conditional inverse targets</a> · <a href="results/sealed_pressure.csv">Pressure screen</a> · <a href="run.sh">Reproduce</a></p>
<p class="muted">24 automated tests pass. No new sealed CAD, hardware measurements, firmware enablement or induction qualification is claimed.</p></html>"""
    )
    (ROOT / "report.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
