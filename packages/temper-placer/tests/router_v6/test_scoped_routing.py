"""TDD tests for bounded net-scoped router dispatch."""

from __future__ import annotations

import inspect
from collections.abc import Collection
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from temper_placer.router_v6._adapter_convert import _normalize_target_nets, route_pcb
from temper_placer.router_v6._pipeline_core import _scope_pcb_nets
from temper_placer.router_v6._pipeline_route import _run_stage4


def test_target_nets_are_sorted_and_deduplicated() -> None:
    assert _normalize_target_nets([" LV ", "HV", "HV"], {"HV", "LV"}) == [
        "HV",
        "LV",
    ]


def test_none_target_scope_preserves_full_board_default() -> None:
    assert _normalize_target_nets(None, {"HV", "LV"}) is None


@pytest.mark.parametrize(
    "scope, expected",
    [
        (set(), "non-empty"),
        ({""}, "non-empty"),
        ({"MISSING"}, "unknown nets"),
    ],
)
def test_invalid_target_scope_fails_closed(
    scope: Collection[str], expected: str
) -> None:
    with pytest.raises(ValueError, match=expected):
        _normalize_target_nets(scope, {"HV", "LV"})


def test_route_pcb_forwards_scoped_dispatch_without_changing_default(
    tmp_path,
) -> None:
    board = tmp_path / "board.kicad_pcb"
    board.write_text("(kicad_pcb)\n", encoding="utf-8")
    parsed = SimpleNamespace(
        source_path=board,
        nets=[SimpleNamespace(name="HV"), SimpleNamespace(name="LV")],
    )
    pipeline_result = SimpleNamespace()

    with (
        patch("temper_placer.router_v6.pipeline.RouterV6Pipeline") as pipeline_class,
        patch(
            "temper_placer.router_v6._adapter_convert._write_routes_to_content",
            return_value=("(kicad_pcb)", {}),
        ),
        patch(
            "temper_placer.router_v6._adapter_convert._build_routing_result",
            return_value="result",
        ),
    ):
        pipeline_class.return_value.run.return_value = pipeline_result

        assert route_pcb(
            parsed,
            {},
            target_nets=["LV", "HV", "HV"],
            skip_stage3=True,
            verbose=True,
        ) == "result"

    _, kwargs = pipeline_class.call_args
    assert kwargs["target_nets"] == ["HV", "LV"]
    assert kwargs["skip_stage3"] is True
    assert kwargs["verbose"] is True


def test_scoped_stage4_bypasses_orchestrator_that_routes_all_nets() -> None:
    source = inspect.getsource(_run_stage4)

    assert "if self.target_nets:" in source
    assert "run_astar_pathfinding(" in source


def test_scoped_pipeline_filters_pcb_and_netlist_before_stage_preparation() -> None:
    hv = SimpleNamespace(name="HV")
    lv = SimpleNamespace(name="LV")
    pcb = SimpleNamespace(
        nets=[hv, lv],
        netlist=SimpleNamespace(nets=[hv, lv]),
    )

    _scope_pcb_nets(pcb, {"HV"})

    assert pcb.nets == [hv]
    assert pcb.netlist.nets == [hv]
