"""Native transport controls; no geometry convention is reimplemented here."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "zapote/thermal-sense/candidate/candidate-libs"
HELPER = REPO / "zapote/tools/refresh_native_footprints.py"


def main():
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    results = []
    with tempfile.TemporaryDirectory(prefix="thermal-native-oracle-") as tmp:
        p = Path(tmp) / "oracle.kicad_pcb"
        b = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(b, "test_net")
        b.Add(net)
        fp = io.FootprintLoad(str(LIB / "Resistor_SMD.pretty"), "R_0603_1608Metric", False, None)
        fp.SetFPID(pcbnew.LIB_ID("Resistor_SMD", "R_0603_1608Metric"))
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(20), pcbnew.FromMM(13)))
        fp.SetOrientation(pcbnew.EDA_ANGLE(37, pcbnew.DEGREES_T))
        fp.SetReference("R1")
        fp.SetValue("test")
        fp.SetField("SourceInstance", "oracle")
        fp.SetField("MPN", "RC0603FR-0710KL")
        for pad in fp.Pads():
            pad.SetNet(net)
        b.Add(fp)
        expected = {
            pad.GetNumber(): (tuple(pad.GetPosition()), pad.GetOrientationDegrees())
            for pad in fp.Pads()
        }
        # Simulate metadata/body-angle loss without changing native pad centres.
        for pad in fp.Pads():
            pad.SetOrientation(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        io.SaveBoard(str(p), b)
        args = [
            sys.executable,
            str(HELPER),
            "--board",
            str(p),
            "--libraries",
            str(LIB),
            "--receipt",
            str(Path(tmp) / "receipt.json"),
        ]
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        restored = io.LoadBoard(str(p), None)
        r = list(restored.GetFootprints())[0]
        actual = {
            pad.GetNumber(): (tuple(pad.GetPosition()), pad.GetOrientationDegrees())
            for pad in r.Pads()
        }
        assert actual == expected, (actual, expected)
        assert all(pad.GetNetname() == "test_net" for pad in r.Pads())
        results.append({"test": "37-degree-native-pad-centres-and-orientations", "status": "pass"})
        good_bytes = p.read_bytes()
        pad = list(r.Pads())[0]
        pos = pad.GetPosition()
        pos.x += pcbnew.FromMM(0.1)
        pad.SetPosition(pos)
        io.SaveBoard(str(p), restored)
        before = p.read_bytes()
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        assert result.returncode != 0 and "pad centre differs" in result.stderr, result.stderr
        assert p.read_bytes() == before
        results.append({"test": "changed-pad-centre-refuses-without-writing", "status": "pass"})
        for kind in ["extra-pad", "duplicate-pad", "back-side"]:
            p.write_bytes(good_bytes)
            changed = io.LoadBoard(str(p), None)
            footprint = list(changed.GetFootprints())[0]
            if kind == "back-side":
                footprint.SetLayer(pcbnew.B_Cu)
                expected_error = "front-side"
            else:
                extra = pcbnew.PAD(footprint)
                extra.SetNumber("99" if kind == "extra-pad" else "1")
                footprint.Add(extra)
                expected_error = "pad census"
            io.SaveBoard(str(p), changed)
            before = p.read_bytes()
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            assert result.returncode != 0 and expected_error in result.stderr, result.stderr
            assert p.read_bytes() == before
            results.append({"test": kind + "-refuses-without-writing", "status": "pass"})
    output = {
        "schema": "zapote.native-library-transport-test.v1",
        "kicad_version": pcbnew.Version(),
        "helper_sha256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checks": results,
    }
    (REPO / "zapote/thermal-sense/evidence/library-transport-tests.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(json.dumps(output))


if __name__ == "__main__":
    main()
