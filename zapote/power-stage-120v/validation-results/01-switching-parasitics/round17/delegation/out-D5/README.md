# D5 — controller-to-gate dead time

**For both HS-off→LS-on and LS-off→HS-on, on both legs, the actual minimum and maximum output/gate dead times are unestablished; this firmware does not prove that 307 ns or any interval below 348 ns is unreachable.**

The source has no production PWM initialization caller, no established full-bridge pin mapping, and a conditional HAL setup defect. Stop the proposed exclusion of the short-dead-time D2 corners. These are reported contradictions and missing integration evidence, not firmware or board repairs. The D5 investigation is complete as an unresolved timing contract; hardware qualification is open.

## Identity and method

Reviewed source: `1f09223516cc37d00f73b5e5e6d33a0197d7a30d`. All repository file:line citations below refer to that commit. [gate_dead_time.py](gate_dead_time.py) verifies [input hashes](input-hashes.json), searches production C/H callers, extracts frozen net memberships using D1's existing parser, and replays integer arithmetic and a translation of Espressif's resource guards. [gate_dead_time.txt](gate_dead_time.txt) is its output. It is a static investigation and arithmetic replay, not execution of firmware, an ESP32 emulator, an SDK build, or a measurement of the physical board. The caller scan is lexical; manual inspection of the entry point, HAL registration and external stubs supplies the reachability context.

## What the repository actually configures

| Source | Finding |
| --- | --- |
| `firmware/main/main.c:138–155` | `hal_init()` runs; the separate `mcpwm_init()` line is commented out. |
| `firmware/components/hal/esp32/hal_init.c:44–74` | Registers `hal_pwm_esp32_ops`; does not initialize a PWM channel. |
| `firmware/main/state_handlers.c:23–41`, `firmware/main/state_machine.c:54–70` | Peripheral/power/PWM routines are external stubs. Test implementations are in `firmware/test/state_machine_stubs.c`; they do not establish target PWM timing. |
| `firmware/components/hal/include/hal_types.h:137–147` | The configuration accepts a caller-provided `uint16_t dead_time_ns`, pins and complementary flag. No default is embedded here. |
| `firmware/components/hal/esp32/hal_pwm_esp32.c:25–26,86–90,178–198` | Requests 80 MHz timer resolution (nominal 12.5 ns ticks). Initialization accepts 0–65535 ns; positive delay is floored to `floor(ns × 80 / 1000)` ticks. Zero bypasses the setup block. No 500 ns initialization clamp. |
| Same HAL, `:274–310` | Runtime setter clamps requests below 500 ns to 500 ns, then uses the same tick arithmetic. No production caller was found. This is a request clamp, not a successful waveform guarantee. |
| `firmware/components/safety/include/pwm_guard.h:28–29`, `pwm_guard.c:71–102,124–135` | Accepts stored state in 300–1000 ns; reads `get_state`, not two-channel edge timing. CRC checks stored configuration; frequency capture does not measure dead time. No production guard-init caller was found. |
| `firmware/test/CMakeLists.txt:39`, `test_common.h:63–65`, `test_pwm_guard.c:34,58` | 500 ns is also a test define/mock-state value. It is not a target configuration. |
| `firmware/sdkconfig.defaults:21–23`, `firmware/config.yaml`, `config.h`, `config.c` | MCPWM options concern IRAM; these files supply no PWM dead-time setting. |

The nominal requested-delay arithmetic gives 300→300 ns, 307→300 ns, 348→337.5 ns, 500→500 ns, and 65535→65525 ns. The script also exercises zero and the tick boundary. Integer conversion can shorten a request by less than a tick. It does not establish clock tolerance, output-pad skew, valid pulse widths or a complementary gap. The config type admits the full range; successful SDK setup and meaningful pulses are narrower questions. ESP32-S3 SDK register validation accepts tick counts below 65536 (`source/mcpwm_ll-esp32s3-v5.3.h:53`, `source/mcpwm_gen-v5.3.c:322–323`), so the largest config request is not rejected by that particular range check.

### The two-generator setup does not implement the claimed dead time

The release workflow uses **`espressif/idf:release-v5.3`**, `.github/workflows/release-artifacts.yml:13–18`. It is a floating release-line tag, not a patch version, image digest, build receipt or flashed image identity. `firmware/CMakeLists.txt:30` imports the environment's `IDF_PATH`. Therefore no exact deployed SDK can be established from this tree. This review anchors the defect to official **v5.3** source, compatible with the declared release line, and does not claim it identified the SDK installed on a controller.

Official sources, fetched from Espressif's v5.3 tag and preserved verbatim with their Apache-2.0 license and hashes:

