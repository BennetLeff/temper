"""R4: saved geometry, explicit envelopes, and falsifiable interface checks.

No thermal, leak, mechanical stress or electrical safety qualification.
Run after src/assembly.py with the pinned CadQuery environment.
"""
from pathlib import Path
import importlib.util
import json
import sys

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import baseline_engine as b

spec = importlib.util.spec_from_file_location('panel_source', ROOT / 'src/front_panel.py')
panel_source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel_source)


def main():
    catalog = json.loads((ROOT / 'catalog.json').read_text())
    records = []
    def check(name, passed, **details):
        records.append(dict(id=name, status='PASS_COMPUTED' if passed else 'FAIL', **details))
        print(name, records[-1]['status'], flush=True)
        (ROOT / 'evidence/front-panel-validation.json').write_text(json.dumps({
            'scope': 'Nominal saved geometry only; envelopes are included in interference checks. No leak, thermal, strength, button actuation or life proof.',
            'checks': records,
        }, indent=2))

    # Individual exports are positioned in the whole cooker; undo the front transform.
    world = {p['name']: cq.importers.importStep(str(ROOT / p['file'])).val()
             for p in catalog if p['group'] == 'front_panel'}
    local = {n: s.translate((0, 0, -b.base.FRONT_Z)).rotate((0, 0, 0), (1, 0, 0), -35)
             for n, s in world.items()}
    check('saved-panel-solids', all(s.isValid() and all(v.Volume() > 0 for v in s.Solids()) for s in local.values()), count=len(local))
    actual = panel_source.build()
    differences = {p.name: abs(p.shape.Volume() - local[p.name].Volume()) for p in actual}
    check('source-saved-volume', max(differences.values()) < 1e-4, max_delta_mm3=max(differences.values()))
    # No exception list for internal overlaps: even gaskets, PCB and cable allocations participate.
    physical = {n:s for n,s in local.items() if 'label_' not in n and 'readout_artwork' not in n}
    hits = []
    names = list(physical)
    for i, name in enumerate(names):
        for other in names[i+1:]:
            volume = b.base.overlap(physical[name], physical[other])
            if volume > 1e-4:
                hits.append(dict(a=name,b=other,mm3=volume))
    check('all-panel-parts-including-envelopes', not hits, hits=hits, threshold_mm3=1e-4)
    obstacles = {p['name']:cq.importers.importStep(str(ROOT / p['file'])).val()
                 for p in catalog if p['group'] != 'front_panel' and not p['name'].startswith('pcb_export_')}
    pcb = cq.importers.importStep(str(ROOT / 'inputs/current-pcb.step')).val()
    obstacles['historical_PCB_export'] = b.historical_pcb_world(pcb)
    # The old package first places at y=154 then baseline_engine shifts every
    # PCB/barrier part -4 mm. Compare every source solid to the saved assembly
    # catalog so a future placement edit cannot make this check quietly wrong.
    placed = [b.historical_pcb_world(s).BoundingBox() for s in pcb.Solids()]
    catalog_pcb = [p for p in catalog if p['name'].startswith('pcb_export_')]
    bbox_deltas = [max(abs(a-c) for a,c in zip(
        (bb.xmin,bb.ymin,bb.zmin,bb.xmax,bb.ymax,bb.zmax),p['bbox']))
        for bb,p in zip(placed,catalog_pcb)]
    # STEP import bounds differ by up to ~0.05 mm when OCC transforms the
    # compound versus its individual solids. The incorrect 154 placement is
    # 4 mm away, well beyond this explicit 0.1 mm correspondence tolerance.
    catalog_aligned = len(placed) == len(catalog_pcb) and max(bbox_deltas) < .1
    check('historical-PCB-placement-correspondence',catalog_aligned,
          source_solids=len(placed),catalog_solids=len(catalog_pcb),
          max_bbox_delta_mm=max(bbox_deltas),tolerance_mm=.1,
          scope='R4 inherited PCB only; current native full-bridge outline is separate.')
    hits = []
    for name in physical:
        for other, shape in obstacles.items():
            volume = b.base.overlap(world[name],shape)
            if volume > 1e-4: hits.append(dict(a=name,b=other,mm3=volume))
    check('panel-vs-complete-cooker', not hits, hits=hits, obstacles=len(obstacles), includes='Packaging allocations, actual PCB export, formed shell, knob, glass, supports')
    actual_hits=[hit for hit in hits if hit['b']=='historical_PCB_export']
    check('panel-vs-historical-PCB',not actual_hits and catalog_aligned,hits=actual_hits,
          minimum_nominal_distance_mm=min(world[name].distance(obstacles['historical_PCB_export']) for name in physical),
          limit='Mechanical distance to historical imported geometry only; current full-bridge PCB and electrical insulation unverified.')
    def part(suffix): return local['front_'+suffix]
    lens = part('flush_lens_108x38x2')
    carrier = part('carrier_and_closed_sidewalls')
    membrane=part('three_button_continuous_membrane_INSTALLED')
    check('flush-exterior-datum',abs(lens.BoundingBox().zmax)<1e-5 and abs(membrane.BoundingBox().zmax)<1e-5,
          lens_front_z_mm=lens.BoundingBox().zmax,button_tops_z_mm=membrane.BoundingBox().zmax,
          aluminum_front_z_mm=0,limit='Nominal CAD only; glass/sheet/bond tolerances and assembly jig must establish real flushness.')
    shell=obstacles['three_bend_front_top_rear_cover'].translate((0,0,-b.base.FRONT_Z)).rotate((0,0,0),(1,0,0),-35)
    gap=lens.distance(shell)
    check('lens-perimeter-gap',abs(gap-.4)<1e-5,minimum_nominal_mm=gap,
          limit='Gap for a flush-filled flexible joint; material and thermal expansion unqualified.')
    # Retaining full sheet between window and buttons distinguishes R4 from the cassette aperture.
    bridge=b.box(100,4,1,-35,40,-1.5)
    volume=b.base.overlap(bridge,shell)
    check('continuous-sheet-bridge',abs(volume-400)<1e-4,measured_mm3=volume,expected_mm3=400)
    check('no-visible-cassette-bezel',not any('bezel_with_blind' in p['name'] for p in catalog))
    support=part('lens_rear_support_ring');bond=part('lens_rear_bondline_ALLOCATION')
    check('rear-support-bond-stack',abs(bond.BoundingBox().zlen-.3)<1e-5 and support.distance(bond)<1e-6 and bond.distance(lens)<1e-6,
          support_thickness_mm=support.BoundingBox().zlen,bond_mm=bond.BoundingBox().zlen,
          limit='Contact path only. Outward lens retention and carrier-pad attachment require qualified adhesion.')
    check('carrier-clears-fixed-lens-ring',carrier.distance(support)>.99,
          nominal_clearance_mm=carrier.distance(support))
    raised=lens.translate((0,0,.1))
    check('negative-control-raised-lens',abs(raised.BoundingBox().zmax)>.09,detected_projection_mm=raised.BoundingBox().zmax)
    oversized=lens.translate((.6,0,0))
    penetration=b.base.overlap(oversized,shell)
    check('negative-control-too-small-window',penetration>1,penetration_mm3=penetration,deliberate_shift_mm=.6)
    module=part('NHD_3p12_25664UCW2_PCB_ENVELOPE')
    holes={(round(e.Center().x,3),round(e.Center().y,3)) for e in module.Edges() if e.geomType()=='CIRCLE' and abs(e.radius()-1.25)<1e-5}
    expected={(round(-35+dx,3),round(64+dy,3)) for dx in(-41.6,41.6) for dy in(-19.,19.)}
    check('OLED-drawing-hole-pattern',holes==expected,holes_xy_mm=sorted(holes),pitch_mm=[83.2,38],source='Newhaven rev7 dimension drawing; envelope thickness subdivisions remain assumptions.')
    module_front=part('NHD_display_bezel_ENVELOPE')
    gap=lens.distance(module_front)
    check('OLED-glass-airgap',abs(gap-4)<1e-5, nominal_mm=gap, limit='Air gap is a clearance, not a thermal guarantee.')
    membrane=part('three_button_continuous_membrane_INSTALLED')
    switches={n:s for n,s in local.items() if n.startswith('front_switch_')}
    rest={n:membrane.distance(s) for n,s in switches.items()}
    check('button-rest-allocation',all(abs(v-.2)<1e-5 for v in rest.values()),gaps_mm=rest, limit='No chosen switch, compliant stroke or overtravel validation. This does not establish working buttons.')
    forbidden={'display_window','button_1','button_2','button_3','button_4','minus_label','plus_label','back_label','stop_label','target','actual'}
    check('old-controls-removed',not forbidden.intersection(p['name'] for p in catalog))
    # Nominal disassembly: lid pulled straight rearward 1, 5 and 26mm; hardware removed first.
    lid=part('rear_lid')
    service_hits=[]
    for travel in(1,5,26):
        for name,shape in physical.items():
            if any(token in name for token in ('rear_lid','lid_M3','lid_sealing','lid_compression')):continue
            v=b.base.overlap(lid.translate((0,0,-travel)),shape)
            if v>1e-4:service_hits.append(dict(travel=travel,part=name,mm3=v))
    check('lid-removal-in-isolated-cassette',not service_hits,hits=service_hits,limit='Cassette removed from cooker; screwdriver access and complete cooker service procedure not validated.')
    assert all(r['status']=='PASS_COMPUTED' for r in records), 'R4 panel geometry has failures; read evidence.'


if __name__=='__main__': main()
