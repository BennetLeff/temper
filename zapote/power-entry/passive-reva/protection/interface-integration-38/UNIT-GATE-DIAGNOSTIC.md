# Maintained Zapote unit gate diagnostic

**Status: FAIL for the maintained suite; no Rev38 U7 credit.** On
2026-09-24 local time, the full maintained-unit check ran with KiCad's
framework Python:

```sh
KICAD_PYTHON=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
  make -C zapote check-units
```

The run saved `zapote/validation/runs/20260925T015618Z/summary.json`
(SHA-256 `819ed6206d7ba47a2618e1747d990feb0c488e7c0e3f9c636f9ec2d4aa266`).
Its seven maintained units returned six `indeterminate` and one `fail`.
The failing unit is the existing `power-entry` design; its report
(SHA-256 `36038f5bfa6df76ed0fcf6383758e1fdf7cbde378d17e87d4df3d3bcc27602c8`)
reports `ERC.PFC.SHUNT_PART`: authored `WSL2726R0100FEA` does not substantiate
the claimed 10 mΩ, two-pad shunt. This is an existing source-part issue, not
a finding on the Rev38 diagnostic board. The other six units remain
indeterminate on their own evidence gaps. The suite result is not waived.

This maintained-unit runner does not accept `placement-review/02/` as a
Rev38 candidate. That board's separate KiCad ERC, non-routing DRC,
footprint parity and source-edge checks are recorded in its README; U7
remains open for reviewed placement, routing, insulation and physical work.
