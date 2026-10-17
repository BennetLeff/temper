"""Read-only nominal STEP/envelope comparison; no thermal or clearance approval."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'zapote').is_dir())
P = ROOT / 'zapote/power-stage-120v/prototype-closure'


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--step', type=Path, required=True)
    args = parser.parse_args()
    (HERE / 'fit-status.json').write_text(json.dumps({'status': 'INCOMPLETE'}) + '\n')
    digest = hashlib.sha256(args.step.read_bytes()).hexdigest()
    expected = '5921406f7249cf716cdd2d20be8ae79215760f20cce1f01dda443be85356c1fa'
    if digest != expected:
        raise ValueError(f'Unreviewed geometry: {digest}')
    packaging = load(P / 'round3/packaging/build_proposal.py', 'packaging')
    cooling = load(P / 'round2/cooling/build_revision.py', 'cooling')
    box, bounds, hits = packaging.box, packaging.bounds, packaging.hits
    # Discriminating instrument checks: asymmetric positive overlap and separation.
    a = box([1, 2, 3], [4, 5, 6])
    if abs(a.intersect(box([3, 4, 5], [4, 5, 6])).Volume() - 24) >= 1e-8:
        raise ValueError('Overlap instrument check failed')
    if abs(a.distance(box([8, 2, 3], [1, 1, 1])) - 3) >= 1e-8:
        raise ValueError('Distance instrument check failed')
    print('Reading pinned STEP', flush=True)
    parts = packaging.read_parts(args.step)
    inventory = {k: bounds(v) for k, v in sorted(parts.items())}
    (HERE / 'geometry-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    print(f'Read {len(parts)} named shapes', flush=True)
    interface = json.loads((P / 'round2/cooling/interface.json').read_text())
    filter_box = box(interface['emi']['module_min'], interface['emi']['module_size'])
    # Use the source air volume, not the hollow duct wall, to test exhaust exclusion.
    airflow = interface['airflow']
    left_shell, left_air = cooling.make_duct('LEFT', airflow['side_duct_wall'],
        airflow['leg_sleeve_inner_radius'], airflow['leg_sleeve_outer_radius'])
    subjects = {k: parts[k] for k in (
        'BASE_R2_CUSTOM_SINK', 'BASE_R2_RIGHT_PUSH_FAN', 'BASE_R2_LEFT_PULL_FAN')}
    custom_hits = hits(subjects, {k: v for k, v in parts.items() if k not in subjects})
    duct_names = ['BASE_R2_LEFT_DUCT', 'BASE_R2_RIGHT_DUCT', 'BASE_R2_SINK_DUCT_TOP']
    cooling_names = set(subjects) | set(duct_names)
    duct_hits = hits({k: parts[k] for k in duct_names}, {k: v for k,v in parts.items() if k not in cooling_names})
    exhaust_hits = hits({'left_air': left_air}, {k: v for k,v in parts.items() if k not in cooling_names})
    floor = parts['BASE_R4_two_bend_bottom_and_sides']
    floor_distances = {k: v.distance(floor) for k,v in {**subjects, 'D22': filter_box}.items()}
    # Catalog counterfactual: preserve existing center X, front contact plane and floor Z.
    # Remove the custom sink and its two fans only; retained ducts/mounts are the test.
    catalog = {}
    for name, depth, height in [('upright', 60, 68), ('rotated', 68, 60)]:
        y = 161.9 - depth
        replacement = {
            'sink': box([-164.5, y, 12], [305, depth, height]),
            'left_fan': box([-189.5, y, 12], [25, 60, 60]),
            'right_fan': box([140.5, y, 12], [25, 60, 60]),
        }
        catalog[name] = {
            'envelopes_mm': {k: bounds(v) for k, v in replacement.items()},
            'envelope_intersections': hits(replacement, {k: v for k, v in parts.items() if k not in subjects}),
        }
        print(f'Checked catalog {name}', flush=True)
    fischer = {}
    for name, depth, height in [('upright', 62, 74), ('rotated', 74, 62)]:
        y = 161.9 - depth
        replacement = {'body': box([-112, y, 12], [200, depth, height]),
                       'right_fan': box([88, y, 12], [25, 60, 60])}
        fischer[name] = {'envelopes_mm': {k: bounds(v) for k,v in replacement.items()},
                         'envelope_intersections': hits(replacement, {k:v for k,v in parts.items() if k not in subjects})}
    filter_context = {k: v for k, v in parts.items() if not k.startswith('BASE_R2_FILTER_')}
    filter_hits = hits({'D22_full_envelope': filter_box}, filter_context)
    # Mesher's region constants, without importing gmsh or building a native bridge.
    source = ROOT / 'zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/mesh25d_hybrid.py'
    text = source.read_text()
    legs = ast.literal_eval(re.search(r'^LEGS = (\{.*\})$', text, re.M)[1])
    for match in re.finditer(r'^LEGS\["(\w+)"\] = (\(.*\))$', text, re.M):
        legs[match[1]] = ast.literal_eval(match[2])
    ox, oy = interface['board']['origin_xy']
    regions = {}
    for name in ('A', 'B'):
        x0, y0, x1, y1 = legs[name]
        # Conservative rectangular 20 mm grow used by leg_region_diff; mesher clips
        # its front edge at -0.5 mm. Keeping the larger region cannot fake separation.
        origin = [x0 - 20 + ox, y0 - 20 + oy, 0]
        shape = box(origin, [x1-x0+40, y1-y0+40, 120])
        regions[name] = {'bounds_mm': bounds(shape), 'D22_distance_mm': filter_box.distance(shape),
                         'D22_intersection_mm3': filter_box.intersect(shape).Volume()}
    report = {
        'status': 'NOMINAL_GEOMETRY_ONLY', 'cadquery': cq.__version__,
        'source_step': str(args.step), 'source_step_sha256': digest,
        'named_shapes': len(parts), 'instrument_checks': 'PASS',
        'custom_sink_and_fans_intersections': custom_hits,
        'retained_duct_intersections': duct_hits, 'left_exhaust_air_obstacles': exhaust_hits,
        'distance_to_bottom_and_sidewalls_mm': floor_distances,
        'Fischer_LA6_body_plus_one_right_fan': fischer,
        'source_adapters_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [P/'round3/packaging/build_proposal.py', P/'round2/cooling/build_revision.py', P/'round2/cooling/interface.json', source]},
        'D22': {'bounds_mm': bounds(filter_box), 'context_intersections': filter_hits,
                'left_exhaust_air_distance_mm': filter_box.distance(left_air),
                'left_exhaust_air_intersection_mm3': filter_box.intersect(left_air).Volume(),
                'left_duct_wall_distance_mm': filter_box.distance(parts['BASE_R2_LEFT_DUCT']),
                'regions': regions},
        'catalog_SFA2B1L_with_two_fans': catalog,
        'scope': 'Round3 R4 barrier STEP; later boards/catch/service wiring not assembled here. Catalog bodies are filled allocation boxes, not fin geometry. No pose optimization.',
    }
    (HERE / 'fit-results.json').write_text(json.dumps(report, indent=2) + '\n')
    (HERE / 'fit-status.json').write_text(json.dumps({'status': 'COMPLETE_NOMINAL_ONLY', 'result_sha256': hashlib.sha256((HERE/'fit-results.json').read_bytes()).hexdigest()}) + '\n')
    print(json.dumps({'custom_intersections': len(custom_hits), 'filter_intersections': len(filter_hits),
                      'catalog_intersections': {k: len(v['envelope_intersections']) for k,v in catalog.items()},
                      'D22': report['D22']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
