"""Emit local symbol sidecars and a grid-aligned standalone schematic.

This uses the existing source netlist/parser/symbol emitter. It changes drawing
geometry and library references only; native netlist equality is checked by the
caller before this post-generation step is accepted. PCB files are untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

LIBRARY = "CurrentSenseUnit"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drawing_height(part: Any) -> float:
    # Donor pin pitch is 5.08 mm. Bound the drawn box around those unchanged
    # pin positions instead of its historical count*5.08 half-height.
    largest_side = (len(part.pins) + 1) // 2
    return max(5.08, (largest_side - 1) * 2.54 + 2.54)


def library_symbol(donor, part) -> str:
    symbol = donor.synthesize_symbol(part)
    old_height = max(len(part.pins) * 5.08, 5.08)
    height = drawing_height(part)
    symbol = symbol.replace(
        f'(start -12.70 {-old_height:.2f}) (end 12.70 {old_height:.2f})',
        f'(start -12.70 {-height:.2f}) (end 12.70 {height:.2f})')
    for sign in (-1, 1):
        symbol = symbol.replace(f'(at 0 {sign*(old_height+2.54):.2f} 0)',
                                f'(at 0 {sign*(height+2.54):.2f} 0)')
    return symbol


def run(repo: Path, source: Path, output: Path, receipt_path: Path) -> None:
    sys.path.insert(0, str(repo / "scripts"))
    import gen_schematics as donor  # type: ignore[import-not-found]

    net_path = source / "build/default.net"
    bom_path = source / "build/default.csv"
    netlist = donor.parse_netlist(net_path)
    donor.apply_bom_values(netlist, donor.load_bom_values(bom_path))
    components = sorted(netlist.components.values(), key=lambda c: c.ref)
    parts = {c.part_name: netlist.libparts[c.part_name] for c in components}
    symbols = {name: library_symbol(donor, part) for name, part in sorted(parts.items())}
    library = '(kicad_symbol_lib (version 20231120) (generator "zapote_current_sense")\n'
    library += '\n'.join(symbols.values()) + '\n)\n'
    drawing = [donor._schematic_header('Standalone Current-Sensing Unit', donor.ROOT_UUID)
               .replace('(paper "A3")', '(paper "A2")'),
               '(lib_symbols']
    for name, text in symbols.items():
        symbol_id = donor._sanitize_name(name)
        drawing.append(text.replace(f'(symbol "{symbol_id}"',
                                    f'(symbol "{LIBRARY}:{symbol_id}"', 1))
    drawing.append(')')
    pin_net = {(ref, pin): net.name for net in netlist.nets.values()
               for ref, pin in net.nodes}
    singles = {(ref, pin): net.name for net in netlist.nets.values()
               if len(net.nodes) == 1 for ref, pin in net.nodes}
    marked_open = []
    y = 50.8
    for start in range(0, len(components), 5):
        row = components[start:start + 5]
        row_height = max(drawing_height(parts[c.part_name]) for c in row)
        y += row_height
        for column, component in enumerate(row):
            x = 76.2 + column * 76.2
            part = parts[component.part_name]
            sid = LIBRARY + ':' + donor._sanitize_name(component.part_name)
            drawing.append(donor._symbol_instance(
                component.ref, sid, x, y, component.footprint, component.part_name,
                donor._uuid_from_seed(f'flatinst:{component.tstamp}'),
                libpart=part, display_value=component.display_value))
            for number, _ in part.pins:
                px, py = donor._pin_absolute_position(part, number, x, y)
                net = pin_net.get((component.ref, number))
                if net is not None:
                    label = donor._global_label(net, px, py,
                        donor._uuid_from_seed(f'label:{component.ref}:{number}:{net}'))
                    if px < x:
                        label = label.replace(f'(at {px:.2f} {py:.2f} 0)',
                                              f'(at {px:.2f} {py:.2f} 180)')
                        label = label.replace('(justify left bottom)', '(justify right bottom)')
                    drawing.append(label)
                if net is None or (component.ref, number) in singles:
                    drawing.append(donor._no_connect(px, py,
                        donor._uuid_from_seed(f'nc:{component.ref}:{number}')))
                    marked_open.append([component.ref, number, net])
        y += row_height + 15.24
    if y > 390:
        raise ValueError('standalone schematic exceeds the authored A2 drawing area')
    drawing.append(')')
    output.mkdir(parents=True, exist_ok=True)
    schematic_path = output / 'section.kicad_sch'
    before = digest(schematic_path) if schematic_path.exists() else None
    artifacts = {
        'section.kicad_sch': '\n'.join(drawing) + '\n',
        'current-sense-unit.kicad_sym': library,
        'sym-lib-table': '(sym_lib_table (version 7)\n'
            ' (lib (name "CurrentSenseUnit")(type "KiCad")'
            '(uri "${KIPRJMOD}/current-sense-unit.kicad_sym")(options "")'
            '(descr "Generated standalone CurrentSenseUnit source symbols")))\n',
    }
    for name, content in artifacts.items():
        (output / name).write_text(content)
    receipt = {'status': 'emitted-native-verification-required',
               'source_netlist_sha256': digest(net_path),
               'source_bom_sha256': digest(bom_path),
               'donor_sha256': digest(Path(donor.__file__)),
               'helper_sha256': digest(Path(__file__)),
               'input_schematic_sha256': before,
               'outputs': {name: digest(output / name) for name in artifacts},
               'intentional_open_pins': marked_open,
               'component_count': len(components),
               'native_erc': 'NOT RUN', 'native_netlist_equality': 'NOT RUN',
               'pcb_touched': False}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    run(args.repo.resolve(), args.source.resolve(), args.output.resolve(), args.receipt.resolve())
