#!/usr/bin/env python3
"""Generate the ``gnd`` In1.Cu plane (spike/keepout-before-pour) and write
the result to a new file.

Thin CLI wrapper around
``temper_placer.router_v6._ground_plane.generate_ground_plane_content`` --
see that module's docstring for the full "why" (inner-layer planes are
declared in the board file but no code path in router_v6 ever emits
copper onto them; this is the first one).

**Never writes ``--pcb`` in place.** ``--output`` is mandatory and refused
if it resolves to the same path as ``--pcb``, mirroring
``scripts/route_board.py``'s own safety convention -- this script does
not itself decide when (or whether) the generated plane is safe to adopt
as the tracked board; that requires a DRC/zone-fill verification pass
this script does not run (see the module docstring and
docs/evidence/2026-08-11-keepout-before-pour-spike.md S:"What this does
not do").

Usage:
    uv run python3 scripts/generate_ground_plane.py \\
        --pcb pcb/temper.kicad_pcb --output /tmp/temper_with_gnd_plane.kicad_pcb
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcb", type=Path, required=True, help="Input .kicad_pcb path.")
    parser.add_argument(
        "--output", type=Path, required=True, help="Output .kicad_pcb path (must differ from --pcb)."
    )
    parser.add_argument(
        "--domain-manifest",
        type=Path,
        default=Path("elec/domain_manifest.yaml"),
        help="Path to the HV/SELV domain manifest (default: elec/domain_manifest.yaml).",
    )
    args = parser.parse_args(argv)

    if args.pcb.resolve() == args.output.resolve():
        parser.error("--output must not resolve to the same path as --pcb")

    from temper_placer.router_v6._ground_plane import generate_ground_plane_content

    content, result = generate_ground_plane_content(
        args.pcb, domain_manifest_path=args.domain_manifest
    )
    args.output.write_text(content)
    print(f"Wrote {args.output}")
    print(result)
    if not result.keepout_established:
        print(
            "WARNING: no HV keepout could be established -- refusing to trust "
            "this output for a mains board would be the safe default; "
            "investigate before using this file for anything.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
