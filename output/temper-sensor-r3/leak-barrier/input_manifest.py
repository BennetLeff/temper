"""Content-hash manifests of the inputs of four studies (sensor-r3):

- T2 setpoint_cap.py and T3 cr5_band.py (T2_INPUTS, T3_INPUTS);
- F1 firmware/d1_nuisance.py (F1_INPUTS);
- T1 leak-barrier/leak_barrier.py (T1_INPUTS).

The lists are the exact inputs each study reads: the C sources and headers that the
study compiles (with the headers they include), the repo Python modules each script
imports (transitively), and the JSON evidence it reads, including reads made at import
time by an imported module. Git history is not consulted: a study is current iff every
recorded sha256 equals the current file's sha256. Unrelated changes (other firmware,
other studies, the scripts' own docs) do not touch a manifest.

Scripts are not listed: as for setpoint_cap.py, a script's own bytes are not an input.
Reads that happen only in a module's own producer main() (for example the datasheet
PDFs in hs_ntc.py, pcb/checks.py in rim_ntc.py, the rail header in rail_adc.py) are
not inputs of the studies that only import the module.

Paths are repo-relative, as written into the evidence JSON under apparatus.input_sha256
(F1, T2, T3) or provenance.input_sha256 (T1).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

R3 = "output/temper-sensor-r3"

# build_lib.sh, cosim_shim.c, the C sources it lists, and every header they include
# (closure of #include, with -I components/control, components/sensors/include,
# firmware/config.h's directory).
C_LIBRARY = (
    f"{R3}/firmware/build_lib.sh",
    f"{R3}/firmware/cosim_shim.c",
    "firmware/config.h",
    "firmware/components/control/contact_check.c",
    "firmware/components/control/contact_check.h",
    "firmware/components/control/contact_shift.c",
    "firmware/components/control/contact_shift.h",
    "firmware/components/control/current_sense_check.c",
    "firmware/components/control/current_sense_check.h",
    "firmware/components/control/pan_cold_soak.c",
    "firmware/components/control/pan_cold_soak.h",
    "firmware/components/control/pan_leak_check.c",
    "firmware/components/control/pan_leak_check.h",
    "firmware/components/control/pan_rate_pid.c",
    "firmware/components/control/pan_rate_pid.h",
    "firmware/components/control/pan_rim_limit.c",
    "firmware/components/control/pan_rim_limit.h",
    "firmware/components/control/pan_sensor_guard.c",
    "firmware/components/control/pan_sensor_guard.h",
    "firmware/components/control/pan_supervisor.c",
    "firmware/components/control/pan_supervisor.h",
    "firmware/components/control/pan_temp_estimator.c",
    "firmware/components/control/pan_temp_estimator.h",
    "firmware/components/control/pan_temp_loop.c",
    "firmware/components/control/pan_temp_loop.h",
    "firmware/components/control/plant_gain.c",
    "firmware/components/control/plant_gain.h",
    "firmware/components/sensors/hs_ntc.c",
    "firmware/components/sensors/hs_ntc_table.h",
    "firmware/components/sensors/include/hs_ntc.h",
    "firmware/components/sensors/include/rim_ntc.h",
    "firmware/components/sensors/include/rtd_convert.h",
    "firmware/components/sensors/rim_ntc.c",
    "firmware/components/sensors/rim_ntc_table.h",
    "firmware/components/sensors/rtd_convert.c",
)

# Python modules imported (transitively) by both studies.
PY_COMMON = (
    f"{R3}/evidence_compare.py",
    f"{R3}/contact_model.py",
    f"{R3}/screen.py",
    f"{R3}/robustness/shift_kf.py",
    "output/temper-sensor-r2/estimator_study.py",
    f"{R3}/firmware/cosim.py",
    f"{R3}/firmware/leak_checks.py",
    f"{R3}/firmware/rail_adc.py",
    f"{R3}/firmware/ref.py",
    f"{R3}/firmware/rim_limit.py",
    f"{R3}/firmware/rim_ntc.py",
    f"{R3}/firmware/xcheck_cosim.py",
)
# T2 only: cold_soak (cold-soak check) and its heatsink driver model.
PY_T2 = (
    f"{R3}/firmware/cold_soak.py",
    f"{R3}/firmware/hs_ntc.py",
)

# JSON read by the studies (at import or in their own code paths).
AXISYM_JSON = f"{R3}/cad/thermal-axisym.json"   # rim_limit.ENV = envelope(), run at import
DATA_COMMON = (
    AXISYM_JSON,
    f"{R3}/firmware/leak-checks.json",
    f"{R3}/firmware/rim-limit.json",
)
DATA_T2 = (
    f"{R3}/firmware/cold-soak.json",
)

T2_INPUTS = tuple(sorted(set(C_LIBRARY) | set(PY_COMMON) | set(PY_T2) | set(DATA_COMMON) | set(DATA_T2)))
T3_INPUTS = tuple(sorted(set(C_LIBRARY) | set(PY_COMMON) | set(DATA_COMMON)))

# F1 (d1_nuisance.py) builds C_LIBRARY through build_lib.sh (cosim_shim.c is listed there)
# and imports exactly PY_COMMON (its static closure, checked). Its only JSON read is the
# axisymmetric geometry that rim_limit reads at import; it reads no leak-checks.json or
# rim-limit.json. Control sources it does not compile (pll_control.c, pan_detect.c,
# low_temp_control.c, ...) are not inputs.
F1_INPUTS = tuple(sorted(set(C_LIBRARY) | set(PY_COMMON) | {AXISYM_JSON}))

# T1 (leak_barrier.py) compiles only rtd_convert.c, with -I sensors/include, through its own
# cc call; no build_lib.sh and no co-simulation library.
T1_C = (
    "firmware/components/sensors/rtd_convert.c",
    "firmware/components/sensors/include/rtd_convert.h",   # the only #include in rtd_convert.c
)
# T1 imports hs_ntc (PT_CLASS_K) in addition to PY_COMMON; it reads hs-ntc.json (cold-soak budget)
# and leak-checks.json. It does not read the thermal axisymmetric geometry or rim-limit.json.
PY_T1 = (f"{R3}/firmware/hs_ntc.py",)
DATA_T1 = (
    f"{R3}/firmware/hs-ntc.json",
    f"{R3}/firmware/leak-checks.json",
)
T1_INPUTS = tuple(sorted(set(T1_C) | set(PY_COMMON) | set(PY_T1) | set(DATA_T1)))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_manifest(repo: Path, rel_paths) -> dict[str, str]:
    """{repo-relative path: sha256} for exactly the given files; raises if one is missing."""
    return {rel: sha256_file(repo / rel) for rel in sorted(rel_paths)}


def unchanged(recorded: dict[str, str], repo: Path) -> bool:
    """True iff the manifest is non-empty and every recorded hash equals the current file's.

    A missing or unreadable file counts as changed.
    """
    if not recorded:
        return False
    for rel, digest in recorded.items():
        try:
            if sha256_file(repo / rel) != digest:
                return False
        except OSError:
            return False
    return True
