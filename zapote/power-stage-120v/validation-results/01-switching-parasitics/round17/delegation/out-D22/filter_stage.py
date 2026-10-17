#!/usr/bin/env python3
"""Additional damped DM stage in the unchanged round-3 receiver network."""

from pathlib import Path
import json
import re
import runpy
import subprocess
import tempfile
import numpy as np

HERE = Path(__file__).resolve().parent
D19 = HERE.parent / "out-D19"
MODEL = runpy.run_path(str(D19 / "spectrum.py"))
BASE_DECK = MODEL["PREP"]["R3"] / "scripts/emi_topology.cir"
STAGE = """
* Proposed additional stage: uncoupled inductors, one in each mains conductor.
.param LNEW=18u RNEW=8m CPNEW=30p CXNEW=4.7u CDAMP=4.7u RDAMP=3.9
.param ESLC=20n ESRC=35m
RnewL line_in new_la {RNEW}
LnewL new_la line_mid {LNEW}
CnewLp line_in line_mid {CPNEW}
RnewN neut_in new_na {RNEW}
LnewN new_na neut_mid {LNEW}
CnewNp neut_in neut_mid {CPNEW}
LnewX line_mid new_xa {ESLC}
RnewX new_xa new_xb {ESRC}
CnewX new_xb neut_mid {CXNEW}
Ldamp line_mid damp_a {ESLC}
Rdamp damp_a damp_b {RDAMP}
Cdamp damp_b neut_mid {CDAMP}
Rbleed line_mid neut_mid 30000
"""


def deck_text(params: dict[str, float], source: str, added: bool = True) -> str:
    deck = BASE_DECK.read_text()
    if added:
        start = deck.index("* Input X capacitor")
        stop = deck.index("* One rectifier")
        deck = (
            deck[:start]
            + STAGE
            + deck[start:stop].replace("line_in", "line_mid").replace("neut_in", "neut_mid")
            + deck[stop:]
        )
    if "LCMADD" in params:
        deck = (
            deck.replace("RnewL line_in new_la", "RnewL add_l new_la")
            .replace("RnewN neut_in new_na", "RnewN add_n new_na")
            .replace("CnewLp line_in line_mid", "CnewLp add_l line_mid")
            .replace("CnewNp neut_in neut_mid", "CnewNp add_n neut_mid")
        )
        deck = deck.replace(
            "* Input X capacitor",
            ".param LCMADD=1.6m LDMADD=18u RCMADD=4.5m CCMADD=11.078p RLCMADD=12.691k\nRcmAddL line_in cm_la {RCMADD}\nRcmAddN neut_in cm_na {RCMADD}\nLcmAddL cm_la add_l {LCMADD}\nLcmAddN cm_na add_n {LCMADD}\nKcmAdd LcmAddL LcmAddN {1-LDMADD/(2*LCMADD)}\nCcmAddL line_in add_l {CCMADD}\nCcmAddN neut_in add_n {CCMADD}\nRcmLossL line_in add_l {RLCMADD}\nRcmLossN neut_in add_n {RLCMADD}\n* Input X capacitor",
        )
    if "CXIN" in params:
        deck = deck.replace(
            "* Input X capacitor",
            ".param CXIN=1u\nLxin line_in xin_a {ESLC}\nRxin xin_a xin_b {ESRC}\nCxin xin_b neut_in {CXIN}\n* Input X capacitor",
        )
    if "CYADD" in params:
        deck = deck.replace(
            "* Input X capacitor",
            ".param CYADD=2.2n\nCyaddL line_mid pe {CYADD}\nCyaddN neut_mid pe {CYADD}\n* Input X capacitor",
        )
    if "ESLYADD" in params:
        deck = deck.replace(
            "CyaddL line_mid pe {CYADD}",
            ".param ESLYADD=15n ESRYADD=.1\nLyaddL line_mid cy_la {ESLYADD}\nRyaddL cy_la cy_lb {ESRYADD}\nCyaddL cy_lb pe {CYADD}",
        )
        deck = deck.replace(
            "CyaddN neut_mid pe {CYADD}",
            "LyaddN neut_mid cy_na {ESLYADD}\nRyaddN cy_na cy_nb {ESRYADD}\nCyaddN cy_nb pe {CYADD}",
        )
    if "CYHF" in params:
        deck = deck.replace(
            "* Input X capacitor",
            ".param CYHF=2.2n ESLYHF=10n ESRYHF=.1\nLyhfL line_mid yhf_la {ESLYHF}\nRyhfl yhf_la yhf_lb {ESRYHF}\nCyhfL yhf_lb pe {CYHF}\nLyhfN neut_mid yhf_na {ESLYHF}\nRyhfn yhf_na yhf_nb {ESRYHF}\nCyhfN yhf_nb pe {CYHF}\n* Input X capacitor",
        )
    if "LRDAMP" in params:
        deck = deck.replace(
            "Rdamp damp_a damp_b",
            ".param LRDAMP=500n\nLrdamp damp_a damp_r {LRDAMP}\nRdamp damp_r damp_b",
        )
    if params.get("LNEW") == 0:
        if "LCMADD" not in params:
            raise ValueError("choke-only topology needs LCMADD")
        deck = "\n".join(
            line
            for line in deck.split("\n")
            if not line.startswith(("RnewL ", "RnewN ", "LnewL ", "LnewN ", "CnewLp ", "CnewNp "))
        )
        deck = re.sub(r"\badd_l\b", "line_mid", deck)
        deck = re.sub(r"\badd_n\b", "neut_mid", deck)
    excitation = {f"EXC_{key}": int(key == source) for key in ("A", "B", "DM")}
    for key, value in {**params, **excitation}.items():
        deck, count = re.subn(
            rf"(?m)^([.]param .*\b{key}=)([^\s]+)", lambda match: match[1] + str(value), deck
        )
        if count != 1:
            raise ValueError(f"parameter not unique: {key}")
    return deck


