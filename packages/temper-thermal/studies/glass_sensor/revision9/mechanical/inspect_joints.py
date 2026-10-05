"""Inspect the directional seating interface omitted by a catch-only contact graph."""

from __future__ import annotations

import json

import check_capture as capture


def main() -> None:
    rows = []
    for variant in capture.r7.VARIANTS:
        parts, _ = capture.r7.make(variant, 0.0, -0.1, 0.2)
        carrier = capture.part(parts, "main_carrier_and_stem")
        for i in range(1, 4):
            finger = capture.part(parts, f"ceramic_upper_capture_finger_{i}")
            seating = capture.horizontal_contacts(carrier.shape, finger.shape)
            upward_lock = capture.horizontal_contacts(finger.shape, carrier.shape)
            overlap = capture.solid_overlap(carrier.shape, finger.shape)
            if len(seating) != 1 or upward_lock or overlap > 1e-6:
                raise RuntimeError(f"Unexpected attachment geometry: {variant.name}/{finger.name}")
            rows.append(
                {
                    "variant": variant.name,
                    "finger": finger.name,
                    "carrier_upward_face_against_finger_bottom": seating,
                    "finger_upward_face_against_carrier": upward_lock,
                    "overlap_mm3": overlap,
                    "separate_solids": True,
                }
            )
    (capture.OUT / "attachment-checks.json").write_text(
        json.dumps(
            {
                "status": "OPEN_UPWARD_TENSION_JOINT",
                "physical_result": "NOT_RUN",
                "source_sha256": capture.PINS,
                "finding": "The separate capture fingers sit on the carrier. This butt seating contact cannot alone transfer the upward island reaction into the carrier. No interlocking upward bearing surface or modeled attachment joint is present at this interface. A bonded/fastened joint would need explicit design and evidence; the outer clamp/housing stop does not repair this missing force transfer.",
                "checks": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print("Nine separate finger seats checked: upward attachment remains undefined.")


if __name__ == "__main__":
    main()
