#!/usr/bin/env python3
"""Re-execute D-19's two settled operating points before changing numerics."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import runpy
import shutil
import numpy as np

HERE = Path(__file__).resolve().parent
D19 = HERE.parent / "out-D19"


def main() -> None:
    target = HERE / "baseline"
    target.mkdir(exist_ok=True)
    shutil.copyfile(D19 / "periodic-sweep.cir", target / "periodic-sweep.cir")
    source = runpy.run_path(str(D19 / "sweep.py"))
    case = source["case"]
    case.__globals__["HERE"] = target
    configs = [(170, 2, 1.06, 35000, 0.5, 24), (170, 2, 1.06, 60000, 2, 48)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(case, configs))
    checks = []
    for row in rows:
        tag = row["tag"]
        old = json.loads((D19 / "periodic-runs" / (tag + ".json")).read_text())
        assert row["status"] == old["status"] == "complete"
        errors = {}
        with np.load(D19 / "periodic-runs" / (tag + "-fft.npz")) as expected:
            with np.load(target / "periodic-runs" / (tag + "-fft.npz")) as actual:
                for key in expected.files:
                    errors[key] = float(np.max(np.abs(actual[key] - expected[key])))
                    np.testing.assert_allclose(actual[key], expected[key], rtol=1e-9, atol=1e-10)
        checks.append({"tag": tag, "maximum_complex_FFT_absolute_error": errors, "pass": True})
    (HERE / "reproduction.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2), flush=True)


if __name__ == "__main__":
    main()
