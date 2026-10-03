#!/usr/bin/env python3
"""One-off native-15 DC sheet experiment; no board acceptance rule.

Uses the committed kit unchanged. Keeps each physical pad centre, including
four same-number terminal leads. Verifies barrel contacts before any solve.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
KIT = UNIT / 'validation-plan/sim-kit/04-current/sheet_solver.py'
spec = importlib.util.spec_from_file_location('kit_solver', KIT)
solver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solver)


def load_net(data: dict, name: str, pitch: float, plating: float):
    net = solver.Net(pitch_mm=pitch)
    shapes, barrels, pads = defaultdict(list), {}, defaultdict(list)
    for item in data['primitives']:
        if item['net'] != name:
            continue
        layer, kind = item['layer'], item['kind']
        if kind in ('zone', 'pad'):
            shapes[layer].append(Polygon(item['shell'], item['holes']))
        elif kind == 'track':
            shapes[layer].append(LineString([item['start'], item['end']]).buffer(item['width_mm']/2, 16))
        elif kind == 'via':
            shapes[layer].append(Point(item['centre']).buffer(item['diameter_mm']/2, 32))
        if kind == 'pad' and layer == 'F.Cu':
            pads[item['ref']].append(item)
        drill = item.get('drill_mm', 0)
        if kind == 'pad':
            if drill[0] != drill[1]:
                raise ValueError('slotted drill unsupported')
            drill = drill[0]
        if kind in ('pad', 'via') and drill > 0:
            key = (kind, *item['centre'])
            b = barrels.setdefault(key, {'centre':item['centre'], 'drill':drill, 'layers':[],
                                        'kind':kind, 'ref':item.get('ref')})
            if layer not in b['layers']:
                b['layers'].append(layer)
    for layer, parts in shapes.items():
        geom = unary_union(parts)
        polys = list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom]
        net.add_layer(layer, [list(p.exterior.coords) for p in polys],
                      70 if layer in ('F.Cu','B.Cu') else 61,
                      [list(r.coords) for p in polys for r in p.interiors])
    for b in barrels.values():
        net.add_via(b['centre'], b['drill'], plating, b['layers'], filled=b['kind']=='pad')
    return net, list(barrels.values()), pads


def audit_contacts(net, barrels) -> dict:
    """Check actual kit radial edges against drilled physical copper."""
    grids, nodes, matrix, _ = net._build()
    bad = []
    count = 0
    coordinates = {}
    for layer, grid in grids.items():
        ii, jj = np.nonzero(grid['ids'] >= 0)
        coordinates[layer] = {int(grid['ids'][i,j]):(float(grid['xs'][i]),float(grid['ys'][j])) for i,j in zip(ii,jj)}
    for via, by_layer, barrel in zip(net.vias, nodes, barrels):
        cx, cy = via['xy']
        radius = via['drill_mm']/2
        for layer, bn in by_layer.items():
            grid = grids[layer]
            coords = coordinates[layer]
            for node in bn:
                for dest in matrix.getrow(node).indices:
                    if int(dest) not in coords:
                        continue
                    count += 1
                    x,y = coords[int(dest)]
                    dist = math.hypot(x-cx,y-cy)
                    start=(cx+(x-cx)*(radius+1e-6)/dist,cy+(y-cy)*(radius+1e-6)/dist)
                    edge=LineString([start,(x,y)])
                    missing=edge.difference(grid['geom'].buffer(1e-7)).length
                    if missing > 1e-6:
                        bad.append({'layer':layer,'barrel':barrel,'cell_mm':[x,y],
                                    'uncovered_length_mm':missing})
    return {'radial_contacts_checked':count,'uncovered_contacts':bad}


def sheet_and_heat(net, solved, output: Path) -> dict:
    """Report peak edge current per mm and preserve nodal Joule heat for B3."""
    grids, via_nodes, matrix, _ = net._build()
    volts = solved['v']
    arrays = {}
    node_cells = {}
    peaks = {}
    sheet_w = 0.0
    for layer, grid in grids.items():
        ids = grid['ids']
        heat = np.zeros(ids.shape, dtype=np.float64)
        best = None
        for di, dj, orientation in ((1, 0, 'x'), (0, 1, 'y')):
            a = ids[:ids.shape[0]-di, :ids.shape[1]-dj]
            b = ids[di:, dj:]
            valid = (a >= 0) & (b >= 0)
            ii, jj = np.nonzero(valid)
            if len(ii) == 0:
                continue
            aa, bb = a[valid], b[valid]
            conductance = -np.asarray(matrix[aa, bb]).ravel()
            good = (conductance > 0) & np.isfinite(volts[aa]) & np.isfinite(volts[bb])
            if not good.any():
                continue
            aa, bb = aa[good], bb[good]
            ii, jj = ii[good], jj[good]
            g = conductance[good]
            current = g * (volts[aa] - volts[bb])
            edge_heat = current * current / g
            sheet_w += float(edge_heat.sum())
            np.add.at(heat, (ii, jj), edge_heat/2)
            np.add.at(heat, (ii+di, jj+dj), edge_heat/2)
            ix = int(np.argmax(abs(current)))
            candidate = {'amps_per_mm':float(abs(current[ix])/net.h),
                         'edge_amps':float(current[ix]),
                         'location_mm':[float((grid['xs'][ii[ix]]+grid['xs'][ii[ix]+di])/2),
                                        float((grid['ys'][jj[ix]]+grid['ys'][jj[ix]+dj])/2)],
                         'orientation':orientation}
            if best is None or candidate['amps_per_mm'] > best['amps_per_mm']:
                best = candidate
        key = layer.replace('.', '_')
        arrays[f'{key}_x_mm'] = grid['xs']
        arrays[f'{key}_y_mm'] = grid['ys']
        arrays[f'{key}_copper'] = ids >= 0
        arrays[f'{key}_joule_w'] = heat
        arrays[f'{key}_thickness_um'] = np.array([net.layers[layer]['t']*1e6])
        ii, jj = np.nonzero(ids >= 0)
        node_cells.update((int(ids[i,j]), (key, int(i), int(j))) for i,j in zip(ii,jj))
        peaks[layer] = best
    barrel_hops = []
    barrel_w = 0.0
    for via, currents in zip(net.vias, solved['via_currents']):
        for i, amps in enumerate(currents['hop_amps']):
            if amps is None or not math.isfinite(amps):
                continue
            watts = amps*amps*via['hop_ohm'][i]
            barrel_w += watts
            barrel_hops.append({'xy_mm':list(via['xy']), 'filled_lead':via['filled'],
                                'from_layer':via['layers'][i], 'to_layer':via['layers'][i+1],
                                'amps':float(amps),'joule_w':float(watts),
                                'drill_mm':via['drill_mm'], 'plating_um':via['plating_m']*1e6})
    # The sheet edge tally omits radial annulus contacts and circumferential
    # barrel edges. Attribute their dissipation at the actual drill location;
    # assign half of a layer-spanning edge to each adjacent layer.
    barrel_nodes = {}
    for via_index, by_layer in enumerate(via_nodes):
        for layer, nodes in by_layer.items():
            barrel_nodes.update((node,(via_index,layer)) for node in nodes)
    seen = set()
    barrel_network_w = 0.0
    barrel_heat = defaultdict(lambda: defaultdict(float))
    for node,(via_index,layer) in barrel_nodes.items():
        for pos in range(matrix.indptr[node],matrix.indptr[node+1]):
            dest=int(matrix.indices[pos])
            if dest == node:
                continue
            edge=(min(node,dest),max(node,dest))
            if edge in seen:
                continue
            seen.add(edge)
            if not (math.isfinite(volts[node]) and math.isfinite(volts[dest])):
                continue
            watts=float(-matrix.data[pos]*(volts[node]-volts[dest])**2)
            if watts < 0:
                raise ValueError('positive off-diagonal conductance')
            barrel_network_w += watts
            other=barrel_nodes.get(dest)
            if other is None:
                barrel_heat[via_index][layer] += watts/2
                key,i,j=node_cells[dest]
                arrays[f'{key}_joule_w'][i,j] += watts/2
            elif other[1] == layer:
                barrel_heat[via_index][layer] += watts
            else:
                barrel_heat[via_index][layer] += watts/2
                barrel_heat[via_index][other[1]] += watts/2
    np.savez_compressed(output, **arrays)
    barrel_heat_rows=[{'xy_mm':list(via['xy']), 'filled_lead':via['filled'],
                       'drill_mm':via['drill_mm'], 'plating_um':via['plating_m']*1e6,
                       'layer_joule_w':dict(barrel_heat[i])}
                      for i,via in enumerate(net.vias)]
    return {'layer_max_a_per_mm':peaks, 'sheet_joule_w':sheet_w,
            'vertical_barrel_joule_w':barrel_w, 'barrel_network_joule_w':barrel_network_w,
            'barrel_hop_heat':barrel_hops, 'barrel_heat_by_layer':barrel_heat_rows,
            'nodal_heat_file':output.name,
            'energy_balance_error_w':sheet_w+barrel_network_w-solved['loss_w']}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--net',required=True)
    ap.add_argument('--pitch',type=float,default=.125)
    ap.add_argument('--plating',type=float,default=18)
    ap.add_argument('--source',action='append', help='REF or REF:amps; repeat for multiple pads')
    ap.add_argument('--draw',action='append', default=[], help='REF:amps explicit withdrawal; remaining current goes to reference sink')
    ap.add_argument('--sink',action='append', help='REF; repeat for multiple pads')
    ap.add_argument('--amps',type=float,default=18.7)
    ap.add_argument('--name',help='unique scenario ID in output filename')
    a=ap.parse_args()
    src=HERE/'inputs/power_copper.json.gz'
    data=json.load(gzip.open(src,'rt'))
    net,barrels,pads=load_net(data,a.net,a.pitch,a.plating)
    result={'board_sha256':data['board_sha256'], 'input_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
            'kit_sha256':hashlib.sha256(KIT.read_bytes()).hexdigest(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'net':a.net,'pitch_mm':a.pitch,'plating_um':a.plating,
            'evidence_class':'simulation/model-based', 'status':'preflight'}
    name=a.name or f'{a.net}-p{a.pitch}-pl{a.plating}'
    out=HERE/'outputs'/f'{name}.json'
    try:
        audit=audit_contacts(net,barrels)
        result['contact_audit']=audit
        if audit['uncovered_contacts']:
            raise ValueError('kit barrel-contact edges cross non-copper; stop before board solve')
        if a.source and a.sink:
            source_spec=[]
            for term in a.source:
                ref, sep, value = term.partition(':')
                source_spec.append((ref,float(value) if sep else a.amps/len(a.source)))
            sources=[]
            for ref,amps in source_spec:
                physical=pads[ref]
                if not physical:
                    raise ValueError(f'missing source pad {ref}')
                sources.extend(('F.Cu',*p['centre'],amps/len(physical)) for p in physical)
            drive_amps=sum(amps for _,amps in source_spec)
            for term in a.draw:
                ref, sep, value = term.partition(':')
                if not sep:
                    raise ValueError('--draw requires REF:amps')
                physical=pads[ref]
                if not physical:
                    raise ValueError(f'missing draw pad {ref}')
                amps=float(value)
                sources.extend(('F.Cu',*p['centre'],-amps/len(physical)) for p in physical)
            sinks=[]
            for ref in a.sink:
                physical=pads[ref]
                if not physical:
                    raise ValueError(f'missing sink pad {ref}')
                sinks.extend(('F.Cu',*p['centre']) for p in physical)
            solved=net.solve(sources,sinks)
            # The kit's total sums signed injections; for explicit draws the
            # physically useful loss-equivalent R uses positive drive current.
            if a.draw:
                solved['r_ohm']=solved['loss_w']/drive_amps**2
            for via in solved['via_currents']:
                via['status'] = 'solved' if all(math.isfinite(x) for x in via['hop_amps']) else 'unused island; potential undefined'
                via['hop_amps'] = [float(x) if math.isfinite(x) else None for x in via['hop_amps']]
                via['amps'] = float(via['amps']) if math.isfinite(via['amps']) else None
            result.update(status='conditional DC experiment',source_pad=a.source,draw_pad=a.draw,
                          sink_pad=a.sink,drive_amps=drive_amps,
                          reference_sink_amps=drive_amps-sum(float(t.partition(':')[2]) for t in a.draw),
                          sources=sources,sinks=sinks,r_ohm=solved['r_ohm'],loss_w=solved['loss_w'],
                          unused_island_cells=solved['unused_island_cells'],via_currents=solved['via_currents'])
            result.update(sheet_and_heat(net,solved,HERE/'outputs'/f'{name}-heat.npz'))
            result['assumptions']=['20 C copper; DC resistive spreading only',
                'equal current at physical source leads; equipotential sink leads',
                'all through-hole leads solder-filled; vertical conduction uses plating alone',
                'specified current is an experiment, not a verified operating waveform']
        else:
            result['status']='contact preflight complete; no excitation'
    except ValueError as exc:
        result.update(status='BLOCKED',reason=str(exc))
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(out.relative_to(UNIT)), 'status':result['status'],
                      'reason':result.get('reason'), 'uncovered_contacts':len(result.get('contact_audit',{}).get('uncovered_contacts',[]))}))
    return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':
    raise SystemExit(main())
