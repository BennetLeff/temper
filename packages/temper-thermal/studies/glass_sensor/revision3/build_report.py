"""Render the recorded Rust results; does not implement physics."""

from __future__ import annotations

import csv
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main() -> None:
    with (ROOT / "thermal/results/comparison.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    chosen = [
        "R2_resolved_hooks",
        "R3_Cu_hot_anchor",
        "R3_Cu_anchor_contact_target",
        "R3_Cu_anchor_contact_loss_target",
    ]
    labels = [
        "R2 · hooks resolved",
        "R3 · copper anchor",
        "+ contact target",
        "+ contact & loss targets",
    ]
    nominal = []
    for case in chosen:
        candidates = [r for r in rows if r["condition"] == "nominal" and r["case"] == case]
        if len(candidates) != 1:
            raise ValueError(f"Expected one nominal row for {case}")
        nominal.append(candidates[0])
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), layout="constrained")
    fig.patch.set_facecolor("#f6f3eb")
    for ax, key, title in zip(
        axes,
        ["t90_pan_s", "error200_C"],
        ["90% of pan step · seconds", "Thermal underread at 200°C · °C"],
        strict=True,
    ):
        values = [abs(float(r[key])) for r in nominal]
        ax.set_facecolor("#f6f3eb")
        bars = ax.barh(
            labels, values, color=["#8b9496", "#257469", "#91b9a7", "#c6ddc4"], height=0.58
        )
        for i in (2, 3):
            bars[i].set_hatch("//")
        ax.invert_yaxis()
        ax.set_xlim(0, max(values) * 1.22)
        ax.set_title(title, loc="left", fontsize=13, pad=16)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        for i, value in enumerate(values):
            ax.text(value + 0.06, i, f"{value:.2f}", va="center", fontweight="bold")
    fig.savefig(ROOT / "comparison.png", dpi=170)
    fig.savefig(ROOT / "comparison.svg")
    svg = ROOT / "comparison.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)
    table = "".join(
        f"<tr><td>{escape(label)}</td><td>{float(r['t90_final_s']):.2f} s</td><td>{float(r['t90_pan_s']):.2f} s</td><td>{-float(r['error200_C']):.2f}°C</td></tr>"
        for label, r in zip(labels, nominal, strict=True)
    )
    html = (
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Temper · Sensor R3</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f6f3eb;color:#213c37;font:17px/1.6 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:45px 28px 70px}h1{font-size:clamp(36px,5vw,58px);line-height:1.1;letter-spacing:-.04em;max-width:900px}h2{margin-top:40px;font-size:27px}h3{font-size:20px;margin:0}a{color:#116c60;text-underline-offset:3px}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:700}.lead{font-size:22px;max-width:870px}.notice{padding:18px 22px;background:#e9dfc9;border-left:4px solid #b87831}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.card{padding:22px;border:1px solid #d0d5ca;background:#fffdf6;border-radius:8px}.card p{font-size:15px}.figure{width:100%}.drawing{width:100%;height:470px;object-fit:contain;background:white}.caption,footer{font-size:13px;color:#596861}table{width:100%;border-collapse:collapse;font-size:15px}td,th{padding:12px 9px;text-align:left;border-bottom:1px solid #d0d5ca}th{font-size:12px;text-transform:uppercase}.scroll{overflow:auto}li{margin:9px 0}footer{margin-top:38px;padding-top:18px;border-top:1px solid #d0d5ca}@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:24px 18px}}</style></head><body><main>
<div class="eyebrow">Temper engineering · R3 · 4 October 2026</div><h1>Intercept the lead heat loss.<br>Keep the retention gap honest.</h1><p class="lead">A larger catch gap and a hot copper-lead anchor are now dimensioned in CAD. The next thermal target is measurable contact conductance, with explicit limits for wiring and seal losses.</p>
<p class="notice"><b>Dry engineering coupon, not validated hardware.</b> The best copper target predicts1.78 s to its own endpoint,1.89 s to90% of the pan step and1.92°C thermal underread. It requires better contact and lower direct loss that have not been demonstrated. Geometry changes alone do not achieve those numbers.</p>
<h2>What changed physically</h2><div class="grid"><article class="card"><h3>Retention clearance:0.05 →0.20 mm</h3><p>CAD identifies0.720 mm² of opposing hook/ceramic area. Resolving its thin air gap adds a heat path absent from the previous explicit network. The proposed clearance reduces the modeled hook path about68% with less than1% extra cap mass. It also increases free cap lift, so lead slack, catch loading and wear need retesting.</p></article><article class="card"><h3>Keep copper; anchor it to the cap</h3><p>A1.3×1.5×0.42 mm cap-side coupon locates four intact PFA-insulated copper wires. A separate thermal node includes anchor resistance and mass. It redirects part of the cold-wire heat load from the RTD to the cap. Ceramic/PFA contact, jacket creep and the full formed route remain unqualified.</p></article></div>
<h2>The gains and the conditions</h2><img class="figure" src="comparison.png" alt="Thermal comparisons; hatched bars require unverified improved contact and loss targets."><div class="scroll"><table><thead><tr><th>Modeled case</th><th>90% own endpoint</th><th>90% pan step</th><th>200°C underread</th></tr></thead><tbody>"""
        + table
        + """</tbody></table></div>
<p class="caption">Hatched bars include unachieved contact/loss targets. Force0.218182 N from the previous mechanical model; full effective area; M222 unchanged. Step pan25→100°C with glass/body25°C. DC pan/glass/body200/80/60°C. Underread excludes sensor tolerance and readout error. <a href="README.md">Full model and comparison definitions</a>.</p>
<p>The refined R2 model predicts4.80°C underread, versus the earlier4.42°C estimate, because the hook gap is now represented. Its split cap/hook mass also changes the normalized response. All historical evidence is preserved; this is a refinement with uncertain parameters, not a newly measured baseline.</p>
<h2>Replace “better contact” with an experiment</h2><p>The copper target needs an effective pan-to-cap conductance of at least <b>0.077 W/K</b> for≤2 s to90% of the pan step and≤2°C thermal bias under favorable assumed loss boundaries. With stronger wire cooling and an added0.0002 W/K seal path, that minimum rises to <b>0.124 W/K</b>.</p><p>A proposed <b>0.13 W/K coupon screen</b> therefore has meaning only alongside the anchor≥0.003 W/K and other direct-loss≤0.0002 W/K targets. It is not an approved product accuracy limit. Qualification needs independent parameter measurements and uncertainty.</p>
<p class="notice">The nominal margin is small. At lower pan depression the copper target gives2.37 s /2.57°C; weak contact gives4.15 s /4.40°C. Adding only0.0002 W/K of seal leakage raises nominal underread1.92→2.26°C. The sealed version must be re-evaluated.</p>
<h2>What we deliberately did not assume</h2><ul><li><b>No automatic benefit from a crowned cap.</b> A60-case macro-gap screen shows crowns can match one pan shape and worsen another. Flatness/finish and alignment coupons come first.</li><li><b>No perfect hot anchor.</b> Ideal PFA/bond calculations at half-wrap contact are near the proposed0.003 W/K target before unknown interface resistance. Poor contact can erase the gain.</li><li><b>No drop-in alloy-wire upgrade.</b> A sourcedØ0.08 mm constantan/PFA coupon reduces simulated wire leakage, but thermoelectric junction errors require a qualified bipolar readout or equivalent evidence. Existing electronics are unchanged.</li><li><b>No sealed or jam-proof claim.</b> The fixture remains dry. Island seizure, optical drift, contact contamination and extra cap lift still require physical validation; the firmware backend stays unavailable.</li></ul>
<h2>Review the proposed build</h2><div class="grid"><div><img class="drawing" src="mechanical/R3-section.svg" alt="Section through revised dry cartridge and anchor coupon"><p class="caption">Six poses,34 valid parts each, no checked rigid intersections. Flexible routes remain envelopes; full lead routing and manufacturing strength are not proved.</p></div><article class="card"><h3>Build and evidence package</h3><p><a href="mechanical/R3-rest.step">Full assembly STEP</a><br><a href="mechanical/R3-cap.step">Retained cap STEP</a><br><a href="mechanical/R3-cap_capture.step">Cap capture pose</a><br><a href="mechanical/geometry.json">Geometry results</a><br><a href="TEST_PREPARATION.md">Coupon/inspection matrix</a><br><a href="thermal/results/contact_requirements.csv">Contact requirements</a><br><a href="thermal/results/anchor_sensitivity.csv">Anchor sensitivity</a><br><a href="SOURCES.md">Sources and assumptions</a><br><a href="verification.md">Verification record</a></p><p>28 automated tests pass. The model reproduces the prior DC limit and checks the new hook/anchor networks against analytical reductions. Physical tests remain NOT_RUN.</p></article></div>
<footer>Simulation and test preparation only. Saved locally; no hardware energization, purchases, publishing or firmware changes.</footer></main></body></html>"""
    )
    (ROOT / "report.html").write_text(html)


if __name__ == "__main__":
    main()
