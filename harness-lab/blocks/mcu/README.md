# MCU block (P1 U1): source-derived circuit contract

Owner: P1 (`docs/plans/2026-09-10-1322-feat-atopile-mcu-flow-plan.md` U1).
Contract/inventory only: no copper, no placement, no P2/P3-owned files.

## What this is

An isolated Atopile build root for `elec/src/modules.ato::MCU`, plus the
reviewed identity inventory the U2 board generator must satisfy. The
implementation stays owned by production `elec/src`; `mcu.ato` only
supplies the `McuCandidate` entry (power + stubs for the three required
sense signals whose destinations live in other cooker units).

## Reproduce the build

```bash
rm -rf /tmp/mcu-ws && mkdir -p /tmp/mcu-ws
cp harness-lab/blocks/mcu/mcu.ato harness-lab/blocks/mcu/ato.yaml /tmp/mcu-ws/
mkdir -p /tmp/mcu-ws/elec && cp -r elec/src /tmp/mcu-ws/elec/src
rm -f /tmp/mcu-ws/elec/src/*.log
cd /tmp/mcu-ws && uv tool run --offline --from atopile==0.2.69 \
  ato --non-interactive build mcu.ato:McuCandidate
```

Pinned tool: Atopile 0.2.69 (same pin as `harness-lab/circuit_native.py`).
Measured 2026-09-10: clean build, 3/3 assertions pass, exactly 10 physical
instances (U1, C1-C3, R1-R4, SW1-SW2); netlist/BOM hashes are recorded in
`identity-inventory.json`.

Two instrument caveats, both measured:

- Atopile exits nonzero on a FAILED assertion but still writes
  netlist/BOM artifacts (measured 2026-09-10: rc=1 with the old 9-11ms
  band under the honest +/-10% tolerance, artifacts present). Consumers
  must gate on return code AND the assertions report, and never consume
  artifacts from a failed build. The U2 bridge takes this as a strict
  input.
- Netlist `value` fields are `?` for all components and `libsource` carries
  an MPN alias: neither is an authoritative part identity (KTD3). Exact
  MPNs come from the CSV joined through the designator map; values come
  from resolved attributes (U2 bridge).

## Source discrepancies handled in U1

1. `c_en` tolerance fiction (FIXED in `elec/src/modules.ato`): declared
   `1uF +/-2%` against MPN GRM188R71A105KA61D (K = +/-10%). The old
   9-11ms/13-15ms RC bands passed only against the fiction; a fresh build
   with the honest tolerance FAILS them (8.82-11.22ms). Now declares
   +/-10% with 8.5-11.5ms/12-16ms bands containing the honest worst case.
   `main.ato`'s fixed `t_mcu_boot=14ms` still sits inside the delay band.
2. DRDY/IO9 "assumption" (FIXED): comment now cites firmware ground truth
   (`temper_pins.h` `PIN_RTD_DRDY=9`, `main.c`, README).
3. ESP32-S3-WROOM-1-N8R8 variant (VERIFIED against Espressif product page
   2026-09-10): N8R8 ordering code exists (8MB flash + 8MB octal PSRAM, PCB
   antenna, 18x25.5x3.1mm); matches the component `flash_size/psram_size`.
   Pad-level census against the manufacturer pin table (including module
   ground pads; the model exposes a single GND~pin1) is an open R3 map item
   for U2, not a U1 assertion.

## Firmware cross-check (2026-09-10 worktree state)

Agree: PWM 4/5, ADC 1/2/3, SPI 8/10/11/12, DRDY 9, WDI 7, WDT-reset 6,
runaway 15, reset-in 14, BOOT IO0, I2C 38/39.

Open obligations (named owners; contested pins get no copper until
resolved; recorded in `identity-inventory.json` firmware_crosscheck):

- OBLIGATION-1: relay_ctrl=IO16 vs firmware CS_RTD2=16 / RELAY_BYPASS=19.
- OBLIGATION-2: fault_status_in=IO17 vs firmware LED_FAULT=17; LED_POWER=18
  has no source net.
- OBLIGATION-3: native USB on IO19/20 vs firmware RELAY_BYPASS=19 /
  FAULT_OUT=20.
- OBLIGATION-4: discharge_ctrl=IO47 missing from `temper_pins.h`.
- OBLIGATION-5: UART on TXD0/RXD0 (pads 37/36) vs firmware GPIO43/44.

## Adopted layout guidance (manufacturer)

Espressif ESP32-S3 hardware design guidelines (latest, retrieved
2026-09-10; exact revision pinned when P3 U1 freezes the numeric contract):
module-on-board placement with the PCB antenna outside the base-board edge
(feed point at the edge, ~15mm housing clearance, ground copper + dense
ground vias near the antenna); USB 90-ohm diff +/-10%, length-matched,
minimal vias, continuous GND reference; UART away from the antenna and
ground-surrounded; 10uF + 0.1/1uF at the power entrance with star routing.
Exact numeric MCU rules are established jointly with the P3 target context.

## Files

- `mcu.ato`, `ato.yaml` — isolated wrapper (proven by the build above).
- `identity-inventory.json` (`temper.mcu-identity.v1`) — machine-readable
  contract: 10 instances, interfaces, boundary nets with U1 pads,
  assertions, hashes, obligations.
- `harness-lab/test_block_source.py` — contract tests (inventory match,
  identity stability, mutation rejection).

## U2 generation (strict source-to-board bridge)

`harness-lab/block_source.py::assemble_mcu_candidate` compiles this wrapper
in a fresh workspace (gating on return code AND the assertions report),
converts the resolved export through the strict Rust bridge
(`temper-design-bundle`: `candidate_convert_bridge`,
`candidate_validate_pin_map`, `validation.candidate_check_freshness`,
`validation.candidate_check_net_admission`), and generates a fresh
candidate directory (vendored local libs, project, rules, source manifest,
schematic, PCB) with the P3 outline/six-layer stackup and neutral staging.
No production-PCB geometry is read. Regenerate any time with:

```bash
uv run --no-sync --with kiutils python harness-lab/block_source.py \
  --output-dir /tmp/mcu-candidate
```

The combined buck+MCU wrapper for P3 lives in
`harness-lab/blocks/control-assembly/` (proven by
`test_block_source.py::ControlAssemblyContract`).

## Coordinator join

The accepted package state (`assisted-verified-apparatus-only`, run
`harness-lab/runs/mcu-20260910-b/`), its exact board/manifest identities, the
replay result, and the remaining interface obligations are joined in
`docs/hardware/control-assembly/harness-report.md`. Only the assisted
generator path is accepted; the unassisted candidate and the blocked live
transport remain separate evidence, and the milestone stays INCOMPLETE until
the live delivery gap closes. The apparatus-only construction now passes the
full native check (DRC 0, unconnected 0, schematic parity 0, block judge pass).
