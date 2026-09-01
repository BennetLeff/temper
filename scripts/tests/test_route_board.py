"""Tests for the public target-net route driver boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import route_board  # noqa: E402


def test_scoped_route_refuses_whole_board_copper_stripping() -> None:
    with pytest.raises(ValueError, match="retain unrelated copper"):
        route_board.route_once(
            Path("missing.kicad_pcb"),
            Path("missing.yaml"),
            target_nets=["discharge.r_snub1-p2"],
            keep_existing_copper=False,
        )


def test_target_net_cli_reaches_single_route_boundary(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run_single(pcb_path, rules_path, output_path, **kwargs):
        captured.update(
            pcb_path=pcb_path,
            rules_path=rules_path,
            output_path=output_path,
            **kwargs,
        )
        return 0

    monkeypatch.setattr(route_board, "run_single", fake_run_single)
    output = tmp_path / "scoped.kicad_pcb"

    assert route_board.main(
        ["--output", str(output), "--target-net", "discharge.r_snub1-p2"]
    ) == 0
    assert captured["target_nets"] == ["discharge.r_snub1-p2"]
    assert captured["output_path"] == output


def test_target_net_is_not_allowed_in_variance_mode() -> None:
    with pytest.raises(SystemExit) as error:
        route_board.main(["--runs", "1", "--target-net", "discharge.r_snub1-p2"])
    assert error.value.code == 2
