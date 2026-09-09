"""Qualify one protected KiCad keepout and the unchanged routing interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import harness
import routing_host as routing
from qualify_routing import mutate, put

DIRECT = [[6, 11.475], [8.8625, 10.95]]
DETOUR = [[6, 11.475], [7.25, 12.5], [8.5, 12.5], [8.8625, 10.95]]
GROUND = [[6, 8.525], [8.8625, 9.05]]
FIXTURE = "e00r-obstacle"


def qualify(output: Path) -> None:
    if not __debug__:
        raise RuntimeError("Qualification requires assertions")
    output.mkdir(parents=True, exist_ok=False)
    contract_path = routing.CONTRACTS[FIXTURE]
    contract = json.loads(contract_path.read_text())
    cases = []

    def case(
        name: str,
        points: list | None,
        expected: str,
        required: str | None = None,
        change=None,
    ) -> dict:
        directory = output / name
        routing.prepare(directory, [6, 10, 90], fixture=FIXTURE)
        if points:
            put(directory, "+15V", points)
            put(directory, "gnd", GROUND)
        if change:
            change(directory)
        result = routing.evaluate(directory, contract, directory / "evaluation")
        assert result["status"] == expected, (name, result)
        if required:
            assert any(f["id"].startswith(required) for f in result["findings"]), (
                name,
                result,
            )
        cases.append({"case": name, "expected": expected, "actual": result["status"]})
        print(name, result["status"], flush=True)
        return result

    blank = case("blank", None, "fail", "unrouted:")
    native_keepouts = blank["measurement"]["routing"]["keepouts"]
    assert len(native_keepouts) == 1
    assert (
        native_keepouts[0]["layer"] == "F.Cu"
        and native_keepouts[0]["tracks_prohibited"] is True
    )
    assert native_keepouts[0]["outlines_mm"] == [
        [[7.55, 10.5], [7.95, 10.5], [7.95, 12.0], [7.55, 12.0]]
    ]
    cases.append({"case": "native-keepout-context", "actual": "pass"})
    keepout_type = "items_not_allowed"
    case("direct-route-blocked", DIRECT, "fail", f"kicad:{keepout_type}:")
    for i in range(3):
        case(f"detour-{i + 1}", DETOUR, "pass")
    case(
        "centerline-clear-copper-intrudes",
        [[6, 11.475], [7.25, 12.05], [8.5, 12.05], [8.8625, 10.95]],
        "fail",
        f"kicad:{keepout_type}:",
    )
    deleted = case(
        "deleted-keepout",
        DIRECT,
        "fail",
        "protected_state_changed",
        lambda d: mutate(d / "candidate.kicad_pcb", "b.Delete(next(iter(b.Zones())))"),
    )
    disabled = case(
        "disabled-keepout",
        DIRECT,
        "fail",
        "protected_state_changed",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "next(iter(b.Zones())).SetDoNotAllowTracks(False)",
        ),
    )

    # DRC must stop reporting the obstruction when it is removed/disabled,
    # while protected-state acceptance still rejects both tampered boards.
    for result in (deleted, disabled):
        assert not any(
            f["id"].startswith(f"kicad:{keepout_type}:") for f in result["findings"]
        )

    directory = output / "operation-feedback"
    routing.prepare(directory, [6, 10, 90], fixture=FIXTURE)
    session = routing.Session(directory, contract)
    first = session.call("inspect", {})
    assert first["measurement"]["routing"]["keepouts"] == native_keepouts
    blocked = session.call("route", {"net": "+15V", "points_mm": DIRECT})
    ids = {
        f["id"]
        for f in blocked["findings"]
        if f["id"].startswith(f"kicad:{keepout_type}:")
    }
    assert ids and ids.issubset(set(blocked["introduced"]))
    repaired = session.call("route", {"net": "+15V", "points_mm": DETOUR})
    assert ids.issubset(set(repaired["resolved"]))
    assert (
        session.call("route", {"net": "gnd", "points_mm": GROUND})["status"] == "pass"
    )
    assert session.call("remove_route", {"net": "+15V"})["status"] == "fail"
    assert (
        session.call("route", {"net": "+15V", "points_mm": DETOUR})["status"] == "pass"
    )
    assert session.call("check", {})["status"] == "pass"
    assert session.edits == 5
    session.log.close()
    cases.append({"case": "native-feedback-repair-remove-replace", "actual": "pass"})

    receipt = {
        "status": "qualified",
        "scope": "two_routes_one_keepout",
        "contract_sha256": harness.file_hash(contract_path),
        "cases": cases,
        "native_keepout_violation_type": keepout_type,
        "source_sha256": {
            str(p.relative_to(harness.ROOT)): harness.file_hash(p)
            for p in sorted(
                [
                    *harness.ROOT.glob("*.py"),
                    *harness.ROOT.glob("src/*.rs"),
                    harness.ROOT / "Cargo.lock",
                ]
            )
        },
        "evaluator_sha256": harness.file_hash(harness.JUDGE),
    }
    (output / "qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Qualified {len(cases)} obstacle controls", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    qualify(parser.parse_args().output.resolve())
