"""Plot Rust-produced CSVs. This file contains no simulation or physical model."""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_rows(root: Path, name: str) -> list[dict[str, str]]:
    path = root / name
    opener = (
        path.open
        if path.exists()
        else lambda **kwargs: gzip.open(
            path.with_suffix(path.suffix + ".gz"), "rt", **kwargs
        )
    )
    with opener(newline="") as stream:
        return list(csv.DictReader(stream))


def main(root: Path) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    scenarios = read_rows(root, "scenarios.csv")
    traces = read_rows(root, "traces.csv")
    cuts = read_rows(root, "cutoff.csv")
    radial = read_rows(root, "radial_summary.csv")
    candidates = read_rows(root, "candidate_corners.csv")
    colors = {
        "CAD_mid": "#b76332",
        "poor_contact": "#933d53",
        "thin_face_bond": "#847d42",
        "conditional_candidate": "#217b70",
        "aged_bond_leak": "#766182",
        "larger_chip": "#566d87",
    }
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout="constrained")
    for name in ["CAD_mid", "poor_contact", "thin_face_bond", "conditional_candidate"]:
        rows = [r for r in traces if r["case"] == name and r["mode"] == "step"]
        axes[0, 0].plot(
            [float(r["time_s"]) for r in rows],
            [float(r["sensor_C"]) for r in rows],
            label=name.replace("_", " "),
            color=colors[name],
        )
    axes[0, 0].axhline(100, color="#333333", ls=":", label="pan step")
    axes[0, 0].axvline(3, color="#999999", ls="--", label="proposed 3 s target")
    axes[0, 0].set(
        xlabel="Time (s)",
        ylabel="Sensor (°C)",
        title="Contact step: 25 → 100°C; surroundings 25°C",
        xlim=(0, 30),
    )
    axes[0, 0].legend(fontsize=8)
    chosen = ["CAD_mid", "poor_contact", "thin_face_bond", "conditional_candidate"]
    for name in chosen:
        rows = [r for r in cuts if r["case"] == name]
        axes[0, 1].plot(
            [float(r["ramp_C_s"]) for r in rows],
            [float(r["cutoff_pan_C"]) - 200 for r in rows],
            "o-",
            color=colors[name],
            label=name.replace("_", " "),
        )
    axes[0, 1].set(
        xlabel="Imposed pan heating rate (°C/s)",
        ylabel="Pan above 200°C at sensor cutoff (°C)",
        title="Cutoff-only surrogate; not the firmware controller",
    )
    axes[0, 1].legend(fontsize=8)
    mech = read_rows(root, "mechanical.csv")
    for mass, ecc, label in [
        (0.15, 0, "150 g, centered"),
        (0.15, 60, "150 g, COM offset 60 mm"),
        (0.6, 0, "600 g, centered"),
    ]:
        rows = [
            r
            for r in mech
            if float(r["height_mm"]) == 0.6
            and float(r["gap_mm"]) == 0
            and float(r["travel_mm"]) == 1.05
            and float(r["preload_N"]) == 0.1
            and float(r["seal_rate_N_mm"]) == 0
            and float(r["friction_N"]) == 0.1
            and float(r["mass_kg"]) == mass
            and float(r["eccentricity_mm"]) == ecc
        ]
        axes[1, 0].plot(
            [float(r["rate_N_mm"]) for r in rows],
            [float(r["max_edge_gap_mm"]) for r in rows],
            "o-",
            label=label,
        )
    axes[1, 0].set(
        xlabel="Spring stiffness (N/mm)",
        ylabel="Maximum extra edge gap (mm)",
        title="0.6 mm protrusion: rigid pan rocking envelope",
    )
    axes[1, 0].legend(fontsize=8)
    profiles = read_rows(root, "radial_profiles.csv")
    for material, label, color in [
        ("steel", "Steel proxy", "#933d53"),
        ("cast_iron", "Cast-iron proxy", "#b76332"),
        ("aluminum_core_proxy", "Aluminum-core proxy", "#217b70"),
    ]:
        rows = [
            r
            for r in profiles
            if r["material"] == material
            and r["cells"] == "80"
            and r["hole"] == "true"
            and r["pan_glass_h"] == "200"
        ]
        axes[1, 1].plot(
            [float(r["radius_mm"]) for r in rows],
            [float(r["pan_C"]) for r in rows],
            color=color,
            label=label,
        )
    axes[1, 1].axvspan(
        30, 75, color="#dddddd", alpha=0.4, label="imposed heated annulus"
    )
    axes[1, 1].set(
        xlabel="Radius (mm)",
        ylabel="Pan temperature (°C)",
        title="500 W for 120 s: illustrative 3 mm dry pan",
    )
    axes[1, 1].legend(fontsize=8)
    fig.suptitle(
        "Temper in-glass sensor · simulation screening, not physical validation",
        fontsize=16,
    )
    fig.savefig(root / "overview.png", dpi=170)
    fig.savefig(root / "overview.svg")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), layout="constrained")
    for mode, color, label in [
        ("loss_cold", "#b76332", "glass 80°C / body 60°C"),
        ("loss_hot", "#217b70", "surroundings all 200°C"),
    ]:
        rows = [
            r
            for r in traces
            if r["case"] == "CAD_mid"
            and r["mode"] == mode
            and 9 <= float(r["time_s"]) <= 15
        ]
        at_loss = next(float(r["sensor_C"]) for r in rows if float(r["time_s"]) == 10)
        axes[0].plot(
            [float(r["time_s"]) - 10 for r in rows],
            [float(r["sensor_C"]) - at_loss for r in rows],
            label=label,
            color=color,
        )
    axes[0].axvline(0, color="#888888", ls=":")
    axes[0].axvline(1, color="#888888", ls="--")
    axes[0].set(
        xlabel="Time since contact loss (s)",
        ylabel="Sensor change since loss (°C)",
        title="Temperature alone does not prove contact",
    )
    axes[0].legend(fontsize=8)
    for area, color in [(1.0, "#217b70"), (0.3, "#b76332")]:
        subset = [
            r
            for r in candidates
            if float(r["h_ref"]) == 4000
            and float(r["area_fraction"]) == area
            and float(r["face_mm"]) == 0.1
            and float(r["bond_mm"]) <= 0.1
        ]
        times = sorted(float(r["t90_s"]) for r in subset)
        axes[1].plot(
            range(1, len(times) + 1),
            times,
            "o",
            color=color,
            label=f"{area:.0%} effective contact area",
        )
    axes[1].axhline(3, color="#555555", ls="--", label="proposed 3 s screen")
    axes[1].set(
        xlabel="Sorted sensitivity case (not probability)",
        ylabel="90% response time (s)",
        title="Even a 0.1 mm face depends on contact quality",
    )
    axes[1].legend(fontsize=8)
    fig.savefig(root / "hardening.png", dpi=170)
    plt.close(fig)

    control = read_rows(root, "controller_traces.csv")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), layout="constrained")
    for name in ["ideal_sensor", "CAD_mid", "poor_contact", "conditional_candidate"]:
        for ax, mode in zip(axes, ["normal", "loss_at60"]):
            rows = [
                r
                for r in control
                if r["controller"] == "1"
                and r["mass_kg"] == "0.3"
                and r["case"] == name
                and r["mode"] == mode
            ]
            if not rows:
                continue
            ax.plot(
                [float(r["time_s"]) for r in rows],
                [float(r["pan_C"]) for r in rows],
                label=name.replace("_", " "),
                color=colors.get(name, "#333333"),
            )
    rows = [
        r
        for r in control
        if r["controller"] == "1"
        and r["mass_kg"] == "0.3"
        and r["case"] == "CAD_mid"
        and r["mode"] == "loss_guard_at61"
    ]
    axes[1].plot(
        [float(r["time_s"]) for r in rows],
        [float(r["pan_C"]) for r in rows],
        "--",
        label="ideal contact gate: off at 61 s",
        color="#333333",
    )
    for ax in axes:
        ax.axhline(200, color="#aaaaaa", ls=":")
        ax.set(xlabel="Time (s)", ylabel="Pan temperature (°C)", xlim=(0, 180))
        ax.legend(fontsize=8)
    axes[0].set_title("Production cascade module defaults · 300 g plant")
    axes[1].set_title("Contact loss at 60 s · safety state machine excluded")
    axes[1].axvline(60, color="#aaaaaa", ls=":")
    fig.savefig(root / "controller.png", dpi=170)
    plt.close(fig)

    # Validate the hypothetical gate contract independently of the Rust branch.
    guard_rows = [
        r
        for r in control
        if r["mode"] == "loss_guard_at61" and float(r["time_s"]) >= 61
    ]
    assert guard_rows and all(float(r["command_pct"]) == 0 for r in guard_rows)
    assert all(0 <= float(r["command_pct"]) <= 100 for r in control)

    nominal_radial = [
        r
        for r in radial
        if r["cells"] == "80"
        and r["dt_s"] == "0.2"
        and r["pan_glass_h"] == "200"
        and r["hole"] == "true"
    ]
    mesh_delta, time_delta = [], []
    for material in ("steel", "cast_iron", "aluminum_core_proxy"):
        for h in ("50", "200", "1000"):
            for hole in ("false", "true"):
                r40 = next(
                    r
                    for r in radial
                    if r["material"] == material
                    and r["cells"] == "40"
                    and r["pan_glass_h"] == h
                    and r["hole"] == hole
                    and r["dt_s"] == "0.2"
                )
                r80 = next(
                    r
                    for r in radial
                    if r["material"] == material
                    and r["cells"] == "80"
                    and r["pan_glass_h"] == h
                    and r["hole"] == hole
                    and r["dt_s"] == "0.2"
                )
                for key in ("center_pan_C", "hottest_pan_C", "hottest_glass_C"):
                    mesh_delta.append(abs(float(r80[key]) - float(r40[key])))
        r1 = next(r for r in radial if r["material"] == material and r["dt_s"] == "0.1")
        r2 = next(
            r for r in radial if r["material"] == material and r["dt_s"] == "0.05"
        )
        time_delta.extend(
            abs(float(r1[k]) - float(r2[k]))
            for k in ("center_pan_C", "hottest_pan_C", "hottest_glass_C", "sensor_C")
        )
    summary = {
        "mechanical_cases": len(mech),
        "thermal_cases": len(read_rows(root, "thermal.csv")),
        "candidate_cases": len(candidates),
        "candidate_model_screen_passes": sum(
            r["passes_proposed_model_only"] == "true" for r in candidates
        ),
        "radial_runs": len(radial),
        "max_radial_mesh_change_C": max(mesh_delta),
        "max_radial_time_change_C": max(time_delta),
        "max_energy_residual_J": max(
            abs(float(r["energy_residual_J"]))
            for r in radial
            if r["energy_residual_J"] != "NaN"
        ),
        "scenarios": scenarios,
        "radial_nominal": nominal_radial,
    }
    summary["controller_runs"] = len(read_rows(root, "controller_summary.csv"))
    summary["coupled_cases"] = len(read_rows(root, "coupled.csv"))
    summary["hypothetical_gate_trace_assertions"] = (
        "all commands zero from 61 s; all module commands in 0..100 percent"
    )
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
