"""Temper R1: integrated folded prototype revision. mm; geometry, not qualification."""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
from math import pi, cos, sin, radians, sqrt
import importlib.util
import sys
import json
import gzip
import hashlib
import cadquery as cq

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent

def load(name: str, path: Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

base=load('revision_enclosure_base',ROOT/'enclosure.py')
pack=load('revision_packaging_base',ROOT/'reference/packaging.py')
kc=load('revision_knob_previous_correction',ROOT/'reference/knob_correction.py')
sc=load('revision_sensor_previous_correction',ROOT/'reference/sensor_correction.py')

@dataclass(frozen=True)
class Part:
    name: str
    shape: cq.Shape
    color: tuple[float,float,float]
    group: str
    evidence: str='proposed rigid geometry'
    envelope: bool=False

SILVER=(.72,.75,.73); DARK=(.28,.34,.32); SEAL=(.73,.43,.22)
box=base.box
cyl=base.cylinder

def ring(ro: float,ri: float,z: float,h: float,x: float=0,y: float=0) -> cq.Shape:
    return cyl(ro,h,x,y,z).cut(cyl(ri,h+2,x,y,z-1))

def front(s: cq.Shape) -> cq.Shape:
    return s.translate((110,53,0)).rotate((0,0,0),(1,0,0),35).translate((0,0,base.FRONT_Z))

def historical_pcb_world(s: cq.Shape) -> cq.Shape:
    """Place the R4 inherited PCB export after the packaging -4 mm correction.

    This is the older imported board, not the current 240 x 160 mm full bridge.
    Keep this transform shared by the panel and general saved-geometry checks.
    """
    return s.translate((-90,137,0)).rotate((0,0,0),(0,0,1),90).translate((0,150,30.25))

def hexnut(x: float,y: float,z: float,across_flats: float=5.5,h: float=2.4,hole: float=1.45) -> cq.Shape:
    return cq.Workplane('XY').workplane(offset=z).center(x,y).polygon(6,across_flats/cos(pi/6)).extrude(h).val().cut(cyl(hole,h+2,x,y,z-1))

def knob(angle: float=0,press: float=0) -> list[Part]:
    result=[]
    for p in kc.build(angle,press):
        if p.name.startswith('shell_mount_boss'): continue
        shape=p.shape
        if p.name=='corrected_open_trough_shoe':
            # A longer replaceable hub bearing and a flat drop-in click-cartridge seat.
            shape=shape.cut(ring(7.4,6.1,2.1,3.0))
            shape=shape.cut(box(12.5,8.5,1.0,0,-16,4.25))
            shape=shape.cut(cyl(2.3,1.3,0,-20,.4))
            for x in(-4.8,4.8):shape=shape.cut(cyl(.7,2.5,x,-16,2.8))
            for deg in(60,180,300):
                a=radians(deg);shape=shape.fuse(cyl(1,.05,11.5*cos(a),11.5*sin(a),12.4))
        elif p.name=='flanged_hub_guide_bushing':
            shape=shape.fuse(ring(7.3,6.2,2.1,2.9))
        elif p.name=='keyed_thrust_washer':
            tab=box(6,7.5,1,0,-15.25,13-press)
            push=cyl(1.5,3.5,0,-16,9.5-press)
            shape=shape.fuse(tab).fuse(push)
        result.append(Part(p.name,shape,p.color,'knob',envelope=p.envelope))
    # Tactile candidate: supplier envelope and actuator. Max mechanical stroke is
    # NOT specified in the cited sheet. Thus this is not a closed click solution.
    board=box(12,8,.6,0,-16,4.4)
    for x in(-4.8,4.8):board=board.cut(cyl(.85,2,x,-16,4))
    result.append(Part('click_cartridge_removable_seat',board,(.25,.48,.34),'knob'))
    switch=box(6,6,3.45,0,-16,5)
    result.append(Part('CK_PTS645SH43SMTR92_LFS_BODY_ENVELOPE',switch,DARK,'knob','supplier 6x6; body envelope; no electrical connection',True))
    switch_travel=max(0,press-.2)
    result.append(Part('CK_tactile_actuator_ENVELOPE',cyl(1.75,.85-switch_travel,0,-16,8.45),(.80,.75,.57),'knob','prescribed travel; supplier overtravel permission absent',True))
    for x in(-4.8,4.8):
        screw=cyl(.65,2.2,x,-16,2.8).fuse(cyl(1.3,.5,x,-16,5))
        result.append(Part(f'click_seat_M1p4_screw_{x}',screw,SILVER,'knob','thread envelope'))
    key=cq.Workplane('XY').workplane(offset=.15).center(0,-20).circle(2).extrude(.85).edges('>Z').fillet(.3).val()
    result += [Part('optional_bonded_round_antirotation_key',key,SILVER,'knob','positive key geometry; adhesive/shear unqualified'),
               Part('key_bondline_ENVELOPE',cyl(2,.15,0,-20,0),SEAL,'knob','bond process unselected',True)]
    # Backside-bonded stud candidates replace the old bosses that floated 1.5mm off
    # this thinner sheet. Fascia remains without a through-hole beneath the knob.
    for x in(-28,28):
        for y in(-24,24):
            stud=cyl(1.4,10.2,x,y,-12.4).fuse(cyl(3.1,.7,x,y,-2.9))
            result.append(Part(f'rear_bond_stud_{x}_{y}',stud,SILVER,'knob','bonded stud candidate; attachment unqualified'))
            result.append(Part(f'rear_stud_bondline_{x}_{y}',cyl(3.1,.2,x,y,-2.2),SEAL,'knob','bondline allocation',True))
            result.append(Part(f'rear_stud_nut_{x}_{y}',hexnut(x,y,-12.4,h=2.4,hole=1.45),DARK,'knob','M3 envelope'))
    return result


def sensor(travel: float=0.) -> list[Part]:
    result=[]
    omit={'static_glass_aperture_seal_ENVELOPE','outer_seal_clamp','M6_gland_body_thread_envelope','compression_bushing_ENVELOPE'}
    for p in sc.build(travel):
        if p.name in omit:continue
        shape=p.shape
        if p.name=='body_with_independent_flange':
            shape=shape.cut(ring(8.6,8,-2.5,1.7))
            gland=ring(11.8,8.5,-6,1.85)
            gland=gland.cut(ring(11.05,9.1,-5.15,1.2))
            shape=shape.fuse(gland)
            shape=shape.fuse(ring(19,5.2,-22,3))
            for deg in(0,120,240):
                a=radians(deg);shape=shape.cut(cyl(1.45,8,15*cos(a),15*sin(a),-25))
        if p.name.startswith('mount_M2p5x8_screw_'):
            i=int(p.name.split('_')[3])-1;a=radians(i*120)
            shape=shape.translate((2.5*cos(a),2.5*sin(a),0))
        if p.name=='contact_cap_with_proposed_rolled_capture_lip':
            shape=shape.cut(ring(6.1,5.8,-1.0-travel,.7))
        if p.name=='flex_diaphragm_ENVELOPE':
            shape=shape.fuse(ring(6.2,5.8,-1-travel,.7))
        result.append(Part(p.name,shape,p.color,'sensor','flexible/electronics allocation' if p.envelope else 'proposed rigid geometry',p.envelope))
    # Nominal circular-section O-ring 18.65 ID x1.50 CS -> mean radius10.075.
    # Installed elliptical section preserves nominal cross-sectional area.
    semi_h=.575;semi_w=.75*.75/semi_h
    seal=cq.Workplane('XZ').center(10.075,-4.575).ellipse(semi_w,semi_h).revolve(360,( -10.075,0),(-10.075,1)).val()
    # Workplane.center changes revolve origin; explicit profile in world local avoids ambiguity.
    pts=[(10.075+semi_w*cos(i*pi/24),-4.575+semi_h*sin(i*pi/24)) for i in range(48)]
    seal=cq.Workplane('XZ').polyline(pts).close().revolve().val()
    result.append(Part('static_face_seal_1p50CS_INSTALLED_ENVELOPE',seal,SEAL,'sensor','nominal squeeze23.3%; compound unselected',True))
    for deg in(0,120,240):
        x,y=11.45*cos(radians(deg)),11.45*sin(radians(deg))
        result.append(Part(f'glass_face_datum_pad_{deg}',cyl(.3,.15,x,y,-4.15),(.75,.72,.62),'sensor','thin dielectric datum; load unqualified'))
    clamp=ring(8.5,7.5,-.6,.35).fuse(ring(8.5,8,-2.5,1.9))
    for x in(-8.1,8.1):clamp=clamp.cut(box(.5,1,.3,x,0,-.5))
    result.append(Part('M16_clamp_skirt_thread_ENVELOPE',clamp,SILVER,'sensor','thread flank simplified; clamp attachment geometry'))
    fixed=(hexnut(0,0,-36,7,3,1.5).fuse(ring(3,1.5,-33,2)).fuse(ring(2.8,1.5,-39,3)))
    nut=hexnut(0,0,-42,8,5.8,2.85).fuse(ring(3,1.0,-42,1))
    result += [Part('M6_fixed_cable_gland_body_thread_ENVELOPE',fixed,DARK,'sensor','custom concept, not selected supplier gland'),
               Part('M6_compression_nut_thread_ENVELOPE',nut,DARK,'sensor','thread envelope; axially drives bushing'),
               Part('cable_compression_bushing_INSTALLED_ENVELOPE',ring(1.48,.70,-41,8),SEAL,'sensor','installed bore tangent to1.4mm cable; free bushing/compression force unselected',True)]
    return result


def enclosures():
    original,flats,segments,bends,length=base.main()
    result=[]
    for p in original:
        if p.name.startswith(('top_screw_head','side_screw_head')):continue
        name=p.name.replace('washer_stack_2p4_ENVELOPE','single_spacer_2p4')
        evidence='proposed rigid geometry'
        if name.startswith('single_spacer'): evidence='2.4mm cut-to-length tube spacer or measured shim stack; not catalog height'
        result.append(Part(name,p.shape,p.color,p.group,evidence,p.group=='gasket'))
    # Replace fixed connector openings with replaceable adapter blanks.
    cover=next(p for p in result if p.group=='cover')
    rear_seg=segments[3]
    rear_plane=cq.Plane(origin=(0,*rear_seg['start']),xDir=(1,0,0),normal=(0,1,0))
    # Shared feature geometry updates both formed cover and its developed blank.
    f=base.Feature(3,135,rear_seg['start'][1]-34,44,30,3)
    shape=cover.shape.cut(base.cutter(f,rear_plane));flats['cover']=base.flat_cut(flats['cover'],f,rear_seg['flat_start'])
    for x in(106,164):
        f=base.Feature(3,x,rear_seg['start'][1]-34,3.4,3.4,kind='circle')
        shape=shape.cut(base.cutter(f,rear_plane));flats['cover']=base.flat_cut(flats['cover'],f,rear_seg['flat_start'])
    result=[replace(p,shape=shape) if p is cover else p for p in result]
    mains=box(68,2,42,135,441,13)
    for x in(106,164):mains=mains.cut(cq.Solid.makeCylinder(1.7,5,cq.Vector(x,438,34),cq.Vector(0,1,0)))
    result.append(Part('mains_connector_REPLACEABLE_BLANK',mains,SILVER,'adapters','blank pending rated inlet drawing'))
    flats['mains-adapter-blank']=mains.rotate((0,0,0),(1,0,0),90).translate((-135,34,-440))
    tray=next(p for p in result if p.name=='two_bend_bottom_and_sides')
    shape=tray.shape
    aperture=box(6,24,24,184,72,43)
    shape=shape.cut(aperture)
    ba=(base.RI+base.K*base.T)*pi/2
    flats['tray']=flats['tray'].cut(box(24,24,4,180+ba+55-13,72,-1))
    for y in(53,91):
        shape=shape.cut(cq.Solid.makeCylinder(1.7,8,cq.Vector(180,y,55),cq.Vector(1,0,0)))
        flats['tray']=flats['tray'].cut(cyl(1.7,4,180+ba+55-13,y,-1))
    result=[replace(p,shape=shape) if p is tray else p for p in result]
    probe=box(2,48,36,186,72,37)
    for y in(53,91):probe=probe.cut(cq.Solid.makeCylinder(1.7,6,cq.Vector(183,y,55),cq.Vector(1,0,0)))
    result.append(Part('probe_connector_REPLACEABLE_BLANK',probe,SILVER,'adapters','location retained; cut to actual connector later'))
    for y in(53,91):
        screw=cq.Solid.makeCylinder(1.45,8,cq.Vector(187,y,55),cq.Vector(-1,0,0)).fuse(cq.Solid.makeCylinder(2.8,1.8,cq.Vector(187,y,55),cq.Vector(1,0,0)))
        nut=hexnut(0,0,0).rotate((0,0,0),(0,1,0),-90).translate((183,y,55))
        result += [Part(f'probe_adapter_M3x8_{y}',screw,DARK,'hardware'),Part(f'probe_adapter_M3_nut_{y}',nut,DARK,'hardware')]
    for x in(106,164):
        screw=cq.Solid.makeCylinder(1.45,8,cq.Vector(x,442,34),cq.Vector(0,-1,0)).fuse(cq.Solid.makeCylinder(2.8,1.8,cq.Vector(x,442,34),cq.Vector(0,1,0)))
        nut=hexnut(0,0,0).rotate((0,0,0),(1,0,0),90).translate((x,438,34))
        result += [Part(f'mains_adapter_M3x8_{x}',screw,DARK,'hardware'),Part(f'mains_adapter_M3_nut_{x}',nut,DARK,'hardware')]
    # Flattening projection sets thickness to z=0..2.
    flats['probe-adapter-blank']=probe.rotate((0,0,0),(0,1,0),-90).translate((55,-72, -185))
    # Full fastener stacks: top countersunk M3x12 -> spacer/carrier -> washer/nut.
    for sign in(-1,1):
        for y in(140,380):
            x=sign*174
            screw=cyl(1.45,10.55,x,y,93).fuse(cq.Solid.makeCone(1.45,3.1,1.45,cq.Vector(x,y,103.55)))
            result += [Part(f'cover_M3x12_countersunk_{sign}_{y}',screw,DARK,'hardware','standard-size envelope'),
                       Part(f'carrier_M3_washer_{sign}_{y}',ring(3.5,1.6,96.5,.5,x,y),SILVER,'hardware'),
                       Part(f'carrier_M3_nut_{sign}_{y}',hexnut(x,y,94.1),DARK,'hardware','thread envelope')]
            side=cq.Solid.makeCylinder(1.45,8,cq.Vector(sign*185,y+7,93),cq.Vector(-sign,0,0)).fuse(cq.Solid.makeCylinder(2.8,1.8,cq.Vector(sign*185,y+7,93),cq.Vector(sign,0,0)))
            nut=hexnut(0,0,0).rotate((0,0,0),(0,1,0),-90*sign).translate((sign*181.4,y+7,93))
            result += [Part(f'side_M3x8_{sign}_{y}',side,DARK,'hardware','standard-size envelope'),Part(f'side_M3_nut_{sign}_{y}',nut,DARK,'hardware','thread envelope')]
    # Adhesive perimeter joint is explicitly a material allocation, not a validated bond.
    outer=base.rr(339.2,327.2,2,16.6,0,261,103)
    inner=base.rr(338,326,4,16,0,261,102)
    result.append(Part('glass_perimeter_joint_SEALANT_ALLOCATION',outer.cut(inner),(.16,.19,.17),'gasket','0.6mm edge joint; glass supplier approval required',True))
    # Hatch screws terminate in captive nut plates on the tray, accessible from below.
    for x in(-28,28):
        result.append(Part(f'hatch_M3_screw_{x}',cyl(1.45,7,x,261,6).fuse(cyl(2.8,1.5,x,261,4.5)),DARK,'hardware'))
        result.append(Part(f'hatch_M3_nut_{x}',hexnut(x,261,10),DARK,'hardware','nut retention method remains supplier-dependent'))
    # Dedicated PE stud candidate, independent of removable cover fasteners.
    result.append(Part('PE_bonding_stud_ALLOCATION',cyl(2,8,160,405,10),(.64,.62,.42),'hardware','bonded/welded stud process and PE system unqualified'))
    return result,flats,segments,bends,length


def collisions(parts: list[Part]) -> list[dict]:
    hits=[]
    for i,a in enumerate(parts):
        if a.envelope:continue
        for b in parts[i+1:]:
            if b.envelope:continue
            v=base.overlap(a.shape,b.shape)
            if v>1e-4:hits.append({'a':a.name,'b':b.name,'mm3':round(v,6)})
    return hits


def mesh(parts: list[Part],filename: str):
    data=[]
    for p in parts:
        vv,ff=p.shape.tessellate(.15,.15)
        data.append(dict(name=p.name,group=p.group,color=p.color,evidence=p.evidence,envelope=p.envelope,positions=[[v.x,v.y,v.z] for v in vv],indices=ff))
    (ROOT/filename).write_bytes(gzip.compress(json.dumps(data,separators=(',',':')).encode()))


def export(parts: list[Part],filename: str):
    assembly=cq.Assembly(name=filename.replace('.step','').replace('-','_'))
    for p in parts:
        if not p.shape.isValid() or p.shape.Volume()<=0: raise ValueError('Invalid '+p.name)
        assembly.add(p.shape,name=p.name,color=cq.Color(*p.color))
    assembly.export(str(ROOT/filename))
    check=cq.importers.importStep(str(ROOT/filename)).val()
    if not check.isValid():raise ValueError('Invalid reimport '+filename)
    return {'file':filename,'named_parts':len(parts),'solids':len(check.Solids()),'valid':True}


def context_parts():
    old=pack.main()
    excluded={'upper_body','glass_placeholder','rear_exhaust_grille','rear_grille_frame','base_with_rear_intake_and_sensor_hatch','sensor_service_hatch'}
    internals=[]
    for p in old:
        if p.name=='rear_power_inlet_envelope':continue
        if p.name in excluded or p.group in('shell','glass','base','keepout','rejected','alternate') or p.name.startswith(('foot','probe_port','power_inlet')):continue
        group='internals' if p.group in('pcb','coil','barrier','duct','cooling') else 'controls'
        shape=p.shape
        if p.group in('pcb','barrier'):shape=shape.translate((0,-4,0))
        if p.name=='coil_support_with_bolted_sensor_carrier':
            shape=ring(104,19,85,3,0,261).fuse(ring(20,12.1,86,5,0,261))
            for deg in(0,120,240):
                a=radians(deg);shape=shape.cut(cyl(1.25,7,15*cos(a),261+15*sin(a),85))
        internals.append(Part(p.name,shape,p.color,group,p.evidence,p.group in('coil','barrier','duct','cooling')))
    return internals


def main():
    print('Building revised mechanisms',flush=True)
    kp=knob();sp=sensor()
    checks={'status':'PROTOTYPE_GEOMETRY_NOT_QUALIFICATION','knob_rest_rigid_intersections':collisions(kp),'sensor_rest_rigid_intersections':collisions(sp)}
    print(json.dumps(checks),flush=True)
    enclosure,flats,segments,bends,length=enclosures()
    print('Loading documented PCB and packaging',flush=True)
    internals=context_parts()
    parts=enclosure+[replace(p,name='knob_'+p.name,shape=front(p.shape),group='controls') for p in kp]+[replace(p,name='sensor_'+p.name,shape=p.shape.translate((0,261,105)),group='sensor') for p in sp]+internals
    smooth=[p for p in kp if p.name not in('optional_bonded_round_antirotation_key','key_bondline_ENVELOPE')]
    checks['exports']=[export(parts,'temper-revised-integrated.step'),export(kp,'knob-revised.step'),export(smooth,'knob-smooth-face-option.step'),export(sp,'sensor-revised.step')]
    print('Exported STEP',flush=True)
    mesh(parts,'assembly.json.gz');mesh(kp,'knob.json.gz');mesh(sp,'sensor.json.gz')
    flatparts=[]
    for i,(name,shape) in enumerate(flats.items()):
        if not shape.isValid():raise ValueError('invalid flat '+name)
        b=shape.BoundingBox();shape=shape.translate((0,0,-b.zmin))
        cq.exporters.exportDXF(cq.Workplane('XY').add(shape).faces('>Z').wires(),str(ROOT/(name+'-PROVISIONAL.dxf')))
        cq.exporters.export(shape,str(ROOT/(name+'-flat.step')))
        flatparts.append(Part(name,shape.translate((i*650,0,0)),SILVER,'flat'))
    mesh(flatparts,'flats.json.gz')
    (ROOT/'bend-layout.json').write_text(json.dumps({'cover':{'width':370,'length':length,'bends':bends},'tray':{'bend_lines_x':[-180-(3+.42*2)*pi/4,180+(3+.42*2)*pi/4],'bend_angle_deg':90},'sheet_mm':2,'inside_radius_mm':3,'K_assumed':.42,'additional_parts':'Two connector blanks are flat; unchanged carrier and spacer geometry.'},indent=2))
    checks['enclosure_rigid_intersections']=collisions(enclosure)
    # Only actual rigid mechanism versus new sheets; flexible seals are separately intentional.
    shells=[p for p in enclosure if p.group in('cover','tray','carrier','glass')]
    integration=[]
    for mechanism in [p for p in parts if p.name.startswith(('knob_','sensor_')) and p.group in('controls','sensor') and not p.envelope]:
        for shell in shells:
            v=base.overlap(mechanism.shape,shell.shape)
            if v>1e-4:integration.append({'mechanism':mechanism.name,'sheet':shell.name,'mm3':v})
    checks['mechanism_to_enclosure']=integration
    checks['source_hashes']={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'model.py',ROOT/'enclosure.py',ROOT/'reference/packaging.py',OUT/'temper-inbox-cad/source/current-pcb.step')}
    checks['parts']=[{'name':p.name,'group':p.group,'envelope':p.envelope,'evidence':p.evidence,'valid':p.shape.isValid(),'bbox':base.bounds(p.shape)} for p in parts]
    (ROOT/'geometry-checks.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps({k:v for k,v in checks.items() if k!='parts'},indent=2),flush=True)

if __name__=='__main__':main()
