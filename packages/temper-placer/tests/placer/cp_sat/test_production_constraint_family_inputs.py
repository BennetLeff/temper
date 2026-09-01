"""Contracts for the production-board family input adapter."""

from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path
from types import SimpleNamespace

from temper_placer.placer.cp_sat import production_constraint_family_inputs as adapter
from temper_placer.placer.cp_sat.constraint_family_campaign import (
    ConstraintFamilyProbe,
    run_constraint_family_campaign,
)
from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationLimits
from temper_placer.placer.cp_sat.production_stripped_instance import (
    ProductionStrippedDiagnostics,
    ProductionStrippedInstance,
)


class _Netlist:
    components = (SimpleNamespace(ref="A"),)


class _Board:
    pass


def _stripped_instance() -> ProductionStrippedInstance:
    return ProductionStrippedInstance(
        components=(("A", 2.0, 4.0),),
        requirements=(),
        board_width_mm=100.0,
        board_height_mm=80.0,
        initial_placements={"A": (9.0, 8.0, 1)},
        diagnostics=ProductionStrippedDiagnostics(
            100.0, 80.0, 1, 1, 0, (), ((1, 1),), 1
        ),
    )


def test_adapter_uses_live_no_loop_options_and_reports_unavailable_families(monkeypatch, tmp_path) -> None:
    parsed = SimpleNamespace(netlist=_Netlist(), board=_Board())
    monkeypatch.setattr("temper_placer.io.kicad_parser.parse_kicad_pcb", lambda _path: parsed)
    monkeypatch.setattr(
        "temper_placer.io.config_loader.load_constraints",
        lambda _path: SimpleNamespace(pcl_constraints=["authoritative-pcl"]),
    )
    pcb = tmp_path / "board.kicad_pcb"
    config = tmp_path / "production.yaml"
    pcb.write_text("(board)")
    config.write_text("constraints: []")

    inputs = adapter.prepare_production_constraint_family_inputs(
        pcb,
        config,
        include_audits=False,
        seed=17,
        stripped_instance=_stripped_instance(),
    )

    assert inputs.available_families == ("exact_creepage", "tank_creepage")
    assert inputs.production_kwargs["extra_constraints"] == ["authoritative-pcl"]
    assert inputs.production_kwargs["seed"] == 17
    assert inputs.production_kwargs["experimental_omit_generated_creepage"] is True
    assert inputs.families["exact_creepage"] == {"experimental_omit_generated_creepage": False}
    assert inputs.families["tank_creepage"]["tank_creepage"] == {"margin_mm": 10.0}
    assert "decomposed_creepage" in inputs.unavailable_families
    assert "fixed_copper" in inputs.unavailable_families
    assert inputs.unavailable_families["validator_audit"] == "audit inputs excluded by caller"


def test_adapter_includes_audits_only_when_authoritative_builders_resolve(monkeypatch, tmp_path) -> None:
    parsed = SimpleNamespace(netlist=_Netlist(), board=_Board())
    monkeypatch.setattr("temper_placer.io.kicad_parser.parse_kicad_pcb", lambda _path: parsed)
    monkeypatch.setattr(
        "temper_placer.io.config_loader.load_constraints",
        lambda _path: SimpleNamespace(pcl_constraints=[]),
    )
    monkeypatch.setattr(
        adapter,
        "_validator_input",
        lambda _path: ({"placement": {"components": ["A"]}, "voltage_domains": {}}, None),
    )
    monkeypatch.setattr(
        adapter,
        "_body_collision_input",
        lambda _path: ({"fab_bodies": {"A": object()}, "allowlist": object()}, None),
    )
    pcb = tmp_path / "board.kicad_pcb"
    config = tmp_path / "production.yaml"
    pcb.write_text("(board)")
    config.write_text("constraints: []")

    inputs = adapter.prepare_production_constraint_family_inputs(
        pcb, config, stripped_instance=_stripped_instance()
    )

    assert inputs.available_families == (
        "exact_creepage",
        "tank_creepage",
        "validator_audit",
        "body_collision_audit",
    )
    assert "validator_input" in inputs.families["validator_audit"]
    assert "body_collision_input" in inputs.families["body_collision_audit"]


