"""Run the upstream kit smoke test with downloads/temp output confined here."""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[4] / "validation-plan/sim-kit"
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(KIT / "common"))
import run_ngspice  # noqa: E402
import smoke_test  # noqa: E402

run_ngspice.VENDOR = HERE / "vendor/IFX_CFD7_650V.lib"
cache = HERE / "vendor/smoke-cache"
cache.mkdir(exist_ok=True)
tempfile.tempdir = str(cache)
raise SystemExit(smoke_test.main())
