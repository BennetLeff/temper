"""Gate-drive route replay with KiCad 10 compatibility for skeleton fields."""
import sys
from pathlib import Path

import pcbnew

_get_field = pcbnew.FOOTPRINT.GetFieldText
pcbnew.FOOTPRINT.GetFieldText = lambda self, key: (
    self.GetReference() if key == "SourceInstance" else _get_field(self, key)
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rtd"))
from apply_routes import run  # noqa: E402

if __name__ == "__main__":
    run(*(Path(arg) for arg in sys.argv[1:]))
