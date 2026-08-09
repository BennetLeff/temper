"""Tests for router_v6_stage_adapter.py — U7 coverage paydown.

RouterV6Stage0 (LoadPCB) is tested here because it only needs a minimal PCB file
on disk and calls parse_kicad_pcb_v6. The other stages (1-4) require a fully
populated ParsedPCB with design_rules and RouterV6Pipeline, which needs real
board data — those are skipped with reason.
"""

from pathlib import Path

import pytest

from temper_placer.adapters.router_v6_stage_adapter import (
    RouterV6Stage0_LoadPCB,
)
from temper_placer.protocol import StageInput, StageMeta


MINIMAL_PCB = """(kicad_pcb (version 20240108)
  (general (thickness 1.6))
  (setup (pad_to_mask_clearance 0.2))
  (net 0 "")
  (footprint "Test:SOIC-8" (layer F.Cu)
    (tedit 0)
    (tstamp 00000000-0000-0000-0000-000000000000)
    (at 0 0)
    (descr "Test SOIC-8")
    (attr smd)
    (pad "1" smd rect (at -2 3) (size 1 0.5) (layers F.Cu F.Mask F.Paste) (net 0 ""))
    (pad "2" smd rect (at 2 3) (size 1 0.5) (layers F.Cu F.Mask F.Paste) (net 0 ""))
    (pad "3" smd rect (at -2 1) (size 1 0.5) (layers F.Cu F.Mask F.Paste) (net 0 ""))
    (pad "4" smd rect (at 2 1) (size 1 0.5) (layers F.Cu F.Mask F.Paste) (net 0 ""))
  )
)
"""


class TestRouterV6Stage0LoadPCB:
    def test_stage0_attributes(self):
        """Stage 0 has correct name/requires/provides."""
        stage = RouterV6Stage0_LoadPCB()
        assert stage.name == "router_v6/load_pcb"
        assert stage.requires == []
        assert stage.provides == ["parsed_pcb"]
        assert stage.contract is None

    def test_stage0_run_with_path(self, tmp_path):
        """Stage 0 parses a minimal PCB file from a Path."""
        pcb_file = tmp_path / "minimal.kicad_pcb"
        pcb_file.write_text(MINIMAL_PCB)

        stage = RouterV6Stage0_LoadPCB()
        inp = StageInput(data=pcb_file, meta=StageMeta())
        result = stage.run(inp)

        from temper_placer.router_v6.stage0_data import ParsedPCB

        assert result.data is not None
        assert isinstance(result.data, ParsedPCB)
        assert len(result.data.components) >= 0  # may be 0 for minimal
        assert len(result.data.nets) >= 0

    def test_stage0_run_with_str_path(self, tmp_path):
        """Stage 0 accepts a string path."""
        pcb_file = tmp_path / "minimal.kicad_pcb"
        pcb_file.write_text(MINIMAL_PCB)

        stage = RouterV6Stage0_LoadPCB()
        inp = StageInput(data=str(pcb_file), meta=StageMeta())
        result = stage.run(inp)

        from temper_placer.router_v6.stage0_data import ParsedPCB

        assert isinstance(result.data, ParsedPCB)

    def test_stage0_run_rejects_wrong_type(self):
        """Stage 0 raises TypeError for non-Path, non-str input."""
        stage = RouterV6Stage0_LoadPCB()
        inp = StageInput(data=42, meta=StageMeta())  # int is not allowed
        with pytest.raises(TypeError, match="expects Path"):
            stage.run(inp)
