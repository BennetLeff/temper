"""Check the near-lead-edge construction and reject the historical sign error."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[3] / "output/temper-prototype-closure/cooling"


def verify(data: dict) -> dict[str, list[Decimal]]:
    intervals = {}
    for part in ("mos", "bridge"):
        dimensions = data["dimensional_inputs"][part]
        # Rear -> near lead edge -> lead center proceeds in the same direction.
        backs = [
            dimensions["lead_center_board_y"] - (near_edge + thickness / 2)
            for near_edge, thickness in itertools.product(
                dimensions["rear_to_near_lead_edge"], dimensions["lead_thickness"]
            )
        ]
        intervals[f"{part}_back_board_y"] = [min(backs), max(backs)]
    mos, bridge = intervals["mos_back_board_y"], intervals["bridge_back_board_y"]
    intervals["bridge_minus_mos_plane_interval"] = [bridge[0] - mos[1], bridge[1] - mos[0]]
    for part in ("mos", "bridge"):
        interval = intervals[f"{part}_back_board_y"]
        model_y = data[f"generic_model_{part}_y"]
        intervals[f"{part}_signed_gap_to_fixed_1mm_ceramic"] = [
            value - model_y for value in interval
        ]
        contained = interval[0] <= model_y <= interval[1]
        if data[f"generic_model_{part}_within_drawing_interval"] != contained:
            raise ValueError(f"Generic {part} interval membership is incorrect")
    for name, expected in intervals.items():
        if data[name] != expected:
            raise ValueError(f"{name}: recorded bounds do not follow the near-edge construction")
    return intervals


def main() -> None:
    source = HERE / "contact-tolerances.json"
    data = json.loads(source.read_text(), parse_float=Decimal)
    intervals = verify(data)
    rejected = []
    for name, wrong in (
        ("mos_back_board_y", [Decimal("1.805"), Decimal("2.460")]),
        ("bridge_back_board_y", [Decimal("2.000"), Decimal("2.500")]),
    ):
        mutation = copy.deepcopy(data)
        mutation[name] = wrong
        try:
            verify(mutation)
        except ValueError as error:
            rejected.append({"historical_wrong_interval": name, "rejection": str(error)})
        else:
            raise AssertionError(f"Historical plus-sign interval accepted: {name}")
    report = {
        "status": "PASS_DRAWING_ARITHMETIC_ONLY",
        "data_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "construction": "lead_center_y = rear_y + near_edge_distance + half_lead_thickness",
        "intervals": {name: [str(value) for value in values] for name, values in intervals.items()},
        "generic_model_interval_membership": {
            part: data[f"generic_model_{part}_within_drawing_interval"]
            for part in ("mos", "bridge")
        },
        "historical_sign_mutations_rejected": rejected,
        "physical_validation": "NOT_RUN",
    }
    (OUT / "contact-tolerance-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