- [mcpwm_gen.c](https://github.com/espressif/esp-idf/blob/v5.3/components/esp_driver_mcpwm/src/mcpwm_gen.c#L318): local [snapshot](source/mcpwm_gen-v5.3.c).
- [ESP32-S3 mcpwm_ll.h](https://github.com/espressif/esp-idf/blob/v5.3/components/hal/esp32s3/include/hal/mcpwm_ll.h): local [snapshot](source/mcpwm_ll-esp32s3-v5.3.h).

`hal_pwm_esp32.c:153–176` first assigns opposite raw generator actions. Then `:180–186` requests **both** rising and falling delay resources for HS. On a fresh operator, with nonzero tick delay and otherwise successful calls, this claims both resources. `:192–193` requests both again using the independent LS generator as input, with output inversion. SDK `mcpwm_gen.c:330–356` rejects this with `ESP_ERR_INVALID_STATE`, before topology writes, because those resources belong to the HS generator. Applying both delays to an independent inverted generator is not equivalent to a shared source with separate edge delays.

The HAL only logs the initialization failure, saves the requested number, marks the channel initialized and returns `HAL_OK` (`:188–215`). Its start routine checks initialization and SDK timer calls, not dead-time configuration success (`:314–343`). A guard inspecting that saved state could accept 500 ns despite the failed setup. The setter instead returns `HAL_ERROR` after the LS failure (`:298–307`), but the successful HS change may already have happened; it has no rollback. Neither path proves a valid gap on both edges or either configured channel/group.

**This is a source-level conditional defect, not proof that the live board is emitting an unsafe waveform.** No production invocation was found. The first call changes shared delay topology; the second call does not simply leave an independently ideal LS path. No signed HS/LS gap is assigned to that partial topology without a TRM-level proof and a pin measurement. The script's resource-guard translation demonstrates the rejection conditions, not the post-failure waveform.

## Board path and missing controller identity

Frozen netlist `zapote/power-stage-120v/frozen/default.net:1468–1479` gives:

| Leg | Input | Power-board net | Complete net membership |
| --- | --- | --- | --- |
| A | INA / HS | `pwm_ha` | J4.5 → U1.1 |
| A | INB / LS | `pwm_la` | J4.6 → U1.2 |
| B | INA / HS | `pwm_hb` | J4.7 → U2.1 |
| B | INB / LS | `pwm_lb` | J4.8 → U2.2 |

There are no discrete buffers, isolators, level shifters, series resistors or shunt capacitors on those four frozen input nets. Isolation is inside each UCC21550, already accounted for by its propagation specification. No separate component propagation time can be stacked for this board segment. This does **not** mean trace/cable/pad threshold skew is zero.

`firmware/components/hal/include/temper_pins.h:7–8,27–31` explicitly calls its GPIO mapping provisional and names only GPIO4/5 for one half bridge. It supplies no binding of four outputs to this board's J4. `validation-plan/06-controller-interface.md`, “Counterparts to find” and check 7, requests that cross-board validation; it is not a completed controller schematic or harness timing certificate. Neither the frozen power-board netlist nor the searched `zapote/ports.toml` / `project.toml` establishes the ESP32-to-J4 cable, controller components, pad skew or a full-bridge firmware configuration. Their min/max delays and skew remain **unknown**, not zero and not borrowed from the older monolithic board.

## Driver timing and the calculation boundary

TI **UCC21550 SLUSE89C, revised August 2024**, [official datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), repository `datasheets/ucc21550.pdf`:

- Pages 25–26, §7.4.2.2 / Figure 7-4: the opposite falling input starts the interlock timer. A later turn-on waits only for its remainder; a longer input gap dominates. Both-high inputs suppress both outputs. Programmed dead time is not added wholesale to an existing gap.
- Page 10, §5.9: rise/fall propagation 26/33/45 ns min/typ/max, same-edge channel mismatch ≤6.5 ns at −40…−10 °C and ≤5 ns at −10…150 °C, same-channel pulse-width distortion ≤5 ns. These use DT disabled and the stated supply/load conditions.
- Page 10 explicitly measures tPDLH from input VIH to output 10%, and tPDHL from input VIL to output 90%. Figure 6-1 on page 18 draws ideal vertical edges and does not specify 50% crossings; it must not be used to replace the table definitions. Figure 6-3 also marks 10%/90%. This calculation follows the electrical table, consistent with the DTS definition in Figure 6-4 (page 19) and §8.2.2.8 (page 33).
- Page 10, §5.8 has guaranteed DTS rows at 10/20/50 kΩ, none at fitted 39 kΩ. D1's interpolation is not a production bound.

For an input-dominated interval **using the page-10 table convention**, define `F_HL` and `F_LH` as controller gaps referenced to the receiving input VIL/VIH levels, and `P` as each external path's corresponding threshold-crossing delay:

```
O_HL = F_HL + P_L_rise - P_H_fall + tPDLH_L - tPDHL_H
O_LH = F_LH + P_H_rise - P_L_fall + tPDLH_H - tPDHL_L
```

The conditional opposite-edge driver skew envelope is `min(45−26, tDM+tPWD)`: ±11.5 ns cold, ±10 ns warm. It needs both channel matching and pulse-width distortion; subtracting only same-edge mismatch is insufficient. At the rated test conditions it bounds the input-dominated propagation contribution, not the loaded board's DTS.

| Explicitly hypothetical input case | Edge, either leg | Output DTS, cold | Output DTS, warm |
| --- | --- | --- | --- |
| Correctly generated 500 ns VIL-to-VIH gap at INA/INB; zero external skew; nominal clock; no interlock extension | HS-off→LS-on | 488.5–511.5 ns | 490–510 ns |
| Same assumptions | LS-off→HS-on | 488.5–511.5 ns | 490–510 ns |

These numbers are generated by the script and are **not actual board limits**. For a known input interval `[Fmin,Fmax]` and bounded external skew `[Smin,Smax]`, replace them with `[Fmin+Smin−K, Fmax+Smax+K]`, where `K` is the applicable driver bound. Here neither the firmware interval nor `S` is known.

D1's driver-dominated **90%-to-10% DTS estimate**, independently recalculated from D1's committed constants and TI table, is **307.185–391.220 ns**, nominal fit **348.4 ns**. Its resistance interpolation, load/supply and temperature qualifications remain in [D1](../out-D1/README.md). That estimate is not improved by subtracting channel mismatch again: DTS is already an output-to-output specification.

Under that explicit table convention, an illustrative longer-of-input-and-interlock stack is `[max(488.5,307.185), max(511.5,391.220)] = [488.5,511.5] ns` in the cold band. It combines a hypothetical correct input gap and D1's estimated floor; it is **not an actual-board bound**. The example explains why a verified controller interval could eventually remove the short corner, without claiming one exists here. With the actual missing `F` and `P`, the necessary stack cannot be closed. Measurements at 50% crossings would need transition-time corrections before comparison with this table convention.

MOSFET threshold crossings, channel conduction and diode recovery introduce further gate-network and operating-point dependence. The D2 control-ramp parameter is not automatically the measured output interval. No finite worst-case gate/conduction interval follows from this static review.

| Actual board result | HS-off→LS-on | LS-off→HS-on |
| --- | --- | --- |
| U1 output DTS min/max | Unestablished | Unestablished |
| U2 output DTS min/max | Unestablished | Unestablished |
| MOSFET gate/conduction min/max | Unestablished | Unestablished |
| Can <348 ns, including the 307 ns D2 corner, be excluded? | No | No |

## D8 handback and closure evidence

Before power switching, bind the flashed firmware hash, SDK image/version, full-bridge config and cable pin mapping. Check API results and both directional input/output waveforms; do not accept `get_state()` or an initialization log as measurement. On each leg capture outgoing INA/INB falling and incoming INA/INB rising, OUTA/OUTB relative to their own VSS at both 50% and DTS 90%/10%, and both transistor VGS relative to the transistor sources. Preserve simultaneous timestamps and probe deskew. Measure both directions at startup and after runtime changes; verify enable/disable behavior separately. Obtain the fitted-resistance timing guarantee and loaded timing evidence before replacing stress corners. No claim about a safe energized bench setup follows from this static review.

## Replay and publishing validation

From repository root:

```sh
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D5/gate_dead_time.py
```

Compare with `gate_dead_time.txt`, permitting only the Python runtime line to differ. Input drift fails closed. SDK sources can be refetched from the exact tag URLs above and checked against `input-hashes.json`; no network is required to replay. No firmware, Rust, native bridge, or workspace build ran.

Publishing checks: the import boundary gate runs in a private minimal `.venv` with `import-linter` and PyYAML (no workspace synchronization); `python3 scripts/regen_derived.py --check` checks derived outputs without modifying source. Both checks passed: `import-check.txt` reports 5 contracts kept, 0 broken and 0 new violations; `regen-check.txt` reports all derived artifacts consistent. No firmware manifest, board, or upstream round17 artifact changed. Review authored by GPT-6 Astra / OpenAI.
