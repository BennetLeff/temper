**No minimum or maximum is established for either HS-off→LS-on or LS-off→HS-on on U1/U2 in this snapshot; the firmware does not establish ≥500 ns, and dead time below 348 ns remains possible rather than excluded.**

## Method and decision

Read-only audit at `f9b13b483d6d4ed52439d4da419c7670bab6966c`, including the application, ESP32 HAL, guard, configuration, frozen netlist/BOM and native-17 pad assignments. [gate_dead_time.py](gate_dead_time.py) checks cited repository inputs against that revision, hashes them, audits production C sources, verifies the four board input nets, and calculates the conditional timing table. [gate_dead_time.txt](gate_dead_time.txt) is its complete Python 3.12 output. No firmware, board, existing result, Rust workspace or native bridge was changed or built.

This closes the **audit**, not F1 or physical qualification. Keep the 307 ns and existing shorter stress cases. A supplied production firmware binary/configuration and a measured four-PWM interface are required before claiming an input timing floor. The HAL findings below warrant a firmware-owner follow-up before using this implementation to drive the new bridge.

## Firmware findings

All file:line references in this section are at the source revision above; lines are also emitted in the evidence output.

| Source | What it establishes |
| --- | --- |
| `firmware/main/main.c:141`, `:153–154` | Calls `hal_init()`, but MCPWM initialization is commented out. |
| `firmware/components/hal/esp32/hal_init.c:65` | Installs the PWM operations pointer; does not initialize a PWM channel. The production C scan finds no call through `hal_pwm->init` or `hal_pwm->set_dead_time`, nor an application `hal_pwm_config_t` instance; the sole instance is internal HAL storage. This is a snapshot finding, not a claim about externally supplied binaries or other branches. |
| `firmware/components/hal/include/hal_types.h:143` | `dead_time_ns` is unsigned 16-bit: 0–65535 ns. No default is defined here. |
| `firmware/components/hal/esp32/hal_pwm_esp32.c:26`, `:84–88`, `:181–182` | Requested timer resolution 80 MHz, hence nominal 12.5 ns/tick. Integer conversion is `floor(ns × 80 / 1000)`; it rounds down, never up. Clock tolerance is not supplied. |
| Same HAL `:156–198` | Dead-time programming runs only for a complementary configuration with a low pin and positive request. Initialization imposes **no 500 ns floor**. A zero request bypasses it; 1–12 ns requests round to zero ticks. |
| Same HAL `:274–309` | Only the separate setter clamps requests below 500 ns. The setter can return an error after updating high-side hardware but before updating low-side hardware/cached state. |
| `firmware/components/safety/include/pwm_guard.h:28–29`; `pwm_guard.c:93–100`; HAL `:402–416` | Guard accepts cached 300–1000 ns. `get_state` copies software state; it does not measure either output or read back MCPWM dead-time registers. The guard therefore cannot detect a failed delay configuration. |
| `firmware/config.yaml`, generated `config.h`, `sdkconfig.defaults:21–23` | No power-stage dead-time setting. sdkconfig selects IRAM options for MCPWM, not edge delay. The tracked firmware tree contains no Kconfig dead-time owner. |
| `firmware/test/CMakeLists.txt:39`, `firmware/test/test_common.h:64`, `firmware/test/test_pwm_guard.c:34` | 500 ns occurs in host test definitions/mock state. It is not a production configuration. |
| `firmware/components/hal/include/temper_pins.h:27–30`; `elec/src/modules.ato:3580–3581`; `elec/src/main.ato:808–811` | Existing half-bridge firmware/source names GPIO4/5, PWM_HS/PWM_LS. No binding from that pair to the new board's four J4 PWM inputs is demonstrated by these sources. D-10 owns the complete interface audit. |

### P1: dead-time hardware is configured incompatibly with ESP-IDF

