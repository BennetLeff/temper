"""Magnetic knob mechanism study. Millimetres; fascia outside Z=0, +Z outward.

Flexible coils/retaining clip and magnetic fields are not validated by rigid CAD.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from math import pi,sin,cos,radians
import json
import cadquery as cq
import numpy as np

OUT=Path(__file__).resolve().parent
SILVER=(.73,.75,.77); DARK=(.21,.24,.26); BLUE=(.23,.46,.59); GREEN=(.24,.45,.35); RED=(.69,.31,.26); AMBER=(.84,.61,.25)

@dataclass(frozen=True)
class Part:
    name:str
    shape:cq.Shape
    color:tuple[float,float,float]
    removable:bool=False
    envelope:bool=False

def disk(r:float,z:float,h:float,x:float=0,y:float=0,ri:float=0)->cq.Shape:
    wp=cq.Workplane("XY").workplane(offset=z).center(x,y).circle(r)
    if ri:wp=wp.circle(ri)
    return wp.extrude(h).val()

def box(w:float,d:float,z:float,h:float,x:float=0,y:float=0)->cq.Shape:
    return cq.Workplane("XY").box(w,d,h,centered=(True,True,False)).translate((x,y,z)).val()

def radial_cyl(r:float,x:float,length:float,z:float=10.5)->cq.Shape:
    return cq.Solid.makeCylinder(r,length,cq.Vector(x,0,z),cq.Vector(1,0,0))

PROFILE=np.array([[(21+.15*cos(24*a))*cos(a),(21+.15*cos(24*a))*sin(a)] for a in np.linspace(0,2*pi,385)[:-1]])

def follower_center(angle_deg:float)->float:
    a=radians(angle_deg)
    rotation=np.array([[cos(a),-sin(a)],[sin(a),cos(a)]])
    p=PROFILE@rotation.T
    q=np.roll(p,-1,axis=0);edge=q-p
    def clearance(r:float)->float:
        point=np.array([r,0.])
        t=np.clip(np.sum((point-p)*edge,axis=1)/np.sum(edge*edge,axis=1),0,1)
        return np.linalg.norm(point-(p+t[:,None]*edge),axis=1).min()
    lo,hi=19.,20.3
    for _ in range(45):
        mid=(lo+hi)/2
        if clearance(mid)>1.0001:lo=mid
        else:hi=mid
    return (lo+hi)/2

@lru_cache(maxsize=128)
def coil(length:float,mean_d:float,wire:float,turns:int)->cq.Shape:
    path=cq.Wire.makeHelix((length-wire)/turns,length-wire,mean_d/2)
    return cq.Workplane("XY").center(mean_d/2,0).circle(wire/2).sweep(cq.Workplane(obj=path),isFrenet=True).val().translate((0,0,wire/2))

@lru_cache(maxsize=1)
def fixed_geometry()->tuple[cq.Shape,cq.Shape,cq.Shape,cq.Shape]:
    shoe=disk(23,.6,4.4,ri=6.2).cut(disk(8.7,.5,1.5))
    for i in range(3):
        a=2*pi*i/3;x,y=18*cos(a),18*sin(a)
        shoe=shoe.cut(disk(3.1,.5,4.0,x,y))
    # A bolted top flange locates/captures the low-friction hub bushing.
    collar=disk(10,5,6,ri=7.35)
    for deg in(60,180,300):
        a=radians(deg);collar=collar.cut(disk(.8,8,4,8.6*cos(a),8.6*sin(a)))
    shoe=shoe.fuse(collar)
    # Guides and return-key towers are integral to the stationary shoe.
    guide=box(4.75,3.6,5,7.4,16.875)
    guide=guide.cut(radial_cyl(1.25,14.8,4.0)).cut(radial_cyl(.95,18.8,1.4))
    shoe=shoe.fuse(guide).fuse(guide.rotate((0,0,0),(0,0,1),180))
    washer=disk(14,13,1,ri=7.5)
    for deg in(60,180,300):
        key=box(1.4,1.2,5,7.9,13.5).rotate((0,0,0),(0,0,1),deg)
        shoe=shoe.fuse(key)
        slot=box(2.0,1.6,12,4,13.5).rotate((0,0,0),(0,0,1),deg)
        washer=washer.cut(slot)
        a=radians(deg)
        shoe=shoe.fuse(disk(1,5,7.4,11.5*cos(a),11.5*sin(a)))
    cap=disk(25,4,16).cut(disk(23.4,3.9,2.1))
    inside=cq.Workplane("XY").workplane(offset=6).spline(PROFILE.tolist(),periodic=True).close().extrude(12.5).val()
    cap=cap.cut(inside)
    cap=cq.Workplane(obj=cap).edges(">Z").fillet(1).val()
    for i in range(48):
        a=2*pi*i/48
        cap=cap.cut(disk(1.2,6,10,25.8*cos(a),25.8*sin(a)))
    hub=disk(6,.8,17.7).cut(disk(4.1,.7,2.6)).cut(disk(6.1,1.175,.85,ri=5.4))
    actuator=disk(14,14,4.5,ri=7.5)
    cap=cap.fuse(hub).fuse(actuator)
    clip=disk(8.5,1.2,.8,ri=5.5).cut(box(10,6.5,1,1.2,7.5))
    for y in(-4.2,4.2):clip=clip.cut(disk(.5,1,1.2,6,y))
    return shoe,cap,washer,clip

def fascia_pocket()->cq.Shape:
    return disk(31,-3.5,1.5)

def build(angle_deg:float=0,press_mm:float=0,removed_mm:float=0,include_mounts:bool=True,show_springs:bool=True)->list[Part]:
    if not 0<=press_mm<=.6:raise ValueError("Press outside modeled stroke")
    parts=[]
    def add(name:str,shape:cq.Shape,color:tuple[float,float,float],removable:bool=False,envelope:bool=False,rotor:bool=False,axial:bool=False)->None:
        if rotor:shape=shape.rotate((0,0,0),(0,0,1),angle_deg)
        if rotor or axial:shape=shape.translate((0,0,-press_mm))
        if removable:shape=shape.translate((0,0,removed_mm))
        parts.append(Part(name,shape,color,removable,envelope))
    shoe,cap,washer,clip=fixed_geometry()
    add("stationary_shoe_integral_guides",shoe,DARK,True)
    add("silver_rotor_integral_radial_cam",cap,SILVER,True,rotor=True)
    add("keyed_thrust_washer",washer,BLUE,True,axial=True)
    add("flexible_retaining_clip_candidate",clip,AMBER,True,True,rotor=True)
    bushing=disk(7.3,5,6,ri=6.2).fuse(disk(10,11,1,ri=6.2))
    for deg in(60,180,300):
        a=radians(deg);x,y=8.6*cos(a),8.6*sin(a)
        bushing=bushing.cut(disk(.8,10,3,x,y)).cut(cq.Solid.makeCone(.8,1.35,.8,cq.Vector(x,y,11.2)))
        fastener=disk(.7,8.5,2.7,x,y).fuse(cq.Solid.makeCone(.7,1.3,.8,cq.Vector(x,y,11.2)))
        add(f"bushing_capture_screw_{deg}_threads_omitted",fastener,SILVER,True)
    add("flanged_hub_guide_bushing",bushing,BLUE,True)
    add("diametric_sensing_magnet",disk(4,1.2,2),RED,True,rotor=True)
    for i in range(3):
        a=2*pi*i/3;x,y=18*cos(a),18*sin(a)
        add(f"puck_retention_magnet_{i}",disk(3,1.25,3.2,x,y),RED,True)
        add(f"bonded_magnet_pocket_cover_{i}",disk(3.05,.6,.6,x,y),DARK,True)
        add(f"nonmarking_stationary_pad_{i}",disk(3,0,.6,x,y),DARK,True)
        x,y=12*cos(a),12*sin(a)
        if show_springs:add(f"axial_return_coil_{i}",coil(round(8-press_mm,6),3,.3,6).translate((x,y,5)),AMBER,True,True)
    center=follower_center(angle_deg)
    base=center-2.1
    follower=radial_cyl(.85,base,2.1).fuse(radial_cyl(1.1,base,.3)).fuse(cq.Solid.makeSphere(1,cq.Vector(center,0,10.5),angleDegrees1=-90,angleDegrees2=90))
    for deg in(0,180):
        add(f"rounded_radial_follower_{deg}",follower.rotate((0,0,0),(0,0,1),deg),BLUE,True)
        if show_springs:
            spring=coil(round(base-14.8,6),2,.25,4).rotate((0,0,0),(0,1,0),90).translate((14.8,0,10.5)).rotate((0,0,0),(0,0,1),deg)
            add(f"radial_detent_coil_{deg}",spring,AMBER,True,True)
    if include_mounts:
        mount=box(68,60,-10,2)
        for x in(-28,28):
            for y in(-24,24):
                hole=disk(1.7,-11,4,x,y);mount=mount.cut(hole)
                add(f"shell_mount_boss_{x}_{y}",disk(3.5,-8,4.5,x,y,1.3),SILVER)
        for i in range(3):
            a=2*pi*i/3;x,y=18*cos(a),18*sin(a)
            pod=disk(4.2,-8,5.8,x,y).cut(disk(3.1,-5.5,3.4,x,y))
            mount=mount.fuse(pod)
            add(f"rear_retention_magnet_{i}",disk(3,-5.45,3.2,x,y),RED)
        board=box(16,16,-5.4,1.6)
        for x in(-5.8,5.8):
            for y in(-5.8,5.8):
                board=board.cut(disk(1.1,-6,4,x,y))
                standoff=disk(2,-8,2.6,x,y,1.1)
                mount=mount.fuse(standoff)
        add("rear_carrier_with_sensor_standoffs",mount,DARK)
        add("Hall_board_envelope",board,GREEN,False,True)
        add("Hall_package_envelope",box(3,3,-3.8,.8),DARK,False,True)
    return parts

def collisions(parts:list[Part])->list[dict]:
    rigid=[p for p in parts if not p.envelope]
    result=[]
    for i,a in enumerate(rigid):
        ba=a.shape.BoundingBox()
        for b in rigid[i+1:]:
            bb=b.shape.BoundingBox()
            if any(getattr(ba,k+"max")<=getattr(bb,k+"min")+1e-6 or getattr(bb,k+"max")<=getattr(ba,k+"min")+1e-6 for k in("x","y","z")):continue
            v=a.shape.intersect(b.shape).Volume()
            if v>1e-4:result.append({"a":a.name,"b":b.name,"mm3":round(v,6)})
    return result

def export(parts:list[Part],filename:str)->None:
    assembly=cq.Assembly(name="temper_knob")
    for p in parts:assembly.add(p.shape,name=p.name,color=cq.Color(*p.color))
    assembly.save(str(OUT/filename))

def main()->None:
    OUT.mkdir(exist_ok=True)
    rest=build()
    export(rest,"knob-rest.step")
    export(build(7.5,.6),"knob-pressed.step")
    export(build(removed_mm=35),"knob-removed.step")
    exploded=[]
    for p in rest:
        offset=0
        if p.removable:offset=24
        if "rotor" in p.name or "sensing_magnet" in p.name:offset=53
        if "washer" in p.name:offset=39
        exploded.append(Part(p.name,p.shape.translate((0,0,offset)),p.color,p.removable,p.envelope))
    export(exploded,"knob-exploded.step")
    folder=OUT/"parts";folder.mkdir(exist_ok=True)
    inventory=[]
    for p in rest:
        filename=f"parts/{p.name}.step";cq.exporters.export(p.shape,str(OUT/filename))
        inventory.append({"name":p.name,"shape":filename,"color":p.color,"removable":p.removable,"envelope":p.envelope,"valid":p.shape.isValid()})
    (OUT/"parts.json").write_text(json.dumps(inventory,indent=2))
    sweep=[]
    for angle in np.linspace(0,15,9):
        for press in(0,.3,.6):
            parts=build(float(angle),press,show_springs=False)
            sweep.append({"angle_deg":float(angle),"press_mm":press,"follower_radius_mm":follower_center(float(angle)),"rigid_intersections":collisions(parts),"all_shapes_valid":all(p.shape.isValid() for p in parts)})
    results={"scope":"Rigid sampled kinematics, not magnetic, friction, spring fatigue or seal validation","flexible_excluded":["five coil springs","retaining clip"],"electronics":"envelopes excluded from rigid proof","all_rest_shapes_valid":all(p.shape.isValid() for p in rest),"sweep":sweep,"all_sweep_clear":all(not s["rigid_intersections"] and s["all_shapes_valid"] for s in sweep)}
    (OUT/"motion-validation.json").write_text(json.dumps(results,indent=2))
    print(json.dumps({"parts":len(rest),"rest_valid":results["all_rest_shapes_valid"],"samples":len(sweep),"sweep_clear":results["all_sweep_clear"],"first_collisions":[s for s in sweep if s["rigid_intersections"]][:1]}))

if __name__=="__main__":main()
