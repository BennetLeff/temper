#!/usr/bin/env python3
"""Generate the ``In2.Cu`` power-island pours (``+3V3``/``vcc``/``+15V``/
``V_BUS_SENSE``) and write the result to a new file.

Thin CLI wrapper around
``temper_placer.router_v6._power_islands.generate_power_islands_content`` --
see that module's docstring for the full "why" (inner-layer planes are
declared in the board file but no code path in router_v6 ever emits
copper onto them; ``scripts/generate_ground_plane.py`` was the first one,
for ``In1.Cu``/``gnd``; this is the ``In2.Cu`` counterpart).

**Never writes ``--pcb`` in place.** ``--output`` is mandatory and refused
if it resolves to the same path as ``--pcb``, mirroring
``scripts/generate_ground_plane.py``'s/``scripts/route_board.py``'s own
safety convention -- this script does not itself decide when (or
whether) the generated islands are safe to adopt as the tracked board;
that requires a DRC/zone-fill verification pass this script does not
run.

Usage:
    uv run python3 scripts/generate_power_islands.py \\
        --pcb pcb/temper.kicad_pcb --output /tmp/temper_with_power_islands.kicad_pcb

    # Just the highest-value rail (largest pad count):
    uv run python3 scripts/generate_power_islands.py \\
        --pcb pcb/temper.kicad_pcb --output /tmp/temper_3v3_only.kicad_pcb --nets +3V3
"""

from __future__ import annotations

import argparse
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
    parser.add_argument(
        "--nets",
        nargs="+",
        default=None,
        help="Net names to generate islands for, in priority order "
        "(default: +3V3 vcc +15V V_BUS_SENSE, pad-count-descending).",
    )
    args = parser.parse_args(argv)

    if args.pcb.resolve() == args.output.resolve():
        parser.error("--output must not resolve to the same path as --pcb")

    from temper_placer.router_v6._power_islands import (
        POWER_ISLAND_NETS,
        generate_power_islands_content,
    )

    nets = tuple(args.nets) if args.nets else POWER_ISLAND_NETS
    content, results = generate_power_islands_content(
        args.pcb, nets=nets, domain_manifest_path=args.domain_manifest
    )
    args.output.write_text(content)
    print(f"Wrote {args.output}")
    for net_name in nets:
        result = results.get(net_name)
        print(result if result is not None else f"{net_name}: skipped (not found on this board)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
