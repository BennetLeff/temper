"""Proposed mechanically captured cap; not material/thermal qualification."""
from pathlib import Path
import importlib.util
import sys
import cadquery as cq

ORIGINAL=Path(__file__).resolve().parent/"sensor_original.py"
spec=importlib.util.spec_from_file_location("sensor_original_for_audit",ORIGINAL)
assert spec and spec.loader
original=importlib.util.module_from_spec(spec);sys.modules[spec.name]=original;spec.loader.exec_module(original)
Part=original.Part


def build(travel_mm: float=0.) -> list[Part]:
    """Same local origin; use lower guide flange to clear a Ø12 rolled-lip cap."""
    parts=[]
    omitted={"contact_cap","hollow_insulating_plunger_with_capture_groove","M14_retainer_thread_envelope","recessed_bellows_ENVELOPE","bellows_lower_attachment_ENVELOPE","protective_wipe_rim"}
    for p in original.build(travel_mm,"bellows"):
        if p.name not in omitted: parts.append(p)
    retainer=original.ring(7,5.7,-13,.6)
    for x in (-6.5,6.5):
        retainer=retainer.cut(cq.Workplane("XY").box(.5,1,.3).translate((x,0,-12.5)))
    parts.append(Part("M14_retainer_thread_envelope",retainer.val(),original.DARK))
    plunger=original.ring(3,1.4,-19,17).union(original.ring(5.5,1.4,-2,.6))
    plunger=plunger.cut(original.ring(3.1,2.7,-14.75,.75))
    parts.append(Part("hollow_insulating_plunger_with_capture_groove",plunger.val().translate((0,0,-travel_mm)),original.CERAMIC,True))
    cap=(cq.Workplane("XY").workplane(offset=.25).circle(6).extrude(.35)
         .union(original.ring(6,5.6,-2.25,2.5))
         .union(original.ring(6,5.2,-1.4,.3))
         .union(original.ring(6,5.2,-2.25,.2)))
    parts.append(Part("contact_cap_with_proposed_rolled_capture_lip",cap.val().translate((0,0,-travel_mm)),original.METAL,True))
    z=-.5-travel_mm;valley=-1.5-.5*travel_mm
    points=[(6,z),(6.2,z),(6.7,valley),(7.5,-.6),(8.5,-.6),(8.5,-.8),(7.5,-.8),(6.7,valley-.2),(6.2,z-.2),(6,z-.2)]
    seal=cq.Workplane("XZ").polyline(points).close().revolve().val()
    parts.append(Part("flex_diaphragm_ENVELOPE",seal,original.SEAL,False,True))
    return parts


if __name__=="__main__":
    out=Path(__file__).resolve().parent
    for label,travel in (("rest",0.),("loaded",.6),("full",1.2)):
        a=cq.Assembly(name="proposed_captured_cap_"+label)
        for p in build(travel): a.add(p.shape,name=p.name,color=cq.Color(*p.color))
        a.save(str(out/("corrected-"+label+".step")))
