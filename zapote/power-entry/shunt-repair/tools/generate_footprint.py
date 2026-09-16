"""Render reviewed dimensions with official KiCad Library Tools, no rule logic."""
import json
from pathlib import Path
from KicadModTree import Footprint, FootprintType, Pad, Property, Rectangle, Line, KicadFileHandler

library = Path(__file__).resolve().parents[2] / "libraries/temper.pretty"
spec = json.loads((library / "HCSM2818FT10L0.json").read_text())
fp = Footprint(spec["mpn"], FootprintType.SMD)
fp.setDescription("Stackpole 10 mOhm 1% shunt; 5 W conditional on 500 mm2 copper and surface below 100 C. Manufacturer land pattern a=3.5 b=5.3 d=0.6 mm.")
for name, value, at, layer, hide in [
    ("Reference", "R?", [0, -3.65], "F.SilkS", False),
    ("Value", spec["mpn"], [0, 3.65], "F.Fab", True),
    ("Datasheet", spec["datasheet"], [0, 0], "F.Fab", True),
]:
    fp.append(Property(name=name, text=value, at=at, layer=layer, hide=hide))
for number, centre in enumerate(spec["pad_centres_mm"], 1):
    fp.append(Pad(number=number, type=Pad.TYPE_SMT, shape=Pad.SHAPE_RECT,
                  at=centre, size=spec["pad_size_mm"], layers=Pad.LAYERS_SMT))
x, y, _ = spec["body_mm"]
fp.append(Rectangle(start=[-x/2, -y/2], end=[x/2,y/2], layer="F.Fab", width=0.1))
cx, cy = spec["courtyard_half_mm"]
fp.append(Rectangle(start=[-cx,-cy], end=[cx,cy], layer="F.CrtYd", width=0.05))
for y in [-2.90, 2.90]:
    fp.append(Line(start=[-3.6,y], end=[3.6,y], layer="F.SilkS", width=0.12))
KicadFileHandler(fp).writeFile(library / (spec["mpn"] + ".kicad_mod"))
