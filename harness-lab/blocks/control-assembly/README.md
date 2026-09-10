# Control-assembly block (P1 U2): combined buck + MCU source

Owner: P1 (`docs/plans/2026-09-10-1322-feat-atopile-mcu-flow-plan.md` U2).
Wrapper only: no copper, no placement, no P2/P3-owned files.

## What this is

An isolated Atopile build root instantiating the **real**
`BuckConverter3V3` and `MCU` modules from production `elec/src`, joined by
their source-defined supply/return connection
(`buck.power_out.vcc ~ mcu.power.vcc`,
`buck.power_out.gnd ~ mcu.power.gnd`), so P3 can generate its assembly
without authoring another export path.

## Reproduce the build

```bash
rm -rf /tmp/combo-ws && mkdir -p /tmp/combo-ws
cp harness-lab/blocks/control-assembly/control-assembly.ato \
   harness-lab/blocks/control-assembly/ato.yaml /tmp/combo-ws/
mkdir -p /tmp/combo-ws/elec && cp -r elec/src /tmp/combo-ws/elec/src
rm -f /tmp/combo-ws/elec/src/*.log
cd /tmp/combo-ws && uv tool run --offline --from atopile==0.2.69 \
  ato --non-interactive build control-assembly.ato:ControlAssemblyCandidate
```

Pinned tool: Atopile 0.2.69 (same pin as `harness-lab/circuit_native.py`).
Measured 2026-09-10: clean build, all buck + MCU assertions pass, with one
shared supply net and one shared return net joining both blocks'
instance paths.

## Join discipline

Joining whole power interfaces (`buck.power_out ~ mcu.power`) fails: both
sides define `voltage = 3.3V` and Atopile rejects two definitions on a
joined net even when the values agree (measured error: "source and target
separately defined values for the attribute voltage"). The signal-level join
above connects the same copper while each interface keeps its own single
definition and local assertions. Do not "fix" this by deleting either
module's voltage declaration.

## Files

- `control-assembly.ato`, `ato.yaml` — isolated wrapper (proven by the
  build above).
- `harness-lab/test_block_source.py::ControlAssemblyContract` — build,
  assertion, and shared supply/return tests.