def test_adapter_feeds_fresh_campaign_with_the_exact_family_options(monkeypatch, tmp_path) -> None:
    parsed = SimpleNamespace(netlist=_Netlist(), board=_Board())
    monkeypatch.setattr("temper_placer.io.kicad_parser.parse_kicad_pcb", lambda _path: parsed)
    monkeypatch.setattr(
        "temper_placer.io.config_loader.load_constraints",
        lambda _path: SimpleNamespace(pcl_constraints=[]),
    )
    monkeypatch.setattr(adapter, "_validator_input", lambda _path: (None, "not available"))
    monkeypatch.setattr(adapter, "_body_collision_input", lambda _path: (None, "not available"))
    pcb = tmp_path / "board.kicad_pcb"
    config = tmp_path / "production.yaml"
    pcb.write_text("(board)")
    config.write_text("constraints: []")
    inputs = adapter.prepare_production_constraint_family_inputs(
        pcb, config, stripped_instance=_stripped_instance()
    )
    def solver(_netlist: object, _board: object, **kwargs: object) -> SimpleNamespace:
        if kwargs.get("experimental_omit_generated_creepage") not in (True, False):
            raise AssertionError("campaign must set the explicit creepage switch")
        return SimpleNamespace(status="optimal", positions={"A": (1.0, 1.0)}, rotations={"A": 0})

    result = adapter.run_production_constraint_family_campaign(
        inputs,
        planner=lambda _families, _prior: (("exact_creepage",),),
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5, stage_timeout_s=2, memory_limit_mb=None),
    )

    assert result.probes[0].family_set == ()
    assert result.probes[0].status.value == "accepted"
    assert result.probes[1].family_set == ("exact_creepage",)


def test_rust_verifier_converts_centres_and_absolute_rotations_to_lower_left(monkeypatch) -> None:
    inputs = adapter.ProductionConstraintFamilyInputs(
        input_pcb=Path("board.kicad_pcb"),
        config=Path("production.yaml"),
        parse_result=object(),
        netlist=_Netlist(),
        board=_Board(),
        production_kwargs={},
        families={},
        unavailable_families={},
        stripped_instance=_stripped_instance(),
    )
    observed: list[object] = []
    import temper_orchestration

    monkeypatch.setattr(
        temper_orchestration,
        "verify_stripped_creepage_py",
        lambda components, requirements, width, height, placements, allow: observed.append(
            (components, requirements, width, height, placements, allow)
        ),
    )

    result = adapter.make_production_constraint_family_verifier(inputs)(
        SimpleNamespace(positions={"A": (20.0, 30.0)}, rotations={"A": 2})
    )

    assert result.passed
    assert observed[0][4] == [("A", 18.0, 29.0, 1)]
    assert observed[0][5] is True


def test_high_level_entrypoint_wires_stable_cache_and_verifier_only_for_accepted_complete(
    monkeypatch, tmp_path
) -> None:
    config = tmp_path / "production.yaml"
    config.write_text("constraints: []")
    board = tmp_path / "board.kicad_pcb"
    board.write_text("board")
    inputs = adapter.ProductionConstraintFamilyInputs(
        input_pcb=board,
        config=config,
        parse_result=object(),
        netlist=_Netlist(),
        board=_Board(),
        production_kwargs={"seed": 4, "extra_constraints": []},
        families={
            "exact_creepage": {"experimental_omit_generated_creepage": False},
            "tank_creepage": {"tank_creepage": {"margin_mm": 10.0}},
        },
        unavailable_families={},
        stripped_instance=_stripped_instance(),
    )
    def _prepared(*_args: object, **_kwargs: object):
        return inputs

    monkeypatch.setattr(adapter, "prepare_production_constraint_family_inputs", _prepared)

    manager = mp.Manager()
    verifier_calls = manager.list()
    import temper_orchestration

    monkeypatch.setattr(
        temper_orchestration,
        "verify_stripped_creepage_py",
        lambda *_args: verifier_calls.append(True),
    )

    def solver(_netlist: object, _board: object, **kwargs: object) -> SimpleNamespace:
        if kwargs.get("experimental_omit_generated_creepage") is False:
            return SimpleNamespace(status="unknown", positions={}, rotations={})
        return SimpleNamespace(status="optimal", positions={"A": (10.0, 10.0)}, rotations={"A": 1})

    def fake_real_board(_path: object, **kwargs: object):
        return run_constraint_family_campaign(
            inputs.netlist,
            inputs.board,
            families=kwargs["families"],
            probes=kwargs["probes"],
            production_kwargs=kwargs["production_kwargs"],
            solver=kwargs["solver"],
            verify=kwargs["verify"],
            limits=kwargs["limits"],
        )

    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.constraint_family_real_board.run_real_board_constraint_family_campaign",
        fake_real_board,
    )
    result = adapter.run_production_constraint_family_real_board_campaign(
        board,
        config,
        probes=(ConstraintFamilyProbe((), "base"), ConstraintFamilyProbe(("exact_creepage",)), ConstraintFamilyProbe(("tank_creepage",))),
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5, stage_timeout_s=2, memory_limit_mb=None),
    )

    assert [probe.status.value for probe in result.probes] == ["accepted", "unknown", "accepted"]
    assert len(verifier_calls) == 2
    production_projection, family_projection = adapter.production_constraint_family_cache_projections(inputs)
    json.dumps((production_projection, family_projection), sort_keys=True)
    manager.shutdown()