def transfer(name: str, params: dict[str, float], added: bool = True) -> dict:
    folder = HERE / "transfer"
    folder.mkdir(exist_ok=True)
    result = {}
    for source in ("A", "B", "DM"):
        tag = name + "-" + source
        text = deck_text(params, source, added)
        saved = folder / (tag + ".npz")
        if saved.exists():
            if (folder / (tag + ".cir")).read_text() != text:
                raise ValueError(f"inputs changed for {tag}; use a new scenario name")
            with np.load(saved) as data:
                result[source] = {key: data[key] for key in data.files}
            continue
        with tempfile.TemporaryDirectory(prefix="d22-ac-") as directory:
            temp = Path(directory)
            (temp / "case.cir").write_text(text)
            (temp / ".spiceinit").write_text("set filetype=ascii\n")
            run = subprocess.run(
                ["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", "case.cir"],
                cwd=temp,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            (folder / (tag + ".log")).write_text(run.stdout + run.stderr)
            if run.returncode:
                raise RuntimeError(f"AC failure {tag}")
            waves = {
                key: np.asarray(value)
                for key, value in MODEL["read_raw"](temp / "waves.raw").items()
                if key in ("frequency", "v(lisn_l)", "v(lisn_n)", "v(pe)")
            }
        if len(waves["frequency"]) != 30000 or not all(
            np.isfinite(v).all() for v in waves.values()
        ):
            raise ValueError("invalid AC data")
        (folder / (tag + ".cir")).write_text(text)
        np.savez_compressed(saved, **waves)
        result[source] = waves
    return result


def main() -> None:
    cases = ["v170-r2-e1.06-f35000-s0.5-c24", "v170-r2-e1.06-f60000-s0.5-c48"]
    dominant = MODEL["SCENARIOS"]["combined_sensitivity"]
    candidates = {
        "anchor": (False, {}),
        "dm18u_4p7": (True, {}),
        "dm18u_10": (True, {"CXNEW": 10e-6, "CDAMP": 10e-6}),
        "dm18u_4p7_stress": (
            True,
            {
                **dominant,
                "LNEW": 18e-6 * 0.9 * 0.8,
                "CXNEW": 4.7e-6 * 0.8,
                "CDAMP": 4.7e-6 * 0.8,
                "CPNEW": 100e-12,
                "ESLC": 40e-9,
            },
        ),
        "dm18u_10_stress": (
            True,
            {
                **dominant,
                "LNEW": 18e-6 * 0.9 * 0.8,
                "CXNEW": 10e-6 * 0.8,
                "CDAMP": 10e-6 * 0.8,
                "CPNEW": 100e-12,
                "ESLC": 40e-9,
            },
        ),
    }
    rows = []
    for name, (added, params) in candidates.items():
        transfers = transfer(name, params, added)
        for tag in cases:
            with np.load(HERE / (tag + "-n524288-fft.npz")) as data:
                f = data["frequency_Hz"]
                signals = {key: data[key] for key in ("v(swa)", "v(swb)", "bus_current_A")}
            output = MODEL["combine"](transfers, signals, f)
            level = 20 * np.log10(
                np.maximum(abs(output["l_pe"]), abs(output["n_pe"])) / np.sqrt(2) / 1e-6
            )
            _, av, regulated = MODEL["limits"](f)
            index = np.flatnonzero(regulated)[np.argmin((av - level)[regulated])]
            row = {
                "case": tag,
                "scenario": name,
                "min_AV_dB": float((av - level)[index]),
                "Hz": float(f[index]),
            }
            rows.append(row)
            print(row, flush=True)
    (HERE / "filter-exploration.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
