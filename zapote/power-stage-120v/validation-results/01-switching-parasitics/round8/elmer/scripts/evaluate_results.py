"""Reapply round 7's fixture checks to the round 8 Big Umfpack evidence."""

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import fixture checker: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(round7_root: Path, round8_root: Path) -> None:
    raw = round8_root / "raw" / "fixtures"
    coax = load_module(round7_root / "scripts" / "evaluate_coax.py", "r7_coax")
    coax.RAW = raw
    coax.CASES = ("coax-port0p10-vol0p30-big", "coax-port0p08-vol0p25-big")
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        coax.main()
    coax_result = json.loads(capture.getvalue())
    if not coax_result["both_meshes_pass_full_sampled_current_2pct_criterion"]:
        raise ValueError("Big Umfpack coax regression failed")
    (round8_root / "coax-evaluation.json").write_text(
        json.dumps(coax_result, indent=2) + "\n")

    plates = load_module(round7_root / "scripts" / "summarize_plates.py", "r7_plates")
    plates.RAW = raw
    labels = ("plates-box0p25-far12-m20", "plates-box0p25-far12-m40",
              "plates-box0p25-far12-m80")
    rows = [plates.summarize(label) for label in labels]
    if any("inductance_nH" not in row for row in rows):
        raise ValueError("one or more plate solves did not qualify as numerical results")
    middle = rows[1]["inductance_nH"]
    final = rows[2]["inductance_nH"]
    change_pct = 100 * (final - middle) / middle
    domain_pass = abs(change_pct) <= 0.5
    band_pass = 2.85 <= final <= 3.14
    plate_result = {"evidence_class": "simulation/model-based", "cases": rows,
                    "last_two_relative_change_pct": change_pct,
                    "last_two_change_at_most_0p5pct": domain_pass,
                    "final_inside_required_2p85_to_3p14_nH": band_pass,
                    "all_plate_criteria_pass": domain_pass and band_pass}
    (round8_root / "plate-margins.json").write_text(
        json.dumps(plate_result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("round7_root", type=Path)
    parser.add_argument("round8_root", type=Path)
    args = parser.parse_args()
    main(args.round7_root, args.round8_root)
