"""Focused native transport test for duplicate relay pads and NPTH geometry."""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "zapote/tools/refresh_native_footprints.py"
LIB = ROOT / "zapote/power-entry/candidate/candidate-libs"


def run() -> dict:
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    with tempfile.TemporaryDirectory(prefix="native-refresh-transport-") as td:
        td = Path(td)
        board_path = td / "board.kicad_pcb"
        receipt = td / "receipt.json"
        board = pcbnew.BOARD()
        relay = io.FootprintLoad(str(LIB / "temper.pretty"), "Relay_SPST_Schrack-RT33K012", False, None)
        choke = io.FootprintLoad(str(LIB / "Inductor_THT_Wurth.pretty"), "L_Wurth_WE-TORPFC-T75", False, None)
        relay.SetFPID(pcbnew.LIB_ID("temper", "Relay_SPST_Schrack-RT33K012"))
        choke.SetFPID(pcbnew.LIB_ID("Inductor_THT_Wurth", "L_Wurth_WE-TORPFC-T75"))
        relay.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(30), pcbnew.FromMM(30)))
        choke.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(100), pcbnew.FromMM(80)))
        relay.SetOrientation(pcbnew.EDA_ANGLE(45, pcbnew.DEGREES_T))
        choke.SetOrientation(pcbnew.EDA_ANGLE(45, pcbnew.DEGREES_T))
        relay.SetReference("K1"); relay.SetValue("RT33K012")
        choke.SetReference("L1"); choke.SetValue("760800301")
        relay.SetField("SourceInstance", "relay"); relay.SetField("MPN", "RT33K012")
        choke.SetField("SourceInstance", "choke"); choke.SetField("MPN", "760800301")
        board.Add(relay); board.Add(choke); io.SaveBoard(str(board_path), board)
        saved_uuids = sorted(pad.m_Uuid.AsString() for fp in board.GetFootprints() for pad in fp.Pads())
        before = board_path.read_bytes()
        cmd = [sys.executable, str(HELPER), "--board", str(board_path), "--libraries", str(LIB), "--receipt", str(receipt)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        refreshed = io.LoadBoard(str(board_path), None)
        assert len(list(refreshed.GetFootprints())) == 2
        by_ref = {fp.GetReference(): fp for fp in refreshed.GetFootprints()}
        assert len(list(by_ref["K1"].Pads())) == 6
        assert any(pad.GetNumber() == "" for pad in by_ref["L1"].Pads())
        assert saved_uuids == sorted(pad.m_Uuid.AsString() for fp in refreshed.GetFootprints() for pad in fp.Pads())
        good = board_path.read_bytes()
        assert {fp.GetReference(): fp.m_Uuid.AsString() for fp in board.GetFootprints()} == {fp.GetReference(): fp.m_Uuid.AsString() for fp in refreshed.GetFootprints()}

        changed = io.LoadBoard(str(board_path), None)
        pad = list(changed.GetFootprints())[0].Pads()[0]
        pos = pad.GetPosition(); pos.x += pcbnew.FromMM(0.1); pad.SetPosition(pos)
        io.SaveBoard(str(board_path), changed)
        mutated = board_path.read_bytes()
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert result.returncode != 0 and "pad census differs" in result.stderr, result.stderr
        assert board_path.read_bytes() == mutated
        return {"duplicate_relay_pads": 6, "npth": True, "rotation_deg": 45, "mutation_refused": True}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
