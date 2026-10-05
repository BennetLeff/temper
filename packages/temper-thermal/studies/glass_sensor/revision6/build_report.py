"""Render Rust-produced comparison CSVs; no simulation or fitted values live here."""

from __future__ import annotations

import csv
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(relative: str) -> list[dict[str, str]]:
    with (ROOT / relative).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def table(headers: list[str], values: list[list[str]]) -> str:
    head = "".join(f"<th scope='col'>{escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(v)}</td>" for v in row) + "</tr>" for row in values
    )
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def bars(values: list[tuple[str, float]], title: str, limit: float) -> str:
    height = 80 + 49 * len(values)
    content = []
    for i, (label, value) in enumerate(values):
        y = 40 + i * 49
        width = value / limit * 310
        content.append(
            f"<text x='0' y='{y + 19}'>{escape(label)}</text>"
            f"<rect x='220' y='{y}' width='{width:.2f}' height='27' rx='3' fill='#276861'/>"
            f"<text x='{230 + width:.2f}' y='{y + 19}'>{value:.2f} s</text>"
        )
    content.append(
        f"<text x='220' y='{height - 5}'>0</text><text x='510' y='{height - 5}'>{limit:g} s</text>"
    )
    return (
        f"<svg viewBox='0 0 610 {height}' role='img' aria-label='{escape(title)}'>"
        f"<title>{escape(title)}</title>" + "".join(content) + "</svg>"
    )


