"""Open P9-569 process-witness geometry only; no sensor or thermal-property model."""

from __future__ import annotations

import hashlib
import json

import cadquery as cq
import check_capture as capture


def main() -> None:
    parts, _ = capture.r7.make(capture.r7.VARIANTS[0], 0.0, 0.0, 0.0)
    cap = capture.part(parts, "cap_316L").shape
    rows = []
    for gap in (0.100, 0.150):
        identifier = f"P9-569-OPEN-{round(gap * 1000):03d}"
        pad = capture.r7.b.box(2.7, 2.5, gap, (0, 0, 0.45 - gap / 2))
        tile = capture.r7.b.box(2.3, 2.1, 0.25, (0, 0, 0.45 - gap - 0.125))
        shapes = {
            "inherited_D6_316L_cap": cap,
            "569_candidate_process_gap": pad,
            "bare_alumina_witness": tile,
        }
        if not all(s.isValid() for s in shapes.values()):
            raise RuntimeError(f"Invalid witness: {identifier}")
        for a, b in ((cap, pad), (cap, tile), (pad, tile)):
            if capture.solid_overlap(a, b) > 1e-6:
                raise RuntimeError(f"Witness collision: {identifier}")
        if (
            abs(pad.Volume() - 2.7 * 2.5 * gap) > 1e-8
            or abs(tile.Volume() - 2.3 * 2.1 * 0.25) > 1e-8
        ):
            raise RuntimeError(f"Witness volume mismatch: {identifier}")
        filename = capture.OUT / f"{identifier}.step"
        assembly = cq.Assembly(name=identifier)
        for name, shape in shapes.items():
            assembly.add(shape, name=name)
        assembly.save(str(filename))
        filename.write_text(
            "\n".join(line.rstrip() for line in filename.read_text().splitlines()) + "\n"
        )
        restored = cq.importers.importStep(str(filename)).solids().vals()
        if len(restored) != 3 or not all(s.isValid() for s in restored):
            raise RuntimeError(f"Invalid reimport: {identifier}")
        by_name = {}
        for name, source in shapes.items():
            matches = [
                s
                for s in restored
                if abs(s.Volume() - source.Volume()) < 1e-6
                and all(
                    abs(a - b) < 1e-6
                    for a, b in zip(capture.bbox(s), capture.bbox(source), strict=True)
                )
            ]
            if len(matches) != 1:
                raise RuntimeError(f"Witness mapping failed: {name}")
            by_name[name] = matches[0]
        measured_gap = (
            capture.bbox(by_name["569_candidate_process_gap"])[5]
            - capture.bbox(by_name["569_candidate_process_gap"])[4]
        )
        cap_contact = capture.horizontal_contacts(
            by_name["569_candidate_process_gap"], by_name["inherited_D6_316L_cap"]
        )
        tile_contact = capture.horizontal_contacts(
            by_name["bare_alumina_witness"], by_name["569_candidate_process_gap"]
        )
        if (
            abs(measured_gap - gap) > 1e-7
            or abs(sum(x["area_mm2"] for x in cap_contact) - 6.75) > 1e-6
            or abs(sum(x["area_mm2"] for x in tile_contact) - 4.83) > 1e-6
        ):
            raise RuntimeError(f"Witness interface failed: {identifier}")
        rows.append(
            {
                "id": identifier,
                "step": filename.name,
                "sha256": hashlib.sha256(filename.read_bytes()).hexdigest(),
                "bond_gap_mm": gap,
                "step_measured_gap_mm": measured_gap,
                "bond_volume_mm3": pad.Volume(),
                "tile_volume_mm3": tile.Volume(),
                "cap_volume_mm3": cap.Volume(),
                "cap_contact_mm2": sum(x["area_mm2"] for x in cap_contact),
                "tile_contact_mm2": sum(x["area_mm2"] for x in tile_contact),
                "valid_breps_and_step": True,
            }
        )
    (capture.OUT / "process-witness-checks.json").write_text(
        json.dumps(
            {
                "status": "PASS_NOMINAL_PROCESS_WITNESS_GEOMETRY",
                "physical_result": "NOT_RUN",
                "material_properties": "UNKNOWN: no thermal prediction for 569",
                "scope": "Open cap/bond/bare-alumina witness only. No RTD, native leads, covers, seal, cartridge, permanent spacer or external holding fixture included. Nominal CAD gap is not cured process capability.",
                "source_sha256": capture.PINS,
                "witnesses": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print("Two process witness STEP assemblies reimported and verified.")


if __name__ == "__main__":
    main()
