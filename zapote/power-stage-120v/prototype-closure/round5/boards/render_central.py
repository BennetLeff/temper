"""Reuse pinned typed KiCad renderer for the source-derived central partition."""

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = HERE.parents[1] / "round4/supervisor/render.py"
spec = importlib.util.spec_from_file_location("round4_renderer", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE = HERE / "central"
native = module.HERE / "native"
sidecars = {
    p: p.read_bytes()
    for p in [native / "supervisor.kicad_pro", native / "fp-lib-table"]
    if p.exists()
}
module.render()
for p, data in sidecars.items():
    p.write_bytes(data)
# The physical 24V supply and wired 5V converter are external to this partition.
# Power flags declare external connector-fed rails for ERC, not on-board producers.
# D-30: J9 receives CTRL_3V3/CTRL_GND from the controller. The independent
# power_direction.rs validator requires these exact boundaries and ignores flags.
flag = """(symbol "Supervisor:ExternalPower" (power) (pin_names (offset 0)) (in_bom no) (on_board no)
(property "Reference" "#FLG" (at 0 0 0) (effects (font (size 1 1)) hide))
(property "Value" "PWR_FLAG" (at 0 4 0) (effects (font (size 1 1))))
(symbol "ExternalPower_1_1" (pin power_out line (at 0 0 90) (length 0) (name "pwr" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))))"""
p = native / "supervisor.kicad_sch"
text = p.read_text()
text = text.replace("(lib_symbols)", f"(lib_symbols {flag})", 1)
items = []
external_rails = [
    ("AUX_24V", "External supply"),
    ("AUX_0V", "External supply"),
    ("POD_5V", "External supply"),
    ("CTRL_3V3", "Controller supply via J9.1"),
    ("CTRL_GND", "Controller return via J9.2"),
]
for i, (net, description) in enumerate(external_rails, 1):
    x = 30.48 + 50.8 * i
    y = 480.06
    ref = f"#FLG0{i}"
    items.append(f'''(symbol (lib_id "Supervisor:ExternalPower") (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid "{module.uid(ref)}")
(property "Reference" "{ref}" (at {x} {y} 0) (effects (font (size 1 1)) hide))
(property "Value" "{description}" (at {x} {y - 5.08} 0) (effects (font (size 1 1))))
(pin "1" (uuid "{module.uid(ref + "pin")}")) (instances (project "supervisor" (path "/{module.uid("root")}" (reference "{ref}") (unit 1)))))
(global_label "{net}" (shape bidirectional) (at {x} {y} 0) (effects (font (size 1.27 1.27)) (justify left)) (uuid "{module.uid(net + "flag")}"))''')
text = text.rstrip()
p.write_text(text[:-1] + "".join(items) + ")\n")
lib = native / "supervisor.kicad_sym"
t = lib.read_text().rstrip()
lib.write_text(t[:-1] + flag.replace('"Supervisor:ExternalPower"', '"ExternalPower"', 1) + ")\n")
