"""Serialize the experimental fuse/clip assembly using KiCad Library Tools.

Manufacturer clip dimensions are retained separately from selected assembly
spacing and fabrication allowances. Physical fit is a release blocker.
"""
from pathlib import Path
from KicadModTree import Footprint, FootprintType, Pad, Property, Rectangle, KicadFileHandler

root = Path(__file__).resolve().parents[1]
name = "A70QS50_ETI_CH14_Prototype"
fp = Footprint(name, FootprintType.THT)
fp.setDescription("PROVISIONAL 14x51 Mersen fuse with two ETI 006710340 clips. Confirm slot/clip/fuse fit before fabrication. ETI drawing p36 G=10.7 F=0.75 D=5; selected clip centres 38mm.")
for field, text, y, layer in [("Reference","F?",-10,"F.SilkS"),("Value","A70QS50-14F",10,"F.Fab")]:
    fp.append(Property(name=field,text=text,at=[0,y],layer=layer))
for number, centre in [(1,-19),(2,19)]:
    for offset in [-5.35,5.35]:
        fp.append(Pad(number=number,type=Pad.TYPE_THT,shape=Pad.SHAPE_OVAL,
            at=[centre+offset,0],size=[3.0,7.0],drill=[1.2,5.4],layers=Pad.LAYERS_THT))
    fp.append(Rectangle(start=[centre-8,-7],end=[centre+8,7],layer="F.Fab",width=.1))
fp.append(Rectangle(start=[-27,-7.5],end=[27,7.5],layer="F.SilkS",width=.12))
fp.append(Rectangle(start=[-28,-8.5],end=[28,8.5],layer="F.CrtYd",width=.05))
KicadFileHandler(fp).writeFile(root/"libraries/temper.pretty"/(name+".kicad_mod"))
