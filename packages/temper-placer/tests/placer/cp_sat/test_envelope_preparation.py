"""Focused tests for the Rust partition-plan preparation boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from temper_placer.placer.cp_sat import envelope_preparation


class _Rules:
    _classes = {
        "DC_BUS+": "HighVoltage",
        "GATE_H": "HighVoltage",
        "SPI_CLK": "Signal",
        "tank.c_tank1-p2": "HighVoltageTank",
    }

    def get_rules_for_net(self, net_name: str, **_kwargs: object) -> SimpleNamespace:
        name = self._classes[net_name]
        return SimpleNamespace(name=name, safety_category="HV", clearance=2.0)


def _component(ref: str, x: float, y: float, *, net: str) -> SimpleNamespace:
    return SimpleNamespace(
        ref=ref,
        initial_position=(x, y),
        bounds=(4.0, 2.0),
        pins=[SimpleNamespace(name="1", number="1", net=net)],
    )


def _netlist() -> SimpleNamespace:
    components = [
        _component("Q1", 10.0, 10.0, net="GATE_H"),
        _component("R1", 16.0, 10.0, net="GATE_H"),
        _component("U7", 40.0, 10.0, net="SPI_CLK"),
        _component("C6", 70.0, 10.0, net="tank.c_tank1-p2"),
    ]
    nets = [
        SimpleNamespace(name="GATE_H", pins=[("Q1", "1"), ("R1", "1")]),
        SimpleNamespace(name="SPI_CLK", pins=[("U7", "1")]),
        SimpleNamespace(name="tank.c_tank1-p2", pins=[("C6", "1")]),
    ]
    return SimpleNamespace(components=components, nets=nets)


def test_prepares_plain_inputs_from_rust_partition_requirements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        lambda _components, _nets: [
            (11, ["C6"], ["tank.c_tank1-p2"], ["HighVoltageTank"]),
            # The planner's member order is not the output order: preparation
            # canonicalizes component refs by the input's stable ref order.
            (2, ["R1", "Q1"], ["GATE_H"], ["HighVoltage"]),
            (7, ["U7"], ["SPI_CLK"], ["Signal"]),
        ],
        raising=False,
    )
    local_calls: list[tuple[str, tuple[object, object, int], float]] = []
    local_headrooms: list[float] = []

    def local_pack(
        partition_id: str,
        components: object,
        pair_requirements: object,
        _max_width: float,
        _max_height: float,
        _base_gap: float,
        *,
        timeout_s: float,
        num_search_workers: int,
        headroom_mm: float,
    ) -> SimpleNamespace:
        local_calls.append((partition_id, (components, pair_requirements, num_search_workers), timeout_s))
        local_headrooms.append(headroom_mm)
        dimensions = {"2": (8.0, 4.0), "7": (7.0, 5.0), "11": (6.5, 6.5)}
        width, height = dimensions[partition_id]
        return SimpleNamespace(feasible=True, width_mm=width, height_mm=height, message=None)

    monkeypatch.setattr(envelope_preparation, "solve_local_sub_envelope", local_pack)
    monkeypatch.setattr(
        envelope_preparation._to,
        "partition_creepage_requirements_py",
        lambda _partitions, _rows: (
            [(11, 2, 10.0), (7, 2, 12.6)],
            [],
        ),
        raising=False,
    )
    monkeypatch.setattr(envelope_preparation, "_generated_creepage_rows", lambda: [])
    monkeypatch.setattr(
        envelope_preparation._to,
        "internal_component_creepage_requirements_py",
        lambda _partitions, _components, _rows: [(2, "Q1", "R1", 0.0)],
        raising=False,
    )

    prepared = envelope_preparation.prepare_envelope_inputs(
        _netlist(),
        _Rules(),
        100.0,
        80.0,
        0.2,
        rotatable_component_refs={"Q1", "R1", "U7"},
    )

    assert [partition[0] for partition in prepared.partitions] == ["2", "7", "11"]
    assert prepared.partitions[0] == ("2", ("Q1", "R1"), 8.0, 4.0)
    assert [call[0] for call in local_calls] == ["2", "7", "11"]
    # The two-component partition has four pairwise-disjunction units versus
    # one for each singleton, so it is scheduled first and receives the
    # largest proportional initial budget.
    assert local_calls[0][2] > local_calls[1][2]
    assert local_calls[0][1][0] == [("Q1", 4.0, 2.0), ("R1", 4.0, 2.0)]
    assert local_calls[0][1][1] == [("Q1", "R1", 0.0)]
    assert all(call[1][2] == 4 for call in local_calls)
    assert local_headrooms == [0.0, 0.0, 0.0]
    assert prepared.ref_to_partition == {"C6": "11", "Q1": "2", "R1": "2", "U7": "7"}
    assert prepared.pair_requirements == [
        ("2", "7", 12.6),
        ("2", "11", 10.0),
    ]
    assert prepared.partition_hints == {
        "2": (9.0, 8.0),
        "7": (36.5, 7.5),
        "11": (66.75, 6.75),
    }
    assert prepared.rotatable_partition_ids == frozenset({"2", "7"})


def test_local_headroom_is_validated_and_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        lambda _components, _nets: [(0, ["Q1"], ["GATE_H"], ["HighVoltage"])],
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "partition_creepage_requirements_py",
        lambda _partitions, _rows: ([], [(0, 0.0)]),
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "internal_component_creepage_requirements_py",
        lambda _partitions, _components, _rows: [],
        raising=False,
    )
    received: list[float] = []

    def local_pack(*_args: object, headroom_mm: float, **_kwargs: object) -> SimpleNamespace:
        received.append(headroom_mm)
        return SimpleNamespace(feasible=True, width_mm=4.0, height_mm=2.0, message=None)

    monkeypatch.setattr(envelope_preparation, "solve_local_sub_envelope", local_pack)
    netlist = SimpleNamespace(
        components=[_component("Q1", 10.0, 10.0, net="GATE_H")],
        nets=[SimpleNamespace(name="GATE_H", pins=[("Q1", "1")])],
    )

    envelope_preparation.prepare_envelope_inputs(
        netlist, _Rules(), 100.0, 80.0, 0.2, headroom_mm=3.5
    )
    assert received == [3.5]

    with pytest.raises(ValueError, match="headroom_mm"):
        envelope_preparation.prepare_envelope_inputs(
            netlist, _Rules(), 100.0, 80.0, 0.2, headroom_mm=float("nan")
        )


def test_initial_position_is_not_required_for_local_sizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        lambda _components, _nets: [(0, ["Q1"], ["GATE_H"], ["HighVoltage"])],
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "partition_creepage_requirements_py",
        lambda _partitions, _rows: ([], [(0, 0.0)]),
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "internal_component_creepage_requirements_py",
        lambda _partitions, _components, _rows: [],
        raising=False,
    )
    netlist = SimpleNamespace(
        components=[_component("Q1", 10.0, 10.0, net="GATE_H")],
        nets=[SimpleNamespace(name="GATE_H", pins=[("Q1", "1")])],
    )
    netlist.components[0].initial_position = None

    prepared = envelope_preparation.prepare_envelope_inputs(netlist, _Rules(), 100.0, 80.0, 0.2)
    assert prepared.partitions == [("0", ("Q1",), 4.0, 2.0)]
    assert prepared.partition_hints == {"0": None}


@pytest.mark.parametrize("position", [(float("nan"), 10.0), (10.0, float("inf")), (10.0,)])
def test_malformed_initial_position_fails_closed(position: object) -> None:
    component = _component("Q1", 10.0, 10.0, net="GATE_H")
    component.initial_position = position

    with pytest.raises(ValueError, match=r"invalid initial_position|initial_position\."):
        envelope_preparation._partition_initial_position_hints(
            [component],
            {"Q1": "0"},
            {"0"},
        )


def test_partial_partition_positions_are_an_explicitly_absent_hint() -> None:
    components = [
        _component("Q1", 10.0, 10.0, net="GATE_H"),
        _component("R1", 20.0, 10.0, net="GATE_H"),
    ]
    components[1].initial_position = None

    assert envelope_preparation._partition_initial_position_hints(
        components,
        {"Q1": "0", "R1": "0"},
        {"0"},
    ) == {"0": None}


def test_rotation_allowlist_requires_every_partition_member() -> None:
    ref_to_partition = {"Q1": "2", "R1": "2", "U7": "7", "C6": "11"}

    assert envelope_preparation._partition_rotation_allowlist(
        ref_to_partition,
        {"Q1", "R1", "U7"},
    ) == frozenset({"2", "7"})


def test_rotation_allowlist_is_empty_without_authoritative_metadata() -> None:
    assert envelope_preparation._partition_rotation_allowlist(
        {"Q1": "2"},
        None,
    ) == frozenset()


def test_rotation_allowlist_rejects_unknown_refs() -> None:
    with pytest.raises(ValueError, match="unknown refs"):
        envelope_preparation._partition_rotation_allowlist(
            {"Q1": "2"},
            {"Q1", "MISSING"},
        )


def test_position_hint_centroid_is_input_order_independent() -> None:
    components = [
        _component("Q1", 10.0, 20.0, net="GATE_H"),
        _component("R1", 30.0, 40.0, net="GATE_H"),
        _component("U7", 80.0, 10.0, net="SPI_CLK"),
    ]
    ownership = {"Q1": "2", "R1": "2", "U7": "7"}
    expected = {"2": (20.0, 30.0), "7": (80.0, 10.0)}

    assert envelope_preparation._partition_initial_position_hints(
        components,
        ownership,
        {"7", "2"},
    ) == expected
    assert envelope_preparation._partition_initial_position_hints(
        list(reversed(components)),
        ownership,
        {"7", "2"},
    ) == expected


def test_centroid_hint_becomes_a_clamped_lower_left_origin() -> None:
    assert envelope_preparation._partition_hint_origins(
        {"2": (99.0, -4.0), "7": None},
        {"2": (20.0, 10.0), "7": (5.0, 5.0)},
        100.0,
        80.0,
    ) == {"2": (80.0, 0.0), "7": None}


def test_failed_local_pack_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        lambda _components, _nets: [(0, ["Q1"], ["GATE_H"], ["HighVoltage"])],
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "partition_creepage_requirements_py",
        lambda _partitions, _rows: ([], [(0, 0.0)]),
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "internal_component_creepage_requirements_py",
        lambda _partitions, _components, _rows: [],
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation,
        "solve_local_sub_envelope",
        lambda *_args, **_kwargs: SimpleNamespace(
            feasible=False,
            status=SimpleNamespace(value="unknown"),
            message="timed out",
        ),
    )
    netlist = SimpleNamespace(
        components=[_component("Q1", 10.0, 10.0, net="GATE_H")],
        nets=[SimpleNamespace(name="GATE_H", pins=[("Q1", "1")])],
    )

    with pytest.raises(ValueError, match="local sub-envelope solve failed"):
        envelope_preparation.prepare_envelope_inputs(netlist, _Rules(), 100.0, 80.0, 0.2)


def test_malformed_rust_partition_requirements_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        lambda _components, _nets: [(0, ["Q1"], ["GATE_H"], ["HighVoltage"])],
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "partition_creepage_requirements_py",
        lambda _partitions, _rows: ([], []),
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "internal_component_creepage_requirements_py",
        lambda _partitions, _components, _rows: [(0, "Q1")],
        raising=False,
    )

    netlist = SimpleNamespace(
        components=[_component("Q1", 10.0, 10.0, net="GATE_H")],
        nets=[SimpleNamespace(name="GATE_H", pins=[("Q1", "1")])],
    )
    with pytest.raises(ValueError, match="internal component requirement .* malformed"):
        envelope_preparation.prepare_envelope_inputs(netlist, _Rules(), 100.0, 80.0, 0.2)


def test_identical_stacked_pads_collapse_to_one_logical_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = _component("K1", 10.0, 10.0, net="GATE_H")
    component.pins.append(SimpleNamespace(name="4", number="1", net="GATE_H"))
    netlist = SimpleNamespace(
        components=[component],
        nets=[SimpleNamespace(name="GATE_H", pins=[("K1", "1")])],
    )
    received: list[object] = []

    def planner(component_records: object, _nets: object) -> list[object]:
        received.append(component_records)
        return [(4, ["K1"], ["GATE_H"], ["HighVoltage"])]

    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        planner,
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation,
        "_generated_creepage_rows",
        lambda: [],
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "partition_creepage_requirements_py",
        lambda _partitions, _rows: ([], [(4, 0.0)]),
        raising=False,
    )
    monkeypatch.setattr(
        envelope_preparation._to,
        "internal_component_creepage_requirements_py",
        lambda _partitions, _components, _rows: [],
        raising=False,
    )

    prepared = envelope_preparation.prepare_envelope_inputs(netlist, _Rules(), 100.0, 80.0, 0.2)

    assert received == [[("K1", [("1", "GATE_H", "HighVoltage")])]]
    assert prepared.ref_to_partition == {"K1": "4"}


def test_conflicting_stacked_pad_records_fail_closed() -> None:
    component = _component("K1", 10.0, 10.0, net="GATE_H")
    component.pins.append(SimpleNamespace(name="4", number="1", net="SPI_CLK"))
    netlist = SimpleNamespace(components=[component], nets=[])

    with pytest.raises(ValueError, match="conflicting duplicate"):
        envelope_preparation._pin_records(netlist.components, _Rules())


def test_stacked_pad_net_terminals_collapse_per_net_but_cross_net_conflict_remains() -> None:
    netlist = SimpleNamespace(
        nets=[
            SimpleNamespace(
                name="GATE_H",
                pins=[("K3", "1"), ("K3", "1"), ("Q1", "1")],
            ),
            SimpleNamespace(name="SPI_CLK", pins=[("K3", "1")]),
        ]
    )

    assert envelope_preparation._net_records(netlist) == [
        ("GATE_H", [("K3", "1"), ("Q1", "1")]),
        ("SPI_CLK", [("K3", "1")]),
    ]


def test_incomplete_or_malformed_rust_plan_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        lambda _components, _nets: [(0, ["Q1"], ["GATE_H"], ["HighVoltage"])],
        raising=False,
    )
    with pytest.raises(ValueError, match="omitted"):
        envelope_preparation.prepare_envelope_inputs(_netlist(), _Rules(), 100.0, 80.0, 0.2)

    monkeypatch.setattr(
        envelope_preparation._to,
        "plan_component_partitions_py",
        lambda _components, _nets: [(False, ["Q1"], ["GATE_H"], ["HighVoltage"])],
        raising=False,
    )
    with pytest.raises(ValueError, match="non-integer"):
        envelope_preparation.prepare_envelope_inputs(_netlist(), _Rules(), 100.0, 80.0, 0.2)
