"""Draw labeled allocation/interval views from the integration handoff."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round2/cooling"


def main() -> None:
    data = json.loads((HERE / "interface.json").read_text())
    report = json.loads((OUT / "checks.json").read_text())
    fig, (plan, contact) = plt.subplots(
        1, 2, figsize=(14, 8), gridspec_kw={"width_ratios": [1.4, 1]}
    )
    plan.add_patch(Rectangle((-185, 0), 370, 440, fill=False, lw=2, color="#444"))
    plan.add_patch(
        Rectangle(
            data["board"]["origin_xy"], *data["board"]["nominal_size"], color="#a9ceb2", alpha=0.5
        )
    )
    plan.text(0, 275, "Actual native19\n142 references", ha="center", va="center")
    for name, label, color in (
        ("CUSTOM_SINK", "Custom sink", "#df9e49"),
        ("LEFT_PULL_FAN", "Pull", "#8eabc4"),
        ("RIGHT_PUSH_FAN", "Push", "#8eabc4"),
        ("FILTER_INSULATING_COVER_ALLOCATION", "D22 filter", "#b59bd2"),
        ("LPSC0001Z_CLOSED_BODY_ENVELOPE", "Fuse", "#cc8888"),
        ("SCHURTER_4435_BODY_ENVELOPE", "Rocker", "#cc8888"),
    ):
        b = report["new_parts"][name]
        plan.add_patch(Rectangle((b[0], b[1]), b[3] - b[0], b[4] - b[1], color=color, alpha=0.75))
        plan.text(
            (b[0] + b[3]) / 2,
            (b[1] + b[4]) / 2,
            label,
            ha="center",
            va="center",
            fontsize=8,
            rotation=90 if "FAN" in name else 0,
        )
    for x in (-160, 161):
        plan.plot([x, x], [157, 405], color="#80b4c9", lw=12, alpha=0.6)
    plan.annotate(
        "Enclosed air ducts\nwith sealed leg sleeves",
        (160, 230),
        (50, 210),
        fontsize=8,
        arrowprops={"arrowstyle": "->"},
    )
    route = data["pe"]["bond_path_world_xyz"]
    plan.plot(
        [p[0] for p in route],
        [p[1] for p in route],
        color="#5c7d22",
        lw=2,
        label="PE route allocation",
    )
    plan.text(0, 35, "R4 front / controls retained", ha="center", fontsize=10)
    plan.text(0, 453, "Rear panel: left exhaust / right intake", ha="center", fontsize=9)
    plan.set(
        xlim=(-200, 200),
        ylim=(-10, 465),
        aspect="equal",
        xlabel="World X (mm)",
        ylabel="World Y (mm)",
        title="Cold packaging plan — allocation view",
    )
    plan.legend(loc="lower left", fontsize=8)
    front = data["contact"]["ceramic_front_local_y"]
    prior = json.loads((ROOT / data["sources"]["corrected_package_bounds"]["path"]).read_text())
    for i, key in enumerate(("mos", "bridge")):
        low, high = prior[key + "_back_board_y"]
        contact.add_patch(
            Rectangle(
                (front - data["contact"]["ceramic_thickness"], i - 0.24),
                data["contact"]["ceramic_thickness"],
                0.48,
                color="#aecbd5",
            )
        )
        contact.plot([low, high], [i, i], color="#b76a18", lw=15, solid_capstyle="butt")
        contact.plot([front, low], [i, i], color="#8b6533", ls="--")
        contact.text(high + 0.04, i, f"{low:.3f}–{high:.3f}", va="center", fontsize=10)
        contact.text(front + 0.02, i + 0.3, "Individually measured shim + films", fontsize=8)
    contact.axvline(front, color="#467885", lw=1)
    contact.set(
        xlim=(-0.2, 2.65),
        ylim=(-0.6, 1.75),
        yticks=[0, 1],
        yticklabels=["MOS ×4", "BR1"],
        xlabel="Rear-plane position from PCB front edge (mm)",
        title="Independent contact depths",
    )
    contact.text(0.0, -0.48, "1 mm ceramic", fontsize=9)
    contact.text(-0.13, 1.56, "Drawing intervals, not assembled measurements", fontsize=9)
    contact.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "Temper R4 / native19 — cold engineering revision, not a powered release", fontsize=14
    )
    fig.text(
        0.5,
        0.012,
        "Clip profile, films, insulation, precharge and measured airflow/thermal performance remain open.",
        fontsize=9,
        ha="center",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(OUT / "allocation-and-contact.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
