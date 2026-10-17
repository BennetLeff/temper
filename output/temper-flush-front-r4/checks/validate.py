"""Reimport saved parts; check affected interfaces and sampled nominal motion."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import sys
from math import pi
import cadquery as cq

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import baseline_engine as b
import mechanisms as m


def main():
    catalog=json.loads((ROOT/'catalog.json').read_text())
    saved={p['name']:cq.importers.importStep(str(ROOT/p['file'])).val() for p in catalog if not p['name'].startswith('pcb_export_')}
    parts={p['name']:b.Part(p['name'],saved[p['name']],(.5,.5,.5),p['group'],p['evidence'],p['envelope']) for p in catalog if p['name'] in saved}
    checks=[]
    result={'scope':'Saved STEP geometry; dimensional and sampled rigid tests only. No force, stiffness, thermal, seal, EMI, life or supplier acceptance claim.', 'checks':checks}
    def record(name,status,**data):
        checks.append(dict(id=name,status=status,**data))
        (ROOT/'evidence/validation.json').write_text(json.dumps(result,indent=2))
        print(name,status,flush=True)
    record('saved-individual-solids','PASS_COMPUTED' if all(s.isValid() and all(x.Volume()>0 for x in s.Solids()) for s in saved.values()) else 'FAIL',parts=len(saved))
    # Saved circular edges directly determine the cut distances; no bounding-box tolerance inference.
    def circles(name):
        return [(e.radius(),e.Center().toTuple()) for e in saved[name].Edges() if e.geomType()=='CIRCLE']
    hatch=circles('sensor_service_cover')
    outer=max(r for r,c in hatch)
    holes=sorted({round(c[0],6) for r,c in hatch if abs(r-1.7)<1e-5})
    web=min(outer-abs(x)-1.7 for x in holes)
    record('hatch-edge-geometry','PASS_COMPUTED' if web>2 and len(holes)==2 else 'FAIL',OD_mm=2*outer,hole_x_mm=holes,cover_web_mm=web,tray_opening_web_mm=min(abs(x)-1.7-22 for x in holes),head_edge_margin_mm=outer-max(abs(x) for x in holes)-2.8,criterion='Internal revision target cover web >=2mm; not supplier acceptance.')
    carrier=circles('flat_glass_carrier_ring')
    xs=sorted({round(c[0],6) for r,c in carrier if abs(r-1.7)<1e-5})
    web=min(179-abs(x)-1.7 for x in xs)
    record('carrier-edge-geometry','PASS_COMPUTED' if web>3 else 'FAIL',hole_x_mm=xs,edge_web_mm=web,criterion='Internal revision target outer web >=3mm.')
    cap=saved['sensor_contact_cap_thick_skirt_formed_lip']
    slice_=cap.intersect(b.box(30,30,.01,0,261,105-1.8))
    expected=pi*(6**2-5.2**2)*.01
    record('cap-skirt-section','PASS_COMPUTED' if abs(slice_.Volume()-expected)<1e-6 else 'FAIL',z_mm=103.2,thickness_mm=.8,slice_volume_mm3=slice_.Volume(),expected_annulus_volume_mm3=expected)
    groove=cap.intersect(b.box(30,30,.01,0,261,105-.65))
    expected=pi*(5.8**2-4.8**2)*.01
    record('cap-groove-root-section','PASS_COMPUTED' if abs(groove.Volume()-expected)<1e-6 else 'FAIL',wall_mm=1.0,slice_volume_mm3=groove.Volume(),expected_annulus_volume_mm3=expected)
    spread=saved['sensor_glass_load_spreader_flat_annulus']
    area=spread.Volume()/.15
    record('glass-spreader-area','PASS_COMPUTED' if area>100 else 'FAIL',area_mm2=area,ratio_to_R1=area/(3*pi*.3**2),criterion='Nominal area comparison only; NOT a stress/strength result.')
    names=[n for n in parts if n.startswith(('leg_','foot_','hatch_','sensor_mount_','sensor_adapter_','sensor_support_')) or n=='coil_support_flat_routed_plate']
    hits=[]
    for name in names:
        a=parts[name]
        if a.envelope:continue
        for other,c in parts.items():
            if other==name or (other in names and other<name):continue
            # Include packaging envelopes as obstacles: do not silently hide new interference.
            if other.startswith(('knob_','pcb_export_')):continue
            vol=b.base.overlap(a.shape,c.shape)
            if vol>1e-4:hits.append(dict(a=name,b=other,mm3=vol))
    # Check actual PCB assembly explicitly against new support, where broad bounds overlap.
    pcb=cq.importers.importStep(str(ROOT/'inputs/current-pcb.step')).val()
    pcb=b.historical_pcb_world(pcb)
    for name in names:
        if parts[name].envelope:continue
        vol=b.base.overlap(parts[name].shape,pcb)
        if vol>1e-4:hits.append(dict(a=name,b='historical_PCB_export',mm3=vol))
    record('changed-support-hardware-vs-context','PASS_COMPUTED' if not hits else 'FAIL',hits=hits,threshold_mm3=.0001)
    enc=[p for p in parts.values() if p.group in ('cover','tray','carrier','glass','mounts','feet','adapters','hardware')]
    record('enclosure-hardware-intersections','PASS_COMPUTED' if not (hits:=b.collisions(enc)) else 'FAIL',hits=hits)
    # Ensure there is now a nominal contact path between tray, each leg, and plate.
    tray=saved['two_bend_bottom_and_sides'];plate=saved['coil_support_flat_routed_plate']
    contacts=[]
    for n,s in saved.items():
        if n.startswith('leg_tube_'):
            contacts.append(dict(part=n,to_tray_mm=s.distance(tray),to_plate_mm=s.distance(plate)))
    record('support-contact-path','PASS_COMPUTED' if len(contacts)==4 and all(c['to_tray_mm']<1e-6 and c['to_plate_mm']<1e-6 for c in contacts) else 'FAIL',legs=contacts,limit='Contact and fastener geometry only; no stiffness or strength.')
    hits=[]
    for p in parts.values():
        if p.group not in ('controls','sensor') or not p.name.startswith(('knob_','sensor_')) or p.envelope:continue
        for shell in parts.values():
            if shell.group not in ('cover','tray','carrier','glass'):continue
            vol=b.base.overlap(p.shape,shell.shape)
            if vol>1e-4:hits.append(dict(a=p.name,b=shell.name,mm3=vol))
    record('mechanisms-to-enclosure','PASS_COMPUTED' if not hits else 'FAIL',hits=hits)
    print('Building local mechanisms for correspondence and motion',flush=True)
    kp=m.knob();sp=m.sensor()
    correspondence=[]
    for p in kp:
        world=b.front(p.shape);s=saved['knob_'+p.name]
        correspondence.append(abs(world.Volume()-s.Volume())<1e-4)
    for p in sp:
        if p.name.startswith('mount_M2p5x8_screw_'):continue
        s=saved['sensor_'+p.name]
        correspondence.append(abs(p.shape.Volume()-s.Volume())<1e-4)
    record('source-saved-volume-correspondence','PASS_COMPUTED' if all(correspondence) else 'FAIL',parts=len(correspondence),tolerance_mm3=.0001)
    rest_hits=b.collisions(kp)
    record('knob-rest','PASS_COMPUTED' if not rest_hits else 'FAIL',hits=rest_hits,solids=sum(len(p.shape.Solids()) for p in kp),named_entries=len(kp))
    poses=[]
    for angle in (0,1.25,2.5,3.75,5,6.25,7.5,8.75,10,11.25,12.5,13.75,15):
        center=m.ball_center(angle)
        compression=m.PLUNGER_FACE+.3-(center+.5)
        for press in (0,.275,.55):
            moved=[]
            for p in kp:
                shape=p.shape
                if p.name in ('turned_aluminum_grip_56mm','replaceable_profile_cam_8mm','diametric_sensing_magnet','flexible_retaining_clip_candidate') or p.name.startswith('cam_M2x12_'):
                    shape=shape.rotate((0,0,0),(0,0,1),angle).translate((0,0,-press))
                elif p.name=='keyed_thrust_washer':shape=shape.translate((0,0,-press))
                elif p.name.startswith('GN615_M2_KN_') and p.name.endswith('_ball'):
                    sign=-1 if '_180_' in p.name else 1
                    shape=shape.translate((sign*(center-m.ball_center(0)),0,0))
                moved.append(replace(p,shape=shape))
            hits=b.collisions(moved)
            poses.append(dict(angle_deg=angle,press_mm=press,compression_mm=compression,hits=hits))
    record('knob-sampled-motion','PASS_COMPUTED' if all(not p['hits'] and 0<p['compression_mm']<.3 for p in poses) else 'FAIL',poses=poses,scope='One 15-degree period, 13 angle samples and 3 axial positions. Prescribed motion; not force or continuous swept-volume proof.')
    # Tolerance envelope on COMPRESSION only. This is not a multi-axis tolerance sweep.
    low=min(p['compression_mm'] for p in poses)
    high=max(p['compression_mm'] for p in poses)
    minimum=low-m.PLUNGER_OFFSET_BUDGET
    maximum=high+m.PLUNGER_OFFSET_BUDGET
    record('detent-compression-offset-budget',
           'PASS_COMPUTED' if minimum>=m.PLUNGER_END_MARGIN and maximum<=m.PLUNGER_STROKE-m.PLUNGER_END_MARGIN else 'FAIL',
           nominal_compression_mm=[low,high],assumed_combined_offset_mm=m.PLUNGER_OFFSET_BUDGET,
           compression_bounds_mm=[minimum,maximum],catalog_stroke_mm=m.PLUNGER_STROKE,
           required_end_margin_mm=m.PLUNGER_END_MARGIN,
           scope='Arithmetic radial-offset envelope on sampled nominal contact. No temperature/creep, stiffness or friction qualification; no assigned supplier tolerance.')
    # A deliberately excessive offset must fail, preventing an always-green check.
    record('detent-offset-negative-control','PASS_COMPUTED' if low-.1<0 and high+.1>m.PLUNGER_STROKE else 'FAIL',
           excessive_offset_mm=.1,criterion='Both ends violate the nominal0..0.3mm stroke with ±0.1mm combined offset.')
    # Verify that the saved world-coordinate bodies really moved with the source.
    # Volume equality alone cannot detect a wrong placement.
    differences=[]
    for p in kp:
        if p.name.startswith('GN615_M2_KN_') and p.name.endswith('_body'):
            world=b.front(p.shape); saved_body=saved['knob_'+p.name]
            diff=world.cut(saved_body).Volume()+saved_body.cut(world).Volume()
            differences.append(dict(part=p.name,symmetric_difference_mm3=diff))
    record('saved-plunger-placement','PASS_COMPUTED' if len(differences)==2 and all(x['symmetric_difference_mm3']<1e-5 for x in differences) else 'FAIL',parts=differences)
    sensor_poses=[]
    for travel in (0,.3,.6,.9,1.2):
        ps=m.sensor(travel);hits=b.collisions(ps)
        sensor_poses.append(dict(travel_mm=travel,hits=hits))
    record('sensor-sampled-motion','PASS_COMPUTED' if all(not p['hits'] for p in sensor_poses) else 'FAIL',poses=sensor_poses)
    cap=next(p.shape for p in sp if p.name=='contact_cap_thick_skirt_formed_lip')
    stem=next(p.shape for p in sp if p.name=='hollow_insulating_plunger_with_capture_groove')
    volume=b.base.overlap(cap.translate((0,0,.075)),stem)
    record('cap-capture-negative-control','PASS_COMPUTED' if volume>1e-4 else 'FAIL',upward_overtravel_mm=.075,overlap_mm3=volume)
    record('click-tolerance-window','OPEN_INHERITED_FAIL',reason='R1 tactile trip/overtravel conflict unchanged; supplier safe mechanical stroke absent. Detent redesign does not resolve click sensing.')
    record('physical-manufacturing-qualification','UNVERIFIED',items=['thermal transfer and EM interaction','spring force/feel/wear','press and magnetic signal/retention','sheet bend coupon and fit','cap forming and diaphragm bonding','glass preload and support deflection','selected material grades and hardware','control sealing/retention and cooling interfaces'])
    result['artifact_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'STEP').rglob('*.step'))}
    (ROOT/'evidence/validation.json').write_text(json.dumps(result,indent=2))
    if any(check['status']=='FAIL' for check in checks):
        raise SystemExit('R2.1 geometry validation failed; inspect evidence/validation.json')


if __name__=='__main__':main()
