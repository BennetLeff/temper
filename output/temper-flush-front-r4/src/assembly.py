"""Build R4 from the contained source/input tree. Run with CadQuery 2.6.1."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import csv
import gzip
import hashlib
import json
import platform
import cadquery as cq
import baseline_engine as b
import mechanisms
import support
import front_panel

ROOT=Path(__file__).resolve().parents[1]


def enclosure():
    parts, flats, segments, bends, length = b.enclosures()
    result=[]
    for p in parts:
        if p.name.startswith('hatch_M3_nut_'):
            continue
        shape=p.shape
        if p.name=='two_bend_bottom_and_sides':
            for x,y in support.LEGS:
                shape=shape.cut(b.cyl(2.2,4,x,y,7))
                flats['tray']=flats['tray'].cut(b.cyl(2.2,4,x,y,-1))
            for x in (-28,28):
                for y in (253,269):
                    shape=shape.cut(b.cyl(1.6,4,x,y,7))
                    flats['tray']=flats['tray'].cut(b.cyl(1.6,4,x,y,-1))
        if p.name.startswith('foot_'):
            # Replace plain discs with replaceable screw-through foot candidates.
            x,y=map(float,p.name.split('_')[1:])
            shape=shape.cut(b.cyl(2.2,10,x,y,-1)).cut(b.cyl(4.2,6,x,y,-1))
            result += [b.Part(f'foot_M4x12_{x}_{y}',b.cyl(1.95,12,x,y,5).fuse(b.cyl(3.5,4,x,y,1)),b.DARK,'hardware','Nominal M4x12 socket head envelope'),
                       b.Part(f'foot_M4_washer_{x}_{y}',b.ring(4.5,2.15,10,.8,x,y),b.SILVER,'hardware','Nominal M4 washer'),
                       b.Part(f'foot_M4_nut_{x}_{y}',b.hexnut(x,y,10.8,7,3.2,2),b.DARK,'hardware','Nominal M4 nut')]
            p=replace(p,evidence='Screw-through rubber foot candidate: Ø22x8, Ø4.4 bore, Ø8.4x5 recess; exact purchased foot/compound pending.')
        result.append(replace(p,shape=shape))
    for x in (-28,28):
        strip=b.box(10,24,3,x,261,10).cut(b.cyl(1.5,5,x,261,9))
        for y in (253,269):
            strip=strip.cut(b.cyl(1.6,5,x,y,9))
            rivet=b.cyl(1.55,5,x,y,8).fuse(b.cyl(3,1,x,y,7)).fuse(b.cyl(2.0,1,x,y,13))
            result.append(b.Part(f'hatch_strip_rivet_{x}_{y}',rivet,b.DARK,'hardware','Installed Ø3.2 blind-rivet allocation, grip5; actual rivet selection/head/grip to be confirmed.',True))
        result.append(b.Part(f'hatch_tapped_strip_{x}',strip,b.SILVER,'mounts','10x24x3 flat stock; center M3x0.5 through tap, two Ø3.2 rivet holes. Captive service thread, not loose nut.'))
    flats['hatch-cover']=next(p.shape for p in result if p.name=='sensor_service_cover').translate((0,-261,-6))
    strip=next(p.shape for p in result if p.name=='hatch_tapped_strip_28').translate((-28,-261,-10))
    # Cutting file is the PRE-TAP blank, not the finished major-diameter thread envelope.
    strip=strip.fuse(b.cyl(1.5,3,0,0,0)).cut(b.cyl(1.25,5,0,0,-1)).clean()
    flats['hatch-tapped-strip-pre-tap']=strip
    return result, flats, segments, bends, length


def build():
    enc, flats, segments, bends, length=enclosure()
    knob=mechanisms.knob()
    sensor=mechanisms.sensor()
    support_parts=support.build()
    superseded={'coil_support_with_bolted_sensor_carrier','display_window','target','actual','back_label','minus_label','plus_label','stop_label',*[f'button_{i}' for i in range(1,5)]}
    context=[p for p in b.context_parts() if p.name not in superseded]
    # M2.5x12 support fasteners supersede three old M2.5x8 mounting screws.
    sensor=[p for p in sensor if not p.name.startswith('mount_M2p5x8_screw_')]
    parts=enc+[replace(p,name='knob_'+p.name,shape=b.front(p.shape),group='controls') for p in knob]
    parts += [replace(p,name='sensor_'+p.name,shape=p.shape.translate((0,261,105)),group='sensor') for p in sensor]
    parts += support_parts+context
    parts += [replace(p,shape=front_panel.world(p.shape)) for p in front_panel.build()]
    for name in ('coil_support_flat_routed_plate','sensor_support_flat_spacer_2mm','sensor_support_flat_adapter_3mm'):
        p=next(p for p in support_parts if p.name==name)
        flats[name]=p.shape.translate((0,-261,-p.shape.BoundingBox().zmin))
    return parts,knob,sensor,enc,support_parts,flats,segments,bends,length


def write_mesh(parts, path):
    data=[]
    for p in parts:
        vv, ff=p.shape.tessellate(.12,.12)
        data.append(dict(name=p.name,group=p.group,color=p.color,evidence=p.evidence,envelope=p.envelope,
                         positions=[[v.x,v.y,v.z] for v in vv],indices=ff))
    path.write_bytes(gzip.compress(json.dumps(data,separators=(',',':')).encode(),mtime=0))


def export(parts,path):
    a=cq.Assembly(name=path.stem.replace('-','_'))
    for p in parts:
        if not p.shape.isValid() or p.shape.Volume()<=0:
            raise ValueError(f'Invalid {p.name}')
        a.add(p.shape,name=p.name,color=cq.Color(*p.color))
    a.export(str(path))
    check=cq.importers.importStep(str(path)).val()
    if not check.isValid() or any(s.Volume()<=0 for s in check.Solids()):
        raise ValueError(f'Invalid saved STEP {path}')
    return {'file':str(path.relative_to(ROOT)),'named_parts':len(parts),'solids':len(check.Solids()),'valid':True,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    print('Building R4',flush=True)
    parts,knob,sensor,enc,sp,flats,segments,bends,length=build()
    exports=[]
    assemblies={'assembly':parts,'knob':knob,'sensor':sensor,'enclosure':enc,'support':sp}
    panel=front_panel.build()
    skin=next(p.shape for p in enc if p.name=='three_bend_front_top_rear_cover')
    skin=skin.translate((0,0,-b.base.FRONT_Z)).rotate((0,0,0),(1,0,0),-35)
    skin=skin.intersect(front_panel.rr(176,94,2,0,-35,50,-2))
    panel.append(b.Part('front_face_excerpt',skin,b.SILVER,'front_panel','Cropped context from actual formed enclosure, not a separate panel or fabrication part.',True))
    assemblies.update(front_panel=panel,front_panel_exploded=front_panel.exploded(panel))
    flats['front-panel-rear-lid']=next(p.shape for p in panel if p.name=='front_rear_lid').translate((35,-50,29))
    flats['flush-lens-support-ring']=next(p.shape for p in panel if p.name=='front_lens_rear_support_ring').translate((35,-64,3.5))
    for name, group in assemblies.items():
        print('Exporting '+name,flush=True)
        exports.append(export(group,ROOT/'STEP'/f'{name}.step'))
        write_mesh(group,ROOT/f'{name}.json.gz')
    # Service view is a presentation assembly, not a new physical configuration.
    exploded=[]
    for p in knob:
        offset=0
        if p.name=='turned_aluminum_grip_56mm':offset=42
        elif p.name=='replaceable_profile_cam_8mm' or p.name.startswith('cam_M2x12_'):offset=28
        elif p.name in ('keyed_thrust_washer','flanged_hub_guide_bushing'):offset=16
        exploded.append(replace(p,shape=p.shape.translate((0,0,offset))))
    exports.append(export(exploded,ROOT/'STEP/knob_exploded.step'))
    write_mesh(exploded,ROOT/'knob_exploded.json.gz')
    export([next(p for p in sensor if p.name=='contact_cap_thick_skirt_formed_lip')],ROOT/'STEP/sensor_cap.step')
    flatparts=[]
    for i,(name,shape) in enumerate(flats.items()):
        path=ROOT/'DXF'/f'{name}-PROVISIONAL.dxf'
        cq.exporters.exportDXF(cq.Workplane('XY').add(shape).faces('>Z').wires(),str(path))
        cq.exporters.export(shape,str(ROOT/'STEP'/f'{name}-flat.step'))
        flatparts.append(b.Part(name,shape.translate((650*i,0,0)),b.SILVER,'flat','Flat profile; bend compensation/process not released.'))
    write_mesh(flatparts,ROOT/'flats.json.gz')
    export(flatparts,ROOT/'STEP/flat_layout.step')
    catalog=[]
    for p in parts:
        item={'name':p.name,'group':p.group,'envelope':p.envelope,'evidence':p.evidence,
              'bbox':b.base.bounds(p.shape),'volume_mm3':p.shape.Volume()}
        if not p.name.startswith('pcb_export_'):
            filename=f'STEP/parts/{p.name}.step'
            cq.exporters.export(p.shape,str(ROOT/filename))
            item['file']=filename
        else:
            item['file']='inputs/current-pcb.step'
        catalog.append(item)
    (ROOT/'catalog.json').write_text(json.dumps(catalog,indent=2))
    (ROOT/'bend-layout.json').write_text(json.dumps({'cover':{'width':370,'length':length,'bends':bends},'sheet_mm':2,'inside_radius_mm':3,'K_assumed':.42,'status':'PROVISIONAL; actual shop bend coupon/sequence not verified'},indent=2))
    (ROOT/'evidence/build.json').write_text(json.dumps({'exports':exports,'python':platform.python_version(),'cadquery':cq.__version__,'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('src','inputs') for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}},indent=2))
    print(json.dumps(exports),flush=True)


if __name__=='__main__':
    main()
