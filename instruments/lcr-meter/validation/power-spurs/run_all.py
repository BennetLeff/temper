#!/usr/bin/env python3
"""Run every analysis in this directory and write the summary results.json.

    python3 run_all.py          (about 3 minutes; numpy required)

Detail files: alias_map.json, dds_spurs.json, ripple_chain.json,
regulator_check.json, mitigation.json. Every number quoted in README.md is in
results.json or one of those files.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib

import common as c
import alias_map
import dds_spurs
import mitigation
import regulator_check
import ripple_chain

HERE = pathlib.Path(__file__).resolve().parent


def load(name):
    return json.loads((HERE / name).read_text())


def main():
    for mod in (regulator_check, alias_map, dds_spurs, ripple_chain, mitigation):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main()
        (HERE / f"{mod.__name__}.log").write_text(buf.getvalue())
        print(f"ran {mod.__name__}")
    am, ds, rcj, rg, mi = (load(n) for n in ("alias_map.json", "dds_spurs.json", "ripple_chain.json",
                                              "regulator_check.json", "mitigation.json"))
    grid = []
    for a in am["frequencies"]:
        if a["requested_hz"] not in c.TEMPER_GRID:
            continue
        lobe = [h for h in a["hits"] if h["reach"] == "main lobe"]
        grid.append({
            "hz": a["requested_hz"], "f_dds_hz": a["f_dds_hz"], "divider": a["divider"],
            "fs_hz": a["fs_hz"], "bin_hz": a["bin_hz"],
            "usb_sof_harmonic_in_main_lobe": sorted({int(h["source"].split("x")[-1]) for h in lobe if h["source"].startswith("USB")})[:6],
            "board_clock_1khz_comb_in_main_lobe_hypothetical": sorted({int(h["source"].split("x")[-1]) for h in lobe if h["source"].startswith("board")})[:6],
            "dds_harmonics_in_main_lobe": sorted({int(h["source"].split()[-1]) for h in lobe if h["source"].startswith("DDS")})[:6],
            "switcher_harmonics_reachable": sum(1 for h in a["hits"] if h["source"].startswith("TPS")),
        })
    dds = {}
    for r in ds["frequencies"]:
        key = f"{int(r['acquisition']['requested_hz'])} {r['mode']}"
        dds[key] = {lvl: {n: v for n, v in r["z_error_rss"][lvl].items()}
                    for lvl in ("digital_exact", "assumed_-80dBc", "sfdr_typ_-60dBc")}
    pr = rcj["collision_probability_per_harmonic"]["50000"]
    rip = {"any_of_40_harmonics_probability": 1 - (1 - pr) ** 40}
    for corner in ("worst", "typ"):
        p = rcj["corners"][corner]["undersample"]
        rip[corner] = {"fsw_hz": p["fsw"], "raw_p_cap_vpp": p["raw_p_vpp_cap"], "raw_n_cap_vpp": p["raw_n_vpp_cap"],
                       "raw_p_h1_v": p["raw_p_v"][0], "raw_n_h1_v": p["raw_n_v"][0],
                       "rail_p12_h1_v": p["rail_p12_v"][0], "rail_n12_h1_v": p["rail_n12_v"][0],
                       "adc_a_max_v": max(p["adc_a_v"]), "adc_b_max_v": max(p["adc_b_v"]),
                       "adc_a_max_lsb": max(p["adc_a_v"]) / c.LSB_V, "adc_b_max_lsb": max(p["adc_b_v"]) / c.LSB_V,
                       "ldo_psrr_at_fsw_db": {k: v[0] for k, v in p["ldo_psrr_db"].items()},
                       "opamp_psrr_at_fsw_db": p["opamp_psrr_db"][0],
                       "z_error_if_collision": {s: {k: v["max"] for k, v in d.items()}
                                                for s, d in p["z_error_if_collision"].items()}}
    flags = [r for r in rg["checks"] if r["status"] != "PASS"]
    res = {
        "grid": grid,
        "sweep_1hz": am["sweep_1hz"],
        "coherent_clocks_alias_to_dc": am["coherent_clocks_alias_to_dc"],
        "dds_z_error_rss": dds,
        "dds_digital_model_harmonics_dbc": ds["digital_model_harmonics_dbc"],
        "ripple": rip,
        "ripple_source_borne_worst": rcj["source_borne_worst_corner"],
        "ripple_source_borne_typ": rcj["source_borne_typ_corner"],
        "switcher_collision_probability_per_harmonic": rcj["collision_probability_per_harmonic"],
        "usb_digital_supply_path": {k: v["z_error"] for k, v in rcj["usb_digital_supply_path"].items()},
        "regulator_flags": flags,
        "regulator_loads_a": rg["loads_a"], "vpos": rg["vpos"], "vneg": rg["vneg"],
        "r83_alternative": rg["r83_alternative"], "r5_option": rg["r5_option"],
        "mitigation": {k: [{x: r[x] for x in ("hz", "count", "window", "board_1khz_comb_worst",
                                              "sof_worst_560ppm", "sof_worst_150ppm", "dds_lowest_collision_k")}
                           for r in rows] for k, rows in mi.items() if isinstance(rows, list)},
        "divider_study": {k: v for k, v in mi["divider_study"].items() if k != "examples"},
        "temper_grid_best_divider": mi["temper_grid_best_divider"],
    }
    sig_codes = c.SIGNAL_15R_A_V / c.LSB_V
    res["noise_gate"] = {
        "signal_A_15ohm_codes": sig_codes,
        "tone_codes_for_0.01pct_on_A": sig_codes * 1e-4,
        "tone_codes_for_0.05pct_on_A": sig_codes * 5e-4,
        "fit_amplitude_std_codes_per_1lsb_rms_white_noise": (2 / c.DEFAULT_COUNT) ** 0.5,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=float))
    print("wrote results.json")


if __name__ == "__main__":
    main()
