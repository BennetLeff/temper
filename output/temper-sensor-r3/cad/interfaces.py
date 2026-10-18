"""Read-only R43 interface solids for the C1 checks (imported from the frozen round, never written).

glass   : enclosure_r5.build() part enclosure_glass_350x340x4_sensor_bore
carrier : sensor_coil_r5.support() part ...routed_insulating_carrier
former, winding, ferrite : r34_world (the R34-R43 coil as a real part; R37 constants live in that module)
r16     : sensor_coil_r5.r15_cartridge(travel) (reference only)
Bytecode writing is disabled so nothing lands in the frozen src folder.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

sys.dont_write_bytecode = True
R43 = Path(__file__).resolve().parents[2] / "temper-manufacturing-r43"
sys.path.insert(0, str(R43 / "src"))


@lru_cache(maxsize=1)
def context() -> dict:
    import enclosure_r5 as enc
    import r34_world as coil
    import r40_world as r40
    import sensor_coil_r5 as sc
    glass = next(p["shape"] for p in enc.build() if p["name"] == "enclosure_glass_350x340x4_sensor_bore")
    carrier = next(p["shape"] for p in sc.support() if p["name"].endswith("routed_insulating_carrier"))
    wind, _ = coil.winding()
    leads = coil.lead_points()
    return dict(glass=glass, carrier=carrier, former=coil.former(), winding=wind, ferrite=coil.ferrite(),
                coil_lead_points=leads, coil_module=coil, sc=sc, r40=r40,
                glass_top=sc.GLASS_TOP, glass_under=sc.GLASS_UNDERSIDE, sensor_xy=(sc.SENSOR_X, sc.SENSOR_Y))


def r16(travel: float = 0.0) -> list[dict]:
    return context()["sc"].r15_cartridge(travel)
