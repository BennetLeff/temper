"""mesh25d_hybrid's stack hook (c33 adoption): the four-layer stack file reproduces the committed table exactly,
the six-layer file gives six layers, and loop-net copper on a layer outside the stack is refused.

    PYTHONPATH=/opt/homebrew/lib python3 -m pytest -q test_stack_layers.py   (gmsh's python module on the path)
"""
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]
sys.path.insert(0, str(HERE))
os.environ.pop("MESH_STACKUP", None)
import mesh25d_hybrid as m  # noqa: E402


def test_four_layer_stack_is_the_committed_table():
    layers, zb, zt = m.stack_layers(POWER / "native-21/stackup.json")
    assert layers == m.LAYERS and list(layers) == list(m.LAYERS)
    assert (zb, zt) == (m.Z_BOTTOM, m.Z_TOP)


def test_six_layer_stack():
    layers, zb, zt = m.stack_layers(POWER / "native-21/stackup-6L.json")
    assert list(layers) == ["B.Cu", "In4.Cu", "In3.Cu", "In2.Cu", "In1.Cu", "F.Cu"]
    assert zb == -0.07 and zt == 1.588
    assert layers["In1.Cu"] == (1.2355, 1.2965) and layers["In2.Cu"] == (0.8745, 0.9355)
    # In1 / In2 are the 0.30 mm core pair
    assert round(layers["In1.Cu"][0] - layers["In2.Cu"][1], 6) == 0.3


def test_unknown_layer_refused(tmp_path):
    exp = tmp_path / "x.json.gz"
    prim = [{"kind": "track", "net": "bus_p", "layer": "In3.Cu", "start": [50, 20], "end": [60, 20], "width_mm": 1.0}]
    with gzip.open(exp, "wt") as fh:
        json.dump({"primitives": prim}, fh)
    from shapely.geometry import box
    with pytest.raises(SystemExit, match="In3.Cu"):
        m.load_copper(str(exp), box(40, 10, 80, 40), 0.05, 0.01, False, {"bus_p"}, 0.0)


def test_env_hook_selects_six_layers():
    code = "import mesh25d_hybrid as m; print(len(m.LAYERS), m.Z_TOP)"
    env = dict(os.environ, MESH_STACKUP=str(POWER / "native-21/stackup-6L.json"))
    out = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["6", "1.588"]