The release workflow selects `espressif/idf:release-v5.3` (`.github/workflows/release-artifacts.yml:13`); this tag is not a pinned SDK patch revision. The official [ESP-IDF v5.3 implementation](https://github.com/espressif/esp-idf/blob/v5.3/components/esp_driver_mcpwm/src/mcpwm_gen.c#L318-L395) rejects reuse of either edge-delay block by another generator before applying that second configuration (`:329–357`). The [ESP32-S3 API documentation, Dead Time section](https://docs.espressif.com/projects/esp-idf/en/v5.3/esp32s3/api-reference/peripherals/mcpwm.html#dead-time) describes the same hardware restriction. Download identities and verification command are in [sdk-source.txt](sdk-source.txt).

The HAL first makes high and low generators complementary with timer/compare actions (`:151–176`). It then requests **both** rising- and falling-edge delay on high (`:180–186`), followed by both blocks again on low (`:192–193`). For a nonzero tick request, the latter conflicts with ownership established by the former. Both init failures are merely logged; initialization subsequently stores the requested ns and returns `HAL_OK` (`:187–214`). Thus the 500 ns comment and even a successful guard result do not prove a 500 ns complementary waveform.

The low request also sets `invert_output=true` after the low generator was already programmed complementary. That is a second reason not to interpret the code comments as edge timing. Because the documented SDK rejects the conflicting call, this audit does **not** claim that the low output actually receives that inversion, nor infer a precise waveform from an unexecuted hardware configuration. Both edge delays on one signal delay that signal; they do not by themselves create equal blanking on both complementary transitions.

**Disposition:** firmware defect/integration gap, not a contradiction among native-17, its frozen netlist and TI pin definitions. No circuit correction is authorized or made. The firmware owner must supply the actual boot configuration, handle every MCPWM configuration error, verify a valid topology, and demonstrate both transitions on all four outputs. A host mock of `dead_time_ns` cannot establish this.

## Board signal path

The script compares the complete net memberships with native-17 pad assignments, and stops on disagreement:

| Leg/input | Exact frozen net | Endpoints | Intervening fitted component |
| --- | --- | --- | --- |
| A high | `pwm_ha` | J4.5 → U1.1 INA | None |
| A low | `pwm_la` | J4.6 → U1.2 INB | None |
| B high | `pwm_hb` | J4.7 → U2.1 INA | None |
| B low | `pwm_lb` | J4.8 → U2.2 INB | None |

Source: `frozen/default.net:1468–1479`, relative to `zapote/power-stage-120v/`. No isolator, buffer, level shifter or RC filter is fitted between **J4 and INA/INB**; isolation is internal to U1/U2. This means zero additional **component delay stages**, not zero physical delay. Copper, cable, connector, ESP32 GPIO edge rates and threshold-crossing skew are not timing-qualified by a connectivity netlist. The controller-to-J4 path and its min/max/skew are **UNKNOWN** here. Do not fill that gap with an assumed cable delay of zero.

## Driver timing and combination rule

Source: TI **UCC21550, SLUSE89C, revised August 2024**, committed `datasheets/ucc21550.pdf` and [official datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf). Printed page 10 §§5.8–5.9 gives:

| Parameter | Min / typical / max |
| --- | --- |
| INA/B→OUTA/B propagation, rising and falling | 26 / 33 / 45 ns |
| Same-edge channel mismatch, −40 to −10 °C | 0 / unspecified / 6.5 ns |
| Same-edge channel mismatch, −10 to +150 °C | 0 / unspecified / 5 ns |
| Per-channel pulse-width distortion | 0 / unspecified / 5 ns |

These are unloaded test-condition specifications: VCCI 3.3 or 5 V, VDD 12 V for the B variant, DT floating for the switching table, specified decoupling, 100 ns input pulses at 500 kHz. Native-17's gate load and operating supplies are not that test fixture; no loaded-gate min/max follows automatically.

An opposite-edge interval includes **channel mismatch plus pulse-width distortion**, not channel mismatch alone. For example,
`p(L,rise) − p(H,fall) = [p(L,rise) − p(H,rise)] + [p(H,rise) − p(H,fall)]`.
Its magnitude is bounded under those conditions by the smaller of the independent propagation span and that sum: `min(45−26, tDM+5)` = **11.5 ns cold / 10 ns warm**. The same reasoning applies to the reverse transition. A common 33 ns propagation delay cancels; it is not added twice.

Printed pp. 25–26 §7.4.2.2 / Figure 7-4 specify the **longer interval**, not the sum: an input falling edge starts the opposite channel's timer, and a later input turn-on can extend the gap. Both-high overlap forces both outputs low. This interlock does not make the invalid firmware topology a qualified PWM source.

[D-1](../out-D1/README.md) establishes R9/R17 = 39 kΩ ±1%, ±100 ppm/°C. TI's typical programming fit gives **348.4 ns**. D-1's full-temperature/resistor-tolerance interpolation gives **307.185–391.220 ns**, explicitly an **estimate**: TI publishes no guaranteed 39 kΩ min/max. Printed p. 19 Figure 6-4 / p. 33 §8.2.2.8 define DTS from falling OUT at 90% to rising opposite OUT at 10%. Since DTS is already an output interval, subtracting another channel-mismatch allowance from D-1's DTS estimates would double-count the output timing spread.

## Conditional calculation, both edges

For edge `Hoff→Lon`, write `FHL` for firmware non-overlap, `sHL` for the external path/threshold skew, and `δHL = p(L,rise)−p(H,fall)`. Define the reverse quantities analogously. In normal steady complementary operation:

```
GHL ≈ max(DHL, FHL + sHL + δHL)
GLH ≈ max(DLH, FLH + sLH + δLH)
```

This is the practical timing model implied by TI's longer-interval rule, not a new production specification at 39 kΩ. Given independently qualified interval limits, conservative interval arithmetic is `max(Dmin,Fmin+smin−δmax)` through `max(Dmax,Fmax+smax+δmax)`. The script emits each edge separately; symmetry below reflects identical assumed bounds, not measured channel equality.

| Scenario: actual INA/INB threshold gap, zero additional path skew | HS-off→LS-on, estimated min/max (ns) | LS-off→HS-on, estimated min/max (ns) |
| --- | --- | --- |
| 0 ns, full-temperature mismatch | 307.185 / 391.220 | 307.185 / 391.220 |
| 300 ns, full-temperature mismatch | 307.185 / 391.220 | 307.185 / 391.220 |
| 348 ns, full-temperature mismatch | 336.500 / 391.220 | 336.500 / 391.220 |
| 500 ns, full-temperature mismatch | 488.500 / 511.500 | 488.500 / 511.500 |
| 500 ns, −10 to +150 °C mismatch | 490.000 / 510.000 | 490.000 / 510.000 |
| Actual U1/U2 with this firmware snapshot | **UNKNOWN / UNKNOWN** | **UNKNOWN / UNKNOWN** |

The hypothetical 500 ns row shows why a **verified input gap** could remove the short-dead-time corner. It does not verify that input gap. Even then, a literal ≥500 ns **output** claim would need additional margin. U1 and U2 each follow these conditional equations; there is no published matching guarantee between separate driver ICs, and no bridge phase relationship is established here.

Requested ns are not necessarily the gap in that table: 307 ns converts to **300 ns**, 348 to **337.5 ns**, 391 to **387.5 ns**, and 500 to **500 ns** nominal timer delay. These are arithmetic outputs from the HAL conversion, not the resulting defective complementary waveform. The permitted 65535 ns input converts to 5242 ticks / 65525 ns; the official ESP32-S3 register limit is 65536 ticks exclusive (`mcpwm_ll.h:53`), but API range validity still does not guarantee useful pulses within a PWM period.

## Limits and owner decisions

- **Firmware owner:** identify the deployed binary, SDK commit, channel configuration and four-PWM harness assignment; fix the HAL delay ownership/error handling in a separate authorized change. D-5 is read-only.
- **Driver/timing owner:** obtain TI limits for the fitted 39 kΩ network at actual supply/load conditions, or qualify a controller-dominated timing budget including GPIO, threshold and cable skew.
- **Bench owner / D-8:** measure both directions on both legs, recording INA/INB threshold gaps, OUT 90%→10% gaps and actual MOSFET VGS turn-off/turn-on separately. Gate resistor/capacitance and Miller effects mean OUT dead time is not MOSFET threshold-crossing dead time. D-6 retains authority over the off-gate voltage criterion/remedies.
- No guaranteed board-wide maximum can be calculated while the operating waveform and path are unspecified. Stopped, faulted or missing pulses may have no next turn-on at all; the conditional table addresses ordinary switching only.

Rerun from repository root:

```sh
python3.12 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D5/gate_dead_time.py
```

Validation: the evidence output reproduced byte-for-byte; `git diff --check` passed. The isolated import-linter gate reported 5 contracts kept, 0 broken, and the read-only `regen_derived.py --check` reported all derived artifacts consistent. See [validation.txt](validation.txt) for exact commands. Mutating `make regen` was not run because this brief permits writes only in its output folder; its report-only equivalent found no drift. Host firmware tests were not run because firmware was audited without changes.
