"""Present completed CAD and Rust outputs without recomputing sensor physics."""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABELS = {
    "M222_control_010": "M222 control · 0.100 mm bond",
    "M222_thin_0075": "M222 · 0.075 mm bond",
    "IST308_thin_0075": "IST308 · 0.075 mm bond",
}


def read_csv(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    rows = read_csv("thermal/results/comparison.csv")
    nominal = [
        r
        for r in rows
        if r["pattern"] == "Uniform" and r["environment"] == "nominal" and r["href_W_m2K"] == "2000"
    ]
    if {r["variant"] for r in nominal} != set(LABELS) or len(nominal) != 3:
        raise ValueError("Expected the three completed CAD-coupled nominal cases")
    table_rows = "".join(
        f"<tr><th scope='row'>{escape(LABELS[r['variant']])}</th>"
        f"<td>{float(r['t90_pan_s']):.2f} s</td><td>{float(r['t90_own_s']):.2f} s</td>"
        f"<td>{float(r['underread200_C']):.3f}°C</td>"
        f"<td>{float(r['finite5C_s_ramp_underread_at200_C']):.2f}°C</td></tr>"
        for r in nominal
    )
    geometry = json.loads((ROOT / "mechanical/geometry.json").read_text())
    pose_count = sum(len(states) for states in geometry["states"].values())
    downloads = "".join(
        f"<li><a href='mechanical/R7-{variant}-rest.step'>{escape(label)} — assembly STEP</a> · "
        f"<a href='mechanical/R7-{variant}-section.svg'>section drawing</a></li>"
        for variant, label in LABELS.items()
    )
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Temper · R7 experimental coupons</title>
<style>:root{{font-family:system-ui,sans-serif;line-height:1.55;color:#213430;background:#f4f3ed}}body{{max-width:1120px;margin:auto;padding:36px 24px 70px}}h1{{font-size:clamp(2rem,5vw,3.5rem);line-height:1.1;margin:18px 0}}h2{{font-size:1.6rem;margin-top:0}}p{{max-width:950px}}a{{color:#1a615b}}section{{background:white;border:1px solid #dce3de;border-radius:9px;padding:26px;margin-top:24px}}.note{{background:#fff1cf;border-left:4px solid #ab741e;padding:17px 20px}}.small{{font-size:.88rem;color:#516861}}.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:.8rem}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:.93rem}}th,td{{padding:12px;border-bottom:1px solid #dce3de;text-align:left}}thead{{background:#eef3f0}}tbody th{{font-weight:500}}img{{width:100%;height:auto}}li{{margin:9px 0}}nav{{display:flex;flex-wrap:wrap;gap:18px;margin:25px 0}}footer{{margin-top:30px}}@media print{{section{{break-inside:avoid}}nav{{display:none}}}}</style>
<body><div class="eyebrow">Temper engineering · revision 7 · experimental preparation</div>
<h1>Complete coupon geometry.<br>Traceable thermal comparison.</h1>
<p>Three D6 assemblies now define the control, thin-bond change and IST308 candidate. Their exported package, join, cover, anchor and wire geometry feeds the same pinned thermal network. Separate bench fixtures and calibration checks prepare the next measurements.</p>
<p class="note"><strong>All physical tests remain NOT_RUN.</strong> CAD validity and simulation do not qualify the moving seal, bond, joins, retention strength or contact inhibition. These are experimental files, not a production release.</p>
<nav><a href="#cad">Coupon CAD</a><a href="#thermal">Thermal results</a><a href="#fixture">Bench fixtures</a><a href="#calibration">Calibration</a><a href="#open">Remaining evidence</a></nav>
<section id="cad"><h2>1. The alternative is now an assembly</h2><img src="mechanical/coupon-cutaways.png" alt="Cutaways from the exported STEP models for the M222 control, thin-bond M222 and IST308 coupon">
<p class="small">The cap remains 316L stainless steel; cutaway colors distinguish components rather than materials.</p>
<p>The IST308 required new wire approaches and anchor/cover clearance. The comparison includes those geometry changes rather than assigning the smaller chip to the unchanged M222 package. The mechanical package records <strong>{pose_count} nominal motion-pose assemblies</strong> across three variants; see the audit for the exact coverage.</p>
<p>Trim-to-fit native leads are an explicit experimental process. Received lead dimensions, film orientation, forming, joining, resistance calibration and insulation still require evidence. A modeled join envelope is not a qualified weld.</p><ul>{downloads}</ul>
<p><a href="mechanical/README.md">Mechanical assumptions and build package</a> · <a href="mechanical/thermal_geometry.csv">CAD scalar export</a> · <a href="mechanical/geometry.json">Geometry checks</a></p></section>
<section id="thermal"><h2>2. Compare speed and bias together</h2><div class="scroll"><table><thead><tr><th>Complete modeled coupon</th><th>Pan-step t90</th><th>Own-final t90</th><th>Underread at 200°C</th><th>5°C/s ramp error</th></tr></thead><tbody>{table_rows}</tbody></table></div>
<p class="small">Nominal uniform contact, reference contact h=2000 W/m²K, full-envelope chip capacity proxy. Step: pan 25→100°C, glass/body 25°C. Steady: pan/glass/body 200/80/60°C. Ramp: pan 25→200°C in 35 s, glass/body 25°C. These are different operating conditions.</p>
<p>Contact conductance, cured bond properties, film position and effective package heat capacity remain assumed. The sweep covers center/rim contact, higher heat leakage and uncertain chip/film properties. An equal-area circular sensor footprint and mean wire path approximate the three-dimensional assembly; this is not full 3D thermal FEA.</p>
<p><a href="thermal/README.md">Network mapping and limits</a> · <a href="thermal/results/comparison.csv">54-case comparison</a> · <a href="thermal/results/uncertainty.csv">Capacity and film sensitivity</a> · <a href="thermal/results/capacity_ledger.csv">Complete capacity ledger</a> · <a href="thermal/results/convergence.csv">Numerical refinement</a></p></section>
<section id="fixture"><h2>3. Measure contact independently</h2><img src="fixture/fixture-sections.png" alt="Independent force-displacement frame and a separate connected pressure-reference test cell">
<p>The dry station locates the fixed housing and glass datum, with external force and displacement references. A 6 mm puck isolates cap force; the 36 mm pan coupon remains a separate accessory because it contacts the glass during travel. All twelve actual cartridge STEP poses and their wires were checked against the corrected fixture. The separate pressure cell provides a connected fluid-domain geometry for membrane experiments; it does not seal the cartridge.</p>
<p>The proposed 3mN hysteresis allocation is difficult to resolve. A paired displacement-registration error of 2µm already contributes 4.8mN at an assumed 2.4N/mm slope. The fine capability example instead targets 0.2µm registration and 0.6mN force bound per reading, leaving only 1.32mN of measured hysteresis under the 3mN guarded allocation. These are metrology requirements, not selected-instrument performance.</p>
<p><a href="fixture/integration.json">Cartridge integration audit</a> · <a href="fixture/README.md">Fixture method and open instrument choices</a> · <a href="fixture/force-displacement-frame.step">Force/displacement STEP</a> · <a href="fixture/connected-pressure-cell.step">Pressure-cell STEP</a> · <a href="fixture/results/metrology_capability.csv">Metrology capability</a></p></section>
<section id="calibration"><h2>4. A good fit must not masquerade as a good sensor</h2>
<p>The adapter reuses the existing bench fit while requiring a different pan and unchanged article, geometry, BOM and process identities. It separately evaluates strict proposed &lt;2°C and &lt;2s uncertainty-guarded limits. A slow reference, unknown uncertainty or empty acquisition cannot pass.</p>
<p>In the independent synthetic check, the forward surrogate predicts the RTD closely, yet the sensor has about 2.70°C underread and 3.75s pan-step response. Both performance screens fail despite the successful fit. Weak-contact and hidden-dynamics holdouts reject model transfer.</p>
<p><a href="calibration/README.md">Adapter and limits</a> · <a href="calibration/TEST_MATRIX.md">Predeclared acquisition matrix</a> · <a href="calibration/templates/campaign.csv">Empty campaign ledger</a> · <a href="calibration/results/SYNTHETIC-holdout.txt">Synthetic distinction check</a></p></section>
<section id="open"><h2>What this advances—and what still needs a bench</h2>
<ul><li><strong>Geometry/model agreement:</strong> complete experimental alternatives now replace R6's package-only hypotheses. CAD exports and thermal inputs are pinned.</li><li><strong>Bond and leads:</strong> installed geometry and inspection records are prepared; film side, cure/voids, trimming, joins and thermal-cycle durability remain unverified.</li><li><strong>Seal and contact:</strong> fixtures and guarded metrology are prepared; no qualified 250°C moving seal or jam-resistant production detector has been demonstrated.</li><li><strong>Retention:</strong> modeled capture remains independent of seal function; strength, unequal-hook loading, wear and abuse limits need physical evidence.</li><li><strong>Induction/endurance:</strong> interference, cap self-heating, pan hotspots, leakage and cleaning/thermal-cycle tests remain physical gates.</li></ul>
<p>Keep the M222/0.10 assembly as the control, compare the thin-bond M222, then the complete IST308 coupon. Measure the assembled heat path and contact envelope before selecting a production package or transferring compensation to control.</p></section>
<footer><a href="README.md">Study overview</a> · <a href="VERIFICATION.md">Executed checks and review</a> · <a href="source-provenance.json">Artifact identities</a> · <a href="WORK_PLAN.md">Scope</a> · <a href="../CURRENT.md">Current experimental CAD index</a><p class="small">Simulation/test preparation only. No purchased parts, hardware operation, firmware enablement or publication.</p></footer></body></html>"""
    (ROOT / "report.html").write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
