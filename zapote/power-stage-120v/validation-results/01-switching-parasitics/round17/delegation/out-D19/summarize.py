#!/usr/bin/env python3
"""Plot isolated-edge evidence; periodic headroom lives in margin-results.json."""

import gzip
import json
import runpy
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    runpy.run_path(str(HERE / "prepare.py"))
    from run_ngspice import read_raw
    import tempfile

    rows = json.loads((HERE / "edges.json").read_text())
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for row in rows:
        if row["bus_V"] != 198 or row["status"] != "complete":
            continue
        with tempfile.TemporaryDirectory() as directory:
            q = Path(directory) / "wave.raw"
            with gzip.open(HERE / "raw" / (row["case"] + ".raw.gz"), "rb") as f:
                q.write_bytes(f.read())
            waves = read_raw(q)
        t = (np.array(waves["time"]) - 2e-6) * 1e9
        take = t >= 0
        col = 0 if row["current_A"] == 2 else 1
        label = f"ESL {row['esl_nH']} nH / dir {row['direction']}"
        axes[0, col].plot(t[take], np.array(waves["v(sw)"])[take], label=label, lw=0.8)
        axes[1, col].plot(t[take], np.array(waves["i(lbulk)"])[take], label=label, lw=0.8)
    for col, title in enumerate(("2 A: non-ZVS", "37 A: ZVS")):
        axes[0, col].set_title("198 V / " + title)
        axes[0, col].set_ylabel("Switch node V")
        axes[1, col].set_ylabel("Isolated bulk-path current A")
        axes[1, col].set_xlabel("ns after first off command")
        axes[0, col].legend(fontsize=7)
    for ax in axes.flat:
        ax.grid(alpha=0.2)
    fig.suptitle("443 ns isolated edges — not periodic full-bridge EMI sources")
    fig.tight_layout()
    fig.savefig(HERE / "edges.png", dpi=160)
    plt.close(fig)
    complete = [r for r in rows if r["status"] == "complete"]
    out = {
        "complete_edges": len(complete),
        "aborted_edges": len(rows) - len(complete),
        "edge_10_90_ns": [
            min(r["edge_10_90_ns"] for r in complete),
            max(r["edge_10_90_ns"] for r in complete),
        ],
        "zvs_count": sum(r["zvs"] for r in complete),
        "total_EMI_margin_dB": None,
        "filter_change_decision": "INDETERMINATE",
    }
    (HERE / "summary.json").write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
