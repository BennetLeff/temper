#!/usr/bin/env python3
"""Mechanical PSpice -> ngspice conversion for Infineon power-device .lib files.

This is a *syntax* conversion only; the device physics and every element type
(including the behavioral E/G voltage/current sources) are preserved.

Transformations:
  1. `if(cond, a, b)` / `IF(...)` -> `iif(cond, a, b)`, with
     `.func iif(c,a,b) { (c) ? (a) : (b) }` injected at the top of the library.
     ngspice-45 has no `if()` expression function but the native ternary works in
     both B sources and behavioral E/G sources (verified).
  2. PSpice `PARAMS:` continuation lines use `name value` (no `=`); ngspice wants
     `name=value`.  Applied only to `+ fparNN value` lines.
  3. PSpice exponent `^` -> `**` (ngspice power operator).

Element types E and G are NOT rewritten.  Earlier attempts that rewrote them as
B sources made ngspice fail to take the first transient step ("Timestep too
small; initial timepoint: trouble with node ...b_eds4#branch"), whereas the
original E/G elements run.

Usage: convert_infineon_pspice_to_ngspice.py <in.lib> <out.lib>
"""
import re
import sys

HEADER = (
    "* --- ngspice conversion shim (added by convert_infineon_pspice_to_ngspice.py)\n"
    "* Syntax-only conversion; E/G element types unchanged.  ngspice-45 has no\n"
    "* if(); iif() is the native ternary, valid in B and behavioral E/G sources.\n"
    ".func iif(c,a,b) { (c) ? (a) : (b) }\n"
)


def convert_line(line: str) -> str:
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    if stripped.startswith("*"):
        return line
    new = re.sub(r"\bif\s*\(", "iif(", stripped, flags=re.IGNORECASE)
    new = new.replace("^", "**")
    new = re.sub(r"(\+\s*fpar\d+)[ \t]+([^=\r\n \t]+)[ \t]*(?=\r?\n|$)", r"\1=\2", new)
    if new != stripped:
        return indent + new
    return line


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    n_if = 0
    with open(src) as f:
        lines = f.readlines()
    out = [HEADER]
    for line in lines:
        n_if += len(re.findall(r"\bif\s*\(", line, flags=re.IGNORECASE))
        out.append(convert_line(line))
    with open(dst, "w") as f:
        f.writelines(out)
    print(f"renamed {n_if} if() -> iif(); element types preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
