"""Production-mechanism exploration; dimensions mm, glass surface z=0.

Threaded joints use cylindrical envelopes. Flexible items are not rigid solids
for collision decisions. Material, force, seal and insulation qualification absent.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
from math import cos, sin, radians
from pathlib import Path
import sys
import cadquery as cq

OUT=Path(__file__).resolve().parent


@dataclass(frozen=True)
class Part:
    name: str
    shape: cq.Shape
    color: tuple[float,float,float]
    moving: bool=False
    envelope: bool=False


METAL=(.66,.72,.72)
CERAMIC=(.85,.79,.66)
SEAL=(.79,.48,.25)
DARK=(.25,.34,.32)


def ring(ro: float,ri: float,z: float,h: float) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z).circle(ro).circle(ri).extrude(h)


def hole(w: cq.Workplane,x: float,y: float,r: float,z: float,h: float) -> cq.Workplane:
    return w.cut(cq.Workplane("XY").workplane(offset=z).center(x,y).circle(r).extrude(h))


def polar(radius: float,offset: float=0) -> list[tuple[float,float]]:
    return [(radius*cos(radians(offset+a)),radius*sin(radians(offset+a))) for a in (0,120,240)]


def build(travel_mm: float=0.0,seal_variant: str="diaphragm",stem_d: float=6.,guide_bore_d: float=6.4,max_travel: float=1.2) -> list[Part]:
    if seal_variant not in ("diaphragm","bellows"): raise ValueError(seal_variant)
    if not 0<=travel_mm<=1.4: raise ValueError("Exploration travel outside fixture range")
    parts=[]
    def add(name: str,w: cq.Workplane,color: tuple=METAL,moving: bool=False,envelope: bool=False) -> None:
        shape=w.val().translate((0,0,-travel_mm)) if moving else w.val()
        parts.append(Part(name,shape,color,moving,envelope))
    stop=-2-max_travel
    flange_bottom=stop-1 if seal_variant=="diaphragm" else -14.
    # Body has an independent mounting flange and a bolt-off lower spring chamber.
    body=ring(10,5.2,-25,11).union(ring(13,5.2,-29,4)).union(ring(16,5.2,-22,3))
    if seal_variant=="diaphragm":
        body=body.union(ring(8.5,5.2,-14,flange_bottom+14)).union(ring(8.5,7.,flange_bottom,-.8-flange_bottom))
    else:
        body=body.union(ring(8.5,7.,-14,13.2))
    for x,y in polar(12.5): body=hole(body,x,y,1.45,-25,12)
    for x,y in polar(10.2,60): body=hole(body,x,y,1.25,-30,6)
    add("body_with_independent_flange",body)
    # Guide is clamped mechanically, never retained by the flexible seal.
    guide=ring(5,guide_bore_d/2,-14,stop+14).union(ring(6.6,guide_bore_d/2,flange_bottom,1))
    add("insulating_guide",guide,CERAMIC)
    retainer=ring(7,5.2,flange_bottom+1,.6)
    for x in (-6.1,6.1):
        retainer=retainer.cut(cq.Workplane("XY").box(.7,2,.25).translate((x,0,flange_bottom+1.55)))
    add("M14_retainer_thread_envelope",retainer,DARK)
    # Positive upper stop: open retaining clip in a groove beneath guide.
    stem=ring(stem_d/2,1.4,-19,17).union(ring(4.8,1.4,-2,.6))
    stem=stem.cut(ring(stem_d/2+.1,2.7,-14.75,.75))
    add("hollow_insulating_plunger_with_capture_groove",stem,CERAMIC,True)
    clip=ring(4.9,2.7,-14.6,.6).cut(cq.Workplane("XY").box(3.5,7,1).translate((0,-4,-14.3)))
    add("upper_capture_clip_geometry_candidate",clip,DARK,True)
    cap=cq.Workplane("XY").workplane(offset=.25).circle(5).extrude(.35).union(ring(5,4.6,-1.4,1.65))
    if seal_variant=="bellows":
        cap=cap.union(ring(5,4.8,-2,.6)).union(ring(6.4,4.8,-2,.2))
    add("contact_cap",cap,METAL,True)
    add("dielectric_bond",cq.Workplane("XY").box(3.8,2.8,.2).translate((0,0,.15)),(.91,.77,.46),True)
    add("PT100_element",cq.Workplane("XY").box(3,2,.4).translate((0,0,-.15)),(.78,.32,.25),True)
    # Seal outer clamp and static glass interface are distinct from guide capture.
    add("outer_seal_clamp",ring(8.5,7.5,-.6,.35))
    add("static_glass_aperture_seal_ENVELOPE",ring(9,8.5,-4,3.75),SEAL,envelope=True)
    if seal_variant=="diaphragm":
        z=-.5-travel_mm; valley=-1.4-.5*travel_mm
        pts=[(5,z),(5.6,z),(6.3,valley),(7.5,-.6),(8.5,-.6),(8.5,-.8),(7.5,-.8),(6.3,valley-.2),(5.6,z-.2),(5,z-.2)]
        add("flex_diaphragm_ENVELOPE",cq.Workplane("XZ").polyline(pts).close().revolve(),SEAL,envelope=True)
    else:
        # Convolution envelope, not formed-bellows tooling or a fatigue prediction.
        top=-2-travel_mm; bottom=-10.
        outer=[]
        for i in range(13):
            z=top+(bottom-top)*i/12
            outer.append((5.35 if i%2==0 else 6.65,z))
        inner=[(r-.15,z) for r,z in reversed(outer)]
        add("recessed_bellows_ENVELOPE",cq.Workplane("XZ").polyline(outer+inner).close().revolve(),SEAL,envelope=True)
        add("bellows_lower_attachment_ENVELOPE",ring(7,5.2,-10.3,.3),SEAL,envelope=True)
        add("protective_wipe_rim",ring(8.5,5.8,-.25,.15),CERAMIC)
    # Bolt-off cap avoids winding the sensor harness during service.
    lower=ring(13,1.8,-33,4).union(ring(5.2,1.8,-29,1))
    lower=lower.cut(cq.Workplane("XY").workplane(offset=-34).circle(3).extrude(3))
    for x,y in polar(10.2,60): lower=hole(lower,x,y,1.45,-34,6)
    add("lower_spring_cap",lower)
    for i,(x,y) in enumerate(polar(10.2,60)):
        bolt=(cq.Workplane("XY").workplane(offset=-33).center(x,y).circle(1.25).extrude(8)
              .union(cq.Workplane("XY").workplane(offset=-35.5).center(x,y).circle(2.25).extrude(2.5)))
        add(f"lower_M2p5x8_screw_{i+1}_thread_envelope",bolt,DARK)
    for i,(x,y) in enumerate(polar(12.5)):
        bolt=(cq.Workplane("XY").workplane(offset=-22).center(x,y).circle(1.25).extrude(8)
              .union(cq.Workplane("XY").workplane(offset=-24.5).center(x,y).circle(2.25).extrude(2.5)))
        add(f"mount_M2p5x8_screw_{i+1}_thread_envelope",bolt,DARK)
    gland=cq.Workplane("XY").workplane(offset=-39).polygon(6,8).extrude(6).union(ring(3,1.5,-33,2))
    gland=gland.cut(cq.Workplane("XY").workplane(offset=-40).circle(1.5).extrude(10))
    add("M6_gland_body_thread_envelope",gland,DARK)
    add("compression_bushing_ENVELOPE",ring(1.5,.8,-39,6),SEAL,envelope=True)
    # Spring compresses as tip moves. Helix force/stress is deliberately not inferred.
    spring_height=12.9-travel_mm
    path=cq.Wire.makeHelix(spring_height/6,spring_height,3.9)
    spring=(cq.Workplane("XZ").center(3.9,0).circle(.25).sweep(path,isFrenet=True).translate((0,0,-27.75)))
    add("compression_spring_ENVELOPE",spring,DARK,envelope=True)
    # Reserved compliant lead route through stem and gland; no claimed bend-life rating.
    lead=cq.Workplane("XY").workplane(offset=-19-travel_mm).circle(.7).extrude(17.8)
    curve=cq.Workplane("XZ").moveTo(0,-19-travel_mm).spline([(1.7,-22),(-1.7,-25),(0,-28)],includeCurrent=True).val()
    loop=cq.Workplane("XY").workplane(offset=-19-travel_mm).circle(.7).sweep(cq.Wire.assembleEdges([curve]),isFrenet=True)
    lead=lead.union(loop).union(cq.Workplane("XY").workplane(offset=-49).circle(.7).extrude(21))
    add("four_wire_slack_and_exit_ENVELOPE",lead,(.67,.34,.26),envelope=True)
    return parts


def rigid_intersections(parts: list[Part]) -> list[dict]:
    out=[]
    for i,a in enumerate(parts):
        if a.envelope: continue
        for b in parts[i+1:]:
            if b.envelope: continue
            aa,bb=a.shape.BoundingBox(),b.shape.BoundingBox()
            if aa.xmax<bb.xmin or bb.xmax<aa.xmin or aa.ymax<bb.ymin or bb.ymax<aa.ymin or aa.zmax<bb.zmin or bb.zmax<aa.zmin: continue
            v=a.shape.intersect(b.shape).Volume()
            if v>.0001: out.append({"a":a.name,"b":b.name,"overlap_mm3":round(v,6)})
    return out


def save(parts: list[Part],name: str,individual: bool=False) -> dict:
    assembly=cq.Assembly(name=name)
    metadata=[]
    for p in parts:
        assembly.add(p.shape,name=p.name,color=cq.Color(*p.color))
        path=f"parts/{p.name}.step"
        if individual:
            (OUT/"parts").mkdir(exist_ok=True)
            cq.exporters.export(p.shape,str(OUT/path))
        b=p.shape.BoundingBox()
        metadata.append({"name":p.name,"color":p.color,"moving":p.moving,"envelope":p.envelope,"step":path,"valid":p.shape.isValid(),"bbox":[b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax]})
    assembly.save(str(OUT/(name+".step")))
    imported=cq.importers.importStep(str(OUT/(name+".step"))).solids().vals()
    if individual: (OUT/"parts.json").write_text(json.dumps({"origin":"glass top center; z up; mm","parts":metadata},indent=2)+"\n")
    return {"parts":len(parts),"all_valid":all(p.shape.isValid() for p in parts),"roundtrip_solids":len(imported),"roundtrip_all_valid":all(s.isValid() for s in imported),"rigid_overlaps":rigid_intersections(parts)}


def main() -> None:
    report={"status":"computed geometry only; no force/thermal/EMC/seal/material validation","states":{},"tolerance_assumptions":{"stem_d_mm":[5.97,6.03],"guide_bore_d_mm":[6.35,6.45],"radial_running_clearance_mm":[.16,.24],"lower_stop_stack_mm":[1.05,1.35],"glass_hole_d_mm":[17.9,18.1],"neck_d_mm":[16.95,17.05],"minimum_radial_glass_clearance_mm":.425},"sweeps":[]}
    for variant in ("diaphragm","bellows"):
        for label,travel in (("rest",0.),("loaded",.6),("full",1.2)):
            name=f"sensor-{variant}-{label}"
            report["states"][name]=save(build(travel,variant),name,individual=(variant=="diaphragm" and label=="rest"))
        for stem,bore,gap in ((6.03,6.35,1.05),(5.97,6.45,1.35)):
            for requested in (0.,.6,1.2):
                allowed=min(requested,gap)
                parts=build(allowed,variant,stem,bore,gap)
                report["sweeps"].append({"variant":variant,"stem_d":stem,"bore_d":bore,"stop_gap":gap,"requested_travel":requested,"actual_stop_limited_travel":allowed,"blocked_before_requested":requested>gap,"rigid_overlaps":rigid_intersections(parts),"valid":all(p.shape.isValid() for p in parts)})
    parts=build()
    clip=cq.Workplane("XY").box(80,40,160,centered=(True,False,True)).val()
    exploded=[]
    for p in parts:
        delta=0.
        if p.name.startswith("lower_") or "gland" in p.name or "bushing" in p.name: delta=-18.
        if "spring_ENVELOPE" in p.name: delta=-8.
        shape=p.shape.intersect(clip).translate((0,0,delta))
        if shape.Volume()>1e-7: exploded.append(Part(p.name,shape,p.color,p.moving,p.envelope))
    report["exploded_section"]=save(exploded,"sensor-exploded-section")
    (OUT/"geometry-checks.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"state_count":len(report["states"]),"nominal_overlap_count":sum(len(s["rigid_overlaps"]) for s in report["states"].values()),"sweep_count":len(report["sweeps"]),"sweep_overlaps":sum(len(s["rigid_overlaps"]) for s in report["sweeps"])}))


if __name__=="__main__": main()
