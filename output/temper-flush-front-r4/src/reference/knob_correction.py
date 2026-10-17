"""Proposed split-guide correction ONLY; original model is never modified."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import cadquery as cq

OUT=Path(__file__).resolve().parent
SOURCE=OUT/"knob_original.py"
spec=importlib.util.spec_from_file_location("audited_knob",SOURCE)
assert spec and spec.loader
original=importlib.util.module_from_spec(spec);sys.modules[spec.name]=original;spec.loader.exec_module(original)
Part=original.Part

def build(angle_deg:float=0,press_mm:float=0,removed_mm:float=0,include_mounts:bool=True,show_springs:bool=True)->list[Part]:
    parts=original.build(angle_deg,press_mm,removed_mm,include_mounts,show_springs)
    source=next(p for p in parts if p.name=="stationary_shoe_integral_guides")
    shoe=source.shape.translate((0,0,-removed_mm))
    additions=[]
    for side in(0,180):
        cut=original.box(4.95,3.8,10.5,3,16.875).rotate((0,0,0),(0,0,1),side)
        lid=shoe.intersect(cut);shoe=shoe.cut(cut)
        for y in(-3.1,3.1):
            post=original.disk(1.6,5,5.5,16,y).fuse(original.disk(1.15,10.5,.5,16,y))
            post=post.cut(original.disk(.7,8,4,16,y)).rotate((0,0,0),(0,0,1),side)
            shoe=shoe.fuse(post)
            ear=original.disk(1.6,10.5,1.9,16,y).cut(original.disk(.85,10,4,16,y)).cut(original.disk(1.25,10.4,.7,16,y)).rotate((0,0,0),(0,0,1),side)
            lid=lid.fuse(ear)
            screw=original.disk(.65,8.5,3.9,16,y).fuse(original.disk(1.2,12.4,.6,16,y)).rotate((0,0,0),(0,0,1),side)
            additions.append(Part(f"guide_lid_screw_{side}_{y}_thread_envelope",screw.translate((0,0,removed_mm)),original.SILVER,True))
        additions.append(Part(f"keyed_split_guide_lid_{side}",lid.translate((0,0,removed_mm)),original.BLUE,True))
    return [Part("corrected_open_trough_shoe",shoe.translate((0,0,removed_mm)),source.color,True) if p.name==source.name else p for p in parts]+additions

def export()->None:
    a=cq.Assembly(name="proposed_split_guide_correction")
    for p in build():a.add(p.shape,name=p.name,color=cq.Color(*p.color))
    a.save(str(OUT/"split-guide-correction.step"))

if __name__=="__main__":export()