def main() -> None:
    contacts = rows("contact/results/comparison.csv")
    chosen = []
    for package, bond in [
        ("M222", "0.1"),
        ("M222", "0.075"),
        ("IST308", "0.1"),
        ("IST308", "0.075"),
    ]:
        matches = [
            r
            for r in contacts
            if r["package"] == package
            and float(r["bond_mm"]) == float(bond)
            and r["capacity_bracket"] == "envelope_proxy"
            and r["pattern"] == "Uniform"
            and r["environment"] == "nominal"
            and r["href_W_m2K"] == "2000"
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one nominal row for {package}/{bond}")
        chosen.append(matches[0])
    contact_table = table(
        ["Element / bond", "Pan-step t90", "Underread at 200°C", "5°C/s ramp error"],
        [
            [
                f"{r['package']} / {float(r['bond_mm']):.3f} mm",
                f"{float(r['t90_pan_s']):.2f} s",
                f"{float(r['underread200_C']):.3f}°C",
                f"{float(r['finite5C_s_ramp_underread_at200_C']):.2f}°C",
            ]
            for r in chosen
        ],
    )
    chart = bars(
        [(f"{r['package']} · {float(r['bond_mm']):.3f} mm", float(r["t90_pan_s"])) for r in chosen],
        "Conditional pan-step t90, full-envelope capacity assumptions",
        3.5,
    )
    passes = sum(float(r["t90_pan_s"]) <= 2 and float(r["underread200_C"]) <= 1 for r in contacts)
    observers = rows("observer/results/comparison.csv")
    scenarios = list(dict.fromkeys(r["scenario"] for r in observers))
    methods = ["raw_rtd", "steady_loss_correction", "bandlimited_lead", "bounded_bank_midpoint"]
    observer_table = table(
        ["Synthetic scenario", "Raw RTD", "Steady correction", "Lead correction", "Bank midpoint"],
        [
            [scenario.replace("_", " ")]
            + [
                f"{float(next(r['max_abs_error_c'] for r in observers if r['scenario'] == scenario and r['method'] == method)):.2f}°C"
                for method in methods
            ]
            for scenario in scenarios
        ],
    )
    seal_table = table(
        ["Effective diameter", "Pressure for 3 mN", "Equivalent water head"],
        [
            [
                f"{r['effective_diameter_mm']} mm",
                f"{float(r['max_pressure_Pa']):.2f} Pa",
                f"{float(r['max_water_head_mm']):.2f} mm",
            ]
            for r in rows("seal/results/pressure_envelope.csv")
        ],
    )
    optics = [
        r
        for r in rows("optical/results/sensitivity.csv")
        if r["filter"] == "none" and r["pan_C"] == "200" and r["case"] != "hot_filter"
    ]
    optical_table = table(
        ["Hypothetical mismatch", "Inferred pan", "Error (estimate − truth)"],
        [
            [
                r["case"].replace("_", " "),
                f"{float(r['inferred_pan_C']):.2f}°C",
                f"{float(r['error_C']):+.2f}°C",
            ]
            for r in optics
        ],
    )
    document = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Temper · R6 sensor comparison</title><style>
:root{{font-family:system-ui,sans-serif;color:#1d302e;background:#f4f3ed;line-height:1.55}}
body{{max-width:1120px;margin:auto;padding:36px 24px 72px}}h1{{font-size:clamp(2rem,5vw,3.8rem);line-height:1.05;max-width:850px;margin:16px 0}}h2{{font-size:1.65rem;margin-top:0}}h3{{margin-bottom:4px}}p{{max-width:900px}}a{{color:#185d59}}.eyebrow{{letter-spacing:.12em;text-transform:uppercase;font-size:.8rem}}.lead{{font-size:1.2rem;max-width:850px}}.note{{background:#fff1cf;padding:16px 20px;border-left:4px solid #aa6d12}}section{{background:white;padding:28px;margin-top:24px;border:1px solid #dbe2dc;border-radius:10px}}nav{{display:flex;gap:18px;flex-wrap:wrap;margin:26px 0}}table{{border-collapse:collapse;width:100%;font-size:.91rem}}th,td{{text-align:left;padding:11px 12px;border-bottom:1px solid #dbe2dc}}th{{background:#eef3f0}}.scroll{{overflow-x:auto}}.split{{display:grid;grid-template-columns:1.2fr 1fr;gap:28px}}svg{{width:100%;max-width:610px;font:14px system-ui}}.small{{font-size:.88rem;color:#506461}}li{{margin-bottom:10px}}footer{{margin-top:30px}}@media(max-width:800px){{.split{{display:block}}section{{padding:19px}}}}@media print{{body{{padding:0}}section{{break-inside:avoid}}nav{{display:none}}}}
</style><body><div class="eyebrow">Temper engineering · revision 6 · 4 October 2026</div>
<h1>Improve the heat path. Keep contact independently verifiable.</h1>
<p class="lead">Four reproducible studies narrow the next experiment. Thinner packaging helps modeled speed; contact and heat leakage still limit accuracy. Compensation and infrared each introduce their own uncertainty.</p>
<p class="note"><strong>Simulation and test preparation only.</strong> All physical tests remain NOT_RUN. The R5 CAD remains the reference. R6 package variants are parametric hypotheses. These four studies do not combine into a verified product accuracy or response claim.</p>
<nav><a href="#contact">Contact package</a><a href="#observer">Estimation</a><a href="#seal">Seal architecture</a><a href="#optics">Infrared</a><a href="#next">Next evidence</a></nav>
<section id="contact"><h2>1. A thinner element buys time, not accuracy</h2>{contact_table}
<div class="split"><div>{chart}<p class="small">Pan-step t90: 25→100°C pan step, glass/body at 25°C. Underread: pan 200°C, glass 80°C, body 60°C. Ramp error uses a different transient boundary; it is not overshoot.</p></div><div><h3>{passes} / {len(contacts)} cases meet the combined allocation</h3><p>The screen requires ≤2 s and ≤1°C thermal underread, reserving 1°C for the rest of a proposed 2°C worst-case budget. This is a planning allocation.</p><p>At 0.10 mm bond, uncertain capacity assumptions span 2.18–2.94 s for M222 and 1.87–2.27 s for IST308. Overlap prevents a proven component ranking. The smaller chip also roughly doubles bond resistance.</p></div></div>
<p><strong>Advance:</strong> keep D6/M222 as control; compare a controlled thin bond, then an IST308 coupon with complete joins and routed leads. Characterize effective mass and film orientation first. The current 161 listing is Pt1000, so its modeled geometry is not a resolved Pt100 replacement.</p><a href="contact/README.md">Methods and part sources</a> · <a href="contact/RESULTS.md">Detailed results</a> · <a href="contact/results/comparison.csv">324-case CSV</a></section>
<section id="observer"><h2>2. Simple compensation earns a calibration experiment</h2><p>Maximum absolute error across each full 120 s synthetic trajectory, including startup. A separate four-node plant tests the estimators; these results are not fitted R5 scores.</p>{observer_table}
<p><strong>Advance:</strong> log raw, boundary-corrected and bandlimited-lead estimates in future calibration tests. The untuned nine-model bank does not justify firmware integration. Perfectly known absorbed power and body/glass temperatures favor this study.</p><p class="note">A fresh timestamp and plausible warm RTD do not prove contact. Every estimator fails badly when the independent contact input lies. The offline Boolean is not a hardware inhibit, and estimator residuals cannot authorize heating.</p><a href="observer/README.md">Methods, assumptions and fault meanings</a> · <a href="observer/results/comparison.csv">Full metrics</a> · <a href="observer/results/traces.csv">Traces</a></section>
<section id="seal"><h2>3. Seal force is an architecture constraint</h2>{seal_table}<p>Assumed effective area, not necessarily cap area. At zero pressure, a 10 mN total budget minus 3 mN hysteresis and 4 mN harness leaves 3 mN for elastic force. This permits <strong>0.012 N/mm over 0.25 mm</strong>, or <strong>0.00207 N/mm over 1.45 mm</strong>. Consuming the pressure allowance leaves no elastic margin.</p><p><strong>Advance:</strong> a replaceable cartridge with compression datums, dry pressure reference, gravity drainage and positive cap retention. The local-island screen excludes the common carrier seal. A 250–300°C compound rating does not establish flex life or millinewton force.</p><a href="seal/README.md">Architecture precedents and limitations</a> · <a href="seal/results/force_budget.csv">Force budget</a></section>
<section id="optics"><h2>4. Infrared remains a separate research path</h2><p><strong>Invented 3–5 µm transmission curves.</strong> This table shows sensitivity at true pan 200°C, without an additional filter. Inversion assumes emissivity 0.6, glass 80°C and can 40°C. The mismatch cases use emissivity 0.3/0.9, glass 150°C, transmission ×0.8 or can 70°C.</p>{optical_table}
<p>The screen includes glass and filter self-emission; three filter hypotheses and field-of-view outputs are available. It predicts no installed response time or detector accuracy.</p><p>The <a href="https://www.mdpi.com/1424-8220/25/1/235">2025 primary paper</a> reports roughly ±3°C maximum inversion error in its setup. Its approximately 1.1°C forward-model RMSE uses measured pan and glass temperatures as inputs. A bare detector’s 20 ms time constant is a different metric.</p><p><strong>Advance:</strong> obtain exact glass/filter spectra and an identified detector, then compare cold pan/hot glass and held-out cookware. The existing perforated-glass CAD is not an intact-glass optical assembly.</p><a href="optical/README.md">Model and source interpretation</a> · <a href="optical/results/sensitivity.csv">84-case CSV</a></section>
<section id="next"><h2>The next build should be a comparison coupon</h2><ol><li><strong>Retain the control.</strong> D6/M222 at the R5 geometry, with measured bond thickness and assembled thermal response.</li><li><strong>Test one heat-path change at a time.</strong> Thin-bond M222, then a complete IST308 coupon. Preserve covers, retention and actual lead routing in the thermal export.</li><li><strong>Develop the force/seal fixture alongside it.</strong> Measure hot/cold hysteresis, pressure effects, sticking, leakage and cap retention before a cookware claim.</li><li><strong>Calibrate and hold out.</strong> Identify thermal parameters on one cookware set; evaluate separate pans, startup and contact faults before control integration.</li></ol><p>The <a href="README.md">open-gap register</a> records the required bond, seal, contact, retention, induction and endurance evidence. This stage closes the reproducible comparison; it does not close physical qualification.</p></section>
<footer><a href="WORK_PLAN.md">Scope</a> · <a href="VERIFICATION.md">Verification and review</a> · <a href="source-provenance.json">Source provenance</a> · <a href="../revision5/report.html">Frozen R5 report</a><p class="small">Physics: standalone Rust. Report: CSV formatting only. No controller or CAD changes, purchases or publication.</p></footer></body></html>"""
    (ROOT / "report.html").write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
