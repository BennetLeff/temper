# Firmware link triage: the 34 undefined symbols

**Status:** triage only. Nothing in this document was implemented, stubbed or
deleted. It is the input to whoever writes the peripheral layer.

**Tree:** branched from `b9b37ecc6` ("fix(firmware): make the ESP32-S3 build
configure and compile; gate it in CI").

## How this was produced (re-runnable)

```bash
# 1. Clean build in the pinned image (must run rm as root; docker writes
#    root-owned objects into build/).
docker run --rm -u 0 -v "$PWD":/w -w /w/firmware espressif/idf:release-v5.3 \
  bash -lc 'rm -rf build; . $IDF_PATH/export.sh >/dev/null 2>&1; idf.py build 2>&1' \
  > /tmp/clean-build.log

# 2. Ratchet verdict + counts.
python3 scripts/check_firmware_link.py --log /tmp/clean-build.log

# 3. Sim-code guard (needs xtensa nm, so run it inside the container).
docker run --rm -u 0 -v "$PWD":/w -v /tmp:/s -w /w espressif/idf:release-v5.3 \
  bash -lc '. $IDF_PATH/export.sh >/dev/null 2>&1; \
            python3 scripts/check_firmware_link.py --log /s/clean-build.log \
                    --check-sim-symbols firmware/build'

# 4. Per-symbol reference counts.
grep -o "undefined reference to \`[a-zA-Z_0-9]*'" /tmp/clean-build.log \
  | sed "s/.*\`//;s/'//" | sort | uniq -c | sort -rn
```

Result, reproduced independently of any prior summary:

* **34 distinct undefined symbols, 141 undefined references** — matches
  `.firmware-link-inventory` exactly; ratchet verdict **PASS**.
* Compile is clean: the only `error:` line in the whole log is
  `collect2: error: ld returned 1 exit status`. Seven `-Wunused` /
  `-Wdeprecated` warnings, no `-Werror` trips.
* Sim-code guard: **no** `sim_state` / `*_sim_*` symbol is defined in the image.
* Components silently excluded for want of a `CMakeLists.txt`: `sensors`,
  `testing` — both on the allow-list with reasons recorded in `b9b37ecc6`.

Source line numbers below are from `grep` on the source, not from `ld`. The
linker attributes some references to the literal-pool line of the enclosing
function (e.g. it reports `state_machine.c:264` for the over-temperature
branch that actually lives at line 391), so `ld`'s numbers are not citable.

## Counts by disposition

| Disposition | Count |
|---|---|
| Mechanical | 2 |
| Needs a design decision | 12 |
| Needs hardware that does not exist | 17 |
| Should not exist | 3 |
| **Total** | **34** |

---

## Correction to the received brief

The brief states that `trigger_hardware_shutdown`, `watchdog_hardware_*` and
`safety_wdt_init` "are all in the missing set". **They are not.** All four are
defined in `firmware/components/safety/safety.c` (`safety_wdt_init` :138,
`trigger_hardware_shutdown` :440, `watchdog_hardware_init` :462,
`watchdog_hardware_feed` :505) and link successfully now that
`components/safety/CMakeLists.txt` exists. They do not appear in the link
failure or in the ledger. Only `pwm_disable_all` and `power_set_level` — the
two calls *inside* `trigger_hardware_shutdown` — are missing.

This matters for severity: `assert_hardware_fault_cut()`
(`state_machine.c:110-116`) asserts `RUNAWAY_CUT_GPIO` (GPIO15, configured by
`watchdog_hardware_init()` at `safety.c:485-494`) **before** calling
`trigger_hardware_shutdown()`. The hardware latch is therefore set on the way
into every software fault regardless of the two missing symbols.

---

## Safety-relevant subset, with hardware-backstop status

Established and re-verified: OCP-01 (TLV3201, 1:100 CT into 4.99 Ω burden,
~50.1 A) and THM-01/THM-02 feed a combinational chain into a set-dominant SR
latch and thence to the gate driver `DIS` pin, with no MCU in the path.
`RTD_HW_FAULT` from the MAX31865 also enters that chain
(`elec/src/main.ato:846`).

| Symbol | Trip it gates | Software threshold | Hardware backstop | Band lost if absent |
|---|---|---|---|---|
| `read_dc_bus_current` | `FAULT_IGBT_SHORT` (`state_machine.c:400`) | 50.0 A | **Yes** — OCP-01 ~50.1 A | ~nil; hardware trips at essentially the same point |
| `read_dc_bus_current` | `FAULT_OVER_CURRENT` (`state_machine.c:404`) | 40.0 A | **Partial** — OCP-01 ~50.1 A | **40–50 A is unprotected** |
| `read_heatsink_temperature` | `FAULT_OVER_TEMP` (`state_machine.c:391`) | 80.0 °C | **Partial** — THM-01 85 °C | **80–85 °C is unprotected** |
| `read_heatsink_temperature` | fault-clear gate (`state_machine.c:521`), FAULT-state re-trip (`state_handlers.c:635`) | 70 °C / 125 °C | THM-01 release 69.8 °C | clear-permission logic only |
| `read_rtd_resistance` | `FAULT_PROBE_OPEN` / `FAULT_PROBE_SHORT` (`state_machine.c:416-430`) | 300 Ω / 10 Ω / 10 kΩ | **Partial** — MAX31865 device fault → `RTD_HW_FAULT` → latch | firmware-threshold layer only; device open/short still latches |
| `read_pan_temperature` | `FAULT_RUNAWAY_BOUNDARY` (`state_machine.c:466,477`) | 300 °C abs, 15 °C/s rate | **None** — THM-02 senses the *coil*, not the pan | **entire runaway boundary** |
| `read_pan_temperature` | `FAULT_ADC_STUCK` (`state_machine.c:435-448`) | 49 identical reads | **None** | **entire stuck-sensor detection** |
| `is_fan_running` | `FAULT_FAN_FAILURE` (`state_machine.c:410`) | boolean | **Indirect only** — a dead fan eventually trips THM-01 at 85 °C | direct annunciation; thermal consequence is caught late |
| `get_time_ms` | rate term of the runaway check | — | **None** | a wrong time unit silently rescales the 15 °C/s trip |
| `g_config` | supplies both runaway limits | — | **None** | see the trap below |
| `pwm_disable_all`, `power_set_level` | shutdown *response* in `trigger_hardware_shutdown` (`safety.c:444,445`) and `enter_safe_mode` (`safety.c:221,222`) | — | **Yes** — `RUNAWAY_CUT_GPIO` is asserted first | software follow-through only |
| `test_hardware_comparators` | POST of the latch chain (`state_machine.c:333`) | — | n/a (it *is* the test) | no boot-time proof the latch works |

### Two findings that change the severity picture

**1. The software trips are the tighter ones.** `OVER_CURRENT_THRESHOLD` is
40 A against a ~50 A comparator, and `OVER_TEMP_THRESHOLD` is 80 °C against an
85 °C comparator (`firmware/config.h:282-284`). The missing software layer is
not merely redundant annunciation over an identical hardware trip — it is the
only thing covering 40–50 A and 80–85 °C. Anyone tempted to deprioritise these
on "the hardware catches it" should read that row first.

**2. DC-bus undervoltage has no protection of either kind.** Confirmed: no
undervoltage fault code exists in `fault_list_generated.h`, no symbol in the
missing set would implement one, and the two UVLOs are unrelated (gate-drive
silicon's 12 V rail; a TPS3700 on the 3.3 V logic rail). `V_BUS_SENSE` is
routed to `mcu.adc_v_bus` (`main.ato:870-871`, `PIN_ADC_VOLTAGE 2`) and is read
by nothing. This is a gap in the *design*, not in the link — implementing all
34 symbols would not close it.

### Where the software protection actually runs

`check_safety_interlocks()` is called from exactly two sites:
`state_handlers.c:298` (`state_preheat_update`) and `:402`
(`state_heating_update`). It is **not** called from `state_machine_update()`.

`safety.c`'s own `check_hardware_interlocks()`, `check_sensors_valid()` and
`safety_check_all()` are **unreachable in the image**: `monitor_task()` in
`main.c:116` has `safety_monitor_update()` commented out and nothing else calls
them. This is proved, not inferred — with `-ffunction-sections --gc-sections`,
references from garbage-collected sections do not produce undefined-symbol
errors, and `safety.c`'s `read_dc_bus_current` call sites (`:261`, `:353`) do
**not** appear anywhere in the link failure, while its `check_boot_reason`
(reachable from `app_main`) and `trigger_hardware_shutdown` sites do. The same
mechanism explains why `hal_get_tick_ms` — referenced by `ntc_guard.c`,
`adc_guard.c` and `fan_guard.c`, and defined only in `firmware/test/` — is not
a 35th undefined symbol: the whole guard layer has zero callers and is
collected.

**A tested guard layer exists and is wired to nothing.** `adc_guard.c`,
`ntc_guard.c`, `fan_guard.c`, `coil_guard.c` and `pwm_guard.c` all compile into
the image and none of their entry points is called from `main/` or from any
other component. Several of them are close to what the missing symbols need.

---

## Full table

Reference counts are from the linker. "Sites" are grep-verified source lines.

### Mechanical (2)

| Symbol | Refs | Call sites | What it must do | Path |
|---|---|---|---|---|
| `get_time_ms` | 8 | `state_machine.c:205,211,359,457,503,558`; `state_handlers.c:206,354,605,662`; `low_temp_control.c:46,53` | free-running millisecond counter, `uint32_t`, wrap-tolerant (all consumers use `now - then`) | `HAL_TIMER_GET_TIME_MS()` (`hal_timer.h:164`) is already wired by `hal_init()` (`hal_init.c:63`), which `app_main` calls. Or `esp_timer_get_time()/1000`. No hardware needed, no decision. |
| `g_config` | 1 | `state_machine.c:466,477` | supply `runaway.max_absolute_temp_c` and `runaway.max_temp_rise_rate_c_per_s` | `config_t g_config;` is defined at `firmware/config.c:20`; the file is in **no** component's `SRCS`. Adding `"../config.c"` to `main/CMakeLists.txt` links it. |

**`g_config` carries a trap — do not land the one-line CMake fix alone.**
`config.c:20` is a tentative definition with no initialiser, so `g_config`
lands in `.bss` zero-filled, and `config_init()` (`config.c:27`) is **called
from nowhere in the tree**. Linking it as-is gives
`max_absolute_temp_c == 0.0f`, so `check_runaway_boundary()` — which runs at
the very top of `state_machine_update()`, before all state logic — trips on the
first `read_pan_temperature()` above 0 °C, i.e. immediately at room
temperature. `FAULT_RUNAWAY_BOUNDARY` is unclearable (`fault_cleared()` returns
`false` for it) and `transition_to()` blocks every transition out of
`STATE_RUNAWAY_FAULT`. The board would brick itself on boot. The fix must add
`config_init()` to `app_main` in the same commit. The intended defaults are
300 °C / 15 °C·s⁻¹ (`config.h:137-140`).

### Needs a design decision (12)

The sensor and power symbols are grouped by the decision that unblocks them.

**Decision D1 — sensor-fault return contract.** *Owner: whoever signs the IEC
60335-1 safety case, not a firmware agent.* Every one of the four reads below
returns a bare `float` with no error channel. What does a read return when the
ADC is not configured, when SPI times out, when the value is out of physical
range? `safety.c` guards with `isfinite()` in its (unreachable) checks;
`state_machine.c:391,400,404` do **not** — a NaN there compares false against
every threshold and silently disables the trip. Deciding this once unblocks all
four. It is a safety decision, not a coding one.

| Symbol | Refs | Trip sites | Hardware | HAL | What is actually missing |
|---|---|---|---|---|---|
| `read_heatsink_temperature` | 7 | `state_machine.c:391,521`; `state_handlers.c:165,548,563,635` | **Exists.** `safety.ntc_sense.line ~ mcu.adc_ntc` (`main.ato:868`) → `PIN_ADC_NTC 3` / `ADC_CHANNEL_NTC` (`ADC_CHANNEL_2`). Divider is VCC → 10 kΩ ±1% → sense → NTC → GND, `V_sense` 3.000 V @25 °C, 1.607 V @85 °C, 0.828 V @120 °C (`modules.ato:2474-2492`). | **Exists.** `hal_adc_esp32.c` implements oneshot + calibration; `hal_adc` is wired by `hal_init()`. | Nothing under `firmware/main/` references the ADC HAL — **confirmed**. Also: `esp32_adc_init()` must be called per channel and is called by nobody, so `HAL_ADC_READ_RAW` would hit an unconfigured unit. **And see the ntc_guard defect below.** |
| `read_dc_bus_current` | 3 | `state_machine.c:400,404` | **Exists but is not DC.** `I_SENSE` is the CT secondary across a 4.99 Ω burden with a 100 nF C0G filter (`main.ato:833` → `mcu.adc_i_sense` → `PIN_ADC_CURRENT 1` / `ADC_CHANNEL_0`). This is the **tank return current at 25–50 kHz**, not DC-bus current, despite the symbol name. | **Exists**, same as above. | A single `adc_oneshot_read()` on a 25–50 kHz waveform from a 100 Hz loop returns an aliased instantaneous sample, not a magnitude. Needs a sampling strategy (peak-hold, synchronous sampling, or continuous-mode + RMS) before any 40 A / 50 A comparison means anything. **This is why it is not mechanical.** |
| `read_rtd_resistance` | 3 | `state_machine.c:416,528` | **Exists.** MAX31865 + PT100, SPI2, bootstrapped by `rtd_service_bootstrap()` from `app_main`. | Partial. | `max31865.c` reads **only** the fault-status register (0x07). It never reads the RTD data registers, and `max31865.h` does not even define them (only 0x00/0x03/0x05/0x07). No `R_ref`, no resistance conversion. A new register read plus a scaling constant is required. |
| `read_pan_temperature` | 7 | `state_machine.c:435,456,502`; `state_handlers.c:193,205,272,353` | **Exists** — same MAX31865/PT100 as above (`rtd_pan`). | Partial. | Same gap, plus a PT100 resistance→°C conversion (Callendar–Van Dusen or a linearisation) that exists nowhere in the tree. |

**Observation for the hardware owner, not a firmware item.** The CT bias
network (`modules.ato`, `CurrentSensing`) is documented as "1.65 V mid-rail for
bipolar CT output" via a 10 k/10 k divider — but `r_burden` (4.99 Ω) sits
directly from `i_sense.line` to `i_sense.reference`, in parallel with
`r_bias_bot`. For DC the node therefore sits at
3.3 V × (4.99‖10 k)/(10 k + 4.99‖10 k) ≈ **1.6 mV**, not 1.65 V: the bias is
defeated by the burden. This is *consistent* with OCP-01 working as specified
(50 A peak → 2.495 V against a 2.49 V reference on positive half-cycles, no
bias needed), so it is not necessarily a defect — but it does mean an ADC read
of `I_SENSE` sees positive half-cycles only, clipped at ground. Someone in the
electrical domain should confirm the intent before the firmware conversion
constant is chosen. Flagged, not acted on.

**Concrete defect found in the existing NTC code.** `ntc_guard.c:15-18`
hardcodes `NTC_R25 10000.0f` / `NTC_B 3950.0f` for `NCU18XH103F6SRB`. The
schematic part is `NTCALUG01A104GA`: **R25 = 100 kΩ, B25/85 = 4190 K**
(`modules.ato:2459-2469`). The divider orientation and the 10 kΩ pull-up are
right; the thermistor constants are for a different part. At the 85 °C trip
point (`V_sense` 1.607 V, `r_ntc` ≈ 9.49 kΩ) the existing conversion returns
**≈26 °C**. Anyone who reaches for `ntc_guard_read_safe()` as the basis for
`read_heatsink_temperature()` will inherit this. Not fixed here — it sits on a
thermal protection path and the correction should land with a test. Separately,
`ADC_MAX_COUNTS 4095.0f` assumes 12-bit full-scale at the rail; the ESP32-S3
default attenuation in `hal_adc_esp32.c` is the deprecated `ADC_ATTEN_DB_11`
(~3.1 V usable), so the counts→volts constant needs deciding too.

**Decision D2 — who owns MCPWM0.** *Owner: firmware architect.* There are two
independent MCPWM owners in the tree: `hal_pwm_esp32.c` creates its own timer,
operator and generator pair for `HAL_PWM_CHANNEL_GATE`, while
`pll_control.c:184-185,249,261` expects an `mcpwm_timer_handle_t` to be
*injected* via `pll_set_timer()` / `pll_set_capture_channel()` — which nothing
calls. Until that is resolved, "implement `pwm_disable_all`" has no correct
answer. Unblocks 4 symbols (plus `test_pwm_generation`).

**Decision D3 — what a power "level" is.** *Owner: whoever owns the control
law.* `power_set_level(uint8_t)` is called with 0, 5, 10, `pid_output * 10`,
and a clamped PID output. Nothing in the tree defines level → duty, level →
frequency, or the relationship to `pwm_set_duty_cycle(uint8_t duty)`. Note
`state_handlers.c:386` computes `(uint8_t)(pid_output * 10)` with no clamp
before the cast.

| Symbol | Refs | Call sites | Notes |
|---|---|---|---|
| `pwm_disable_all` | 5 | `state_handlers.c:593,650`; `safety.c:221,444` | Must be the fastest path available and must not depend on the HAL being initialised — it runs from `check_boot_reason()` before much else. `hal_pwm->emergency_stop()` exists (`hal_pwm.h:108`). Blocked on D2. |
| `power_set_level` | 13 | `state_handlers.c:121,181,295,387,395,467,538,592,613,649`; `low_temp_control.c:85,93`; `safety.c:222,445` | Blocked on D2 + D3. Highest reference count of all 34. |
| `pwm_set_duty_cycle` | 3 | `state_handlers.c:120,539` | Both call sites pass 0. Relationship to `power_set_level(0)` — called on the adjacent line in both cases — is undefined. Blocked on D2 + D3. |
| `power_enable` | 2 | `state_handlers.c:251` | Single site, `state_preheat_entry`. Whether this means "close the inrush bypass relay" (`PIN_RELAY_BYPASS 19`, `RELAY_CTRL`) or "start the gate PWM" is not written down anywhere. Blocked on D3. |

**Decision D4 — what the POST is allowed to do.** *Owner: safety case owner.*
`run_self_test()` (`state_machine.c:325-345`) is a hard gate: `state_init_entry`
runs it and any failure is terminal. Four of the seven have real hardware.

| Symbol | Refs | Hardware / existing code | Decision required |
|---|---|---|---|
| `test_adc_calibration` | 2 | 3 ADC1 channels exist; `esp32_adc_calibrate()` implemented (`hal_adc_esp32.c:180`); `adc_guard.c` implements stuck/range/variance detection and is unused | What is "calibrated"? A successful `adc_cali` handle, or a plausibility check against a known node? |
| `test_pwm_generation` | 2 | `pwm_guard_self_test()` (`pwm_guard.c:70`) and `pwm_guard_check_integrity()` (`:105`) already exist and are called by nothing | Wire the existing guard, or write a new test? Blocked on D2. |
| `test_hardware_comparators` | 2 | The MCU **can** exercise the latch: `runaway_cut` (GPIO15) sets it, `fault_status_in` (GPIO20, `main.ato:902`) senses it, `reset_n` (GPIO14) resets it | Is deliberately firing the safety latch at every boot acceptable? This is the only symbol that would give boot-time proof the protection chain is alive. Genuinely a safety-case call. |
| `test_rtd_sensor` | 2 | `max31865_start_fault_detection()` / `max31865_service_fault_cycle()` exist and run every control tick | Does POST wait for one fault-detection cycle, or is the running service sufficient? |
| `led_set_pattern` | 9 | GPIO17/18 reserved in `temper_pins.h`; but `modules.ato:3447`: "LED indicators remain unassigned until their current-limiting circuits are specified; they must not be used as safety logic." | Also needs hardware — see below. |

### Needs hardware that does not exist (17)

Nothing in `elec/src/*.ato` instantiates a buzzer, a display, an EEPROM, user
buttons, indicator LEDs, a fan driver or a fan tachometer. Searched
`main.ato`, `modules.ato` and `components.ato` for each. These are not
firmware tasks.

| Group | Symbols | Refs | What exists | What would be required |
|---|---|---|---|---|
| **Fan** | `is_fan_running`, `fan_set_speed`, `fan_set_auto_mode`, `test_fan_operation` | 4+5+2+2 = 13 | `modules.ato:1627-1660`: a Sunon MF60251V1 on flying leads to a 2-pin header `J_FAN`, fed from the 15 V rail through a fixed 39 Ω 1 W dropper. **No switch, no driver, no PWM, no tachometer.** The fan runs whenever the 15 V rail is up. `HAL_PWM_CHANNEL_FAN` exists in `hal_pwm.h:29` with no hardware behind it. | Speed control: a low-side FET plus a gate resistor and a PWM pin. Fan-failure detection: a 3-wire fan and a tach input with a pull-up — or drop `is_fan_running` and rely on THM-01. The latter is a documented safety-case position, not a default. |
| **Display** | `display_show_message`, `display_update_temperature`, `display_update_countdown`, `display_show_fault`, `test_display_communication` | 12+6+2+2+2 = 24 | `main.ato:533-534` declares two bare signals `i2c_sda_ui` / `i2c_scl_ui`, commented "I2C expansion header for UI", connected to `mcu.i2c` (GPIO38/39) and to **nothing else — not even a connector footprint**. `temper_pins.h` marks I2C "Optional - for future expansion". | A display module, a connector, isolation (the comment mentions an ADUM1250 that is not instantiated), and a decision on what a cooktop with no display does with 12 `display_show_message()` calls. |
| **Buttons** | `button_is_pressed`, `button_set_enabled` | 12+3 = 15 | Only `PIN_BUTTON_RESET 0` — GPIO0, the boot strap, flagged "use with care". The only tactile part in the design is `components.ato:741`, "boot/reset strap access". `BUTTON_START`, `BUTTON_STOP`, `BUTTON_TEMP_UP`, `BUTTON_TEMP_DOWN` have no hardware at all. | Four more buttons with debounce hardware or a UI board on the I2C expansion. Note `BUTTON_STOP` appears at `state_handlers.c:236,309,427,523` — this is the user's stop control, and it does not exist. |
| **Buzzer** | `buzzer_beep`, `buzzer_beep_continuous`, `buzzer_stop` | 5+2+3 = 10 | Nothing. No pin in `temper_pins.h`, no part in `elec/`. | A magnetic or piezo transducer plus a drive transistor and a pin. Relevant to IEC 60335-1 audible-annunciation expectations — worth checking whether the standard requires it before deciding to delete. |
| **EEPROM** | `eeprom_log_fault`, `test_eeprom_read` | 2+2 = 4 | Nothing. No I²C/SPI EEPROM in the design. However `partitions.csv` (added in `b9b37ecc6`) provides an `nvs` partition and `app_main` already calls `nvs_flash_init()`. | Either add an EEPROM, or reimplement fault logging on NVS. The second is cheap and needs no hardware — but it is a rename, and someone must decide whether fault history must survive a flash erase. |
| **LEDs** | `led_set_pattern` | 9 | GPIO17/18 reserved as `PIN_LED_FAULT` / `PIN_LED_POWER`, but `modules.ato:3447` records the indicators as deliberately unassigned pending current-limiting circuits. | Two LEDs and two resistors — the cheapest hardware gap here. Then a decision: the code uses **five** patterns (`LED_BLINK_FAST`, `LED_BLINK_SLOW`, `LED_STEADY_GREEN`, `LED_STEADY_ORANGE`, `LED_FAULT`) over **two** single-colour indicators. `LED_STEADY_GREEN` and `LED_STEADY_ORANGE` imply a bi-colour part that is not in the BOM. |

### Should not exist (3)

| Symbol | Refs | Call site | Why | What the state machine does without it |
|---|---|---|---|---|
| `peripherals_init` | 2 | `state_handlers.c:88`, `state_init_entry` | **Duplicate.** `app_main` already calls its own static `init_peripherals()` (`main.c:138-166`) — HAL init, RTD bootstrap — *before* `state_machine_init()`, which is what drives `transition_to(STATE_INIT)` and hence `state_init_entry()`. So this is a second initialisation pass over already-initialised peripherals. | `state_init_entry()` would still do `thermal_mass_init()`, set the LED pattern, show "SELF TEST" and extend the watchdog timeout; `state_init_update()` (`state_handlers.c:102-104`) still runs `run_self_test()`. Deleting the call loses nothing — **provided** everything `init_peripherals()` needs to cover is actually in `main.c`, which is only true once the ADC and PWM init that D1/D2 introduce land there. **Delete after those, not before.** |
| `peripherals_enter_low_power` | 2 | `state_handlers.c:134`, `state_idle_entry` | No low-power requirement exists anywhere in `docs/` or `config.yaml`, and no HAL supports it. Worse: ESP32-S3 light sleep would suspend the control task, which is the only thing feeding the TPS3823 external watchdog (`state_machine.c:220`) — a 1.6 s timeout followed by a reset and `enter_safe_mode()`. Any implementation is more likely to be a bug than a feature. | `state_idle_entry` would still zero the power level, set the fan to minimum, show "READY" and enable `BUTTON_START`. Nothing depends on the low-power call. Safe to delete, but it is a product decision (is standby power a requirement?) rather than a purely technical one. |
| `peripherals_exit_low_power` | 2 | `state_handlers.c:178`, `state_pan_det_entry` | Same; it is the paired wake. Deleting one without the other would be a latent bug. | Symmetric — delete as a pair or not at all. |

---

## Shape of the work

**Structure, not hours.**

* **2 mechanical**, and they are genuinely independent of everything else —
  `get_time_ms` needs one HAL call, `g_config` needs one `SRCS` line **plus**
  the `config_init()` call. They can land first and alone.
* **4 decisions gate 12 symbols**, and they nest:
  * **D1** (sensor-fault return contract) unblocks all 4 sensor reads at once
    — the single highest-leverage decision, and the only one that is
    unambiguously a safety-case call rather than an engineering one.
  * **D2** (MCPWM ownership) unblocks 4 power symbols **and** `test_pwm_generation`.
  * **D3** (level semantics) is needed by 4 of the same power symbols; it can
    be taken in parallel with D2 but not applied before it.
  * **D4** (POST scope) covers 4 self-tests and depends on D1 and D2 for two
    of them.
* **17 need hardware**, and they collapse into **one product question**: does
  this cooktop have a user interface? Answering it once disposes of the
  display (5), buttons (2), buzzer (3) and LEDs (1) — 11 symbols, 58 of the
  141 references. Fan (4) and EEPROM (2) are separate, smaller questions; the
  EEPROM one can be answered in firmware alone (NVS already exists).
* **3 should be deleted**, but two of them (`peripherals_init` and the
  low-power pair) should be deleted *after* D1/D2 land, not before, because
  `peripherals_init()` is the only hook where per-channel ADC and PWM
  initialisation would naturally go if the author decides not to put it in
  `main.c`.

**Can the mechanical ones land independently?** Yes, and they should — but note
that landing `g_config` *without* `read_pan_temperature` is harmless (the read
is still undefined, so nothing links), while landing it *with* a
`read_pan_temperature` implementation and *without* `config_init()` bricks the
board. The ordering constraint is real.

**Does any single decision unblock several?** Yes — D1 unblocks 4, D2 unblocks
5, and the UI product question disposes of 11. Three answers cover 20 of the
34.

## Where this triage cannot answer the question

Stated plainly rather than guessed:

* **`power_enable()`** — one call site, no documentation, two plausible
  meanings (close the inrush bypass relay vs. start the gate drive) with very
  different consequences if confused. **Unknown; needs the author.**
* **The `power_set_level` ↔ `pwm_set_duty_cycle` relationship** — both are
  called on adjacent lines at `state_handlers.c:120-121` and `:538-539`, both
  with 0. Whether one is meant to call the other, or they address different
  layers, is not recoverable from the source. **Unknown; needs the author.**
* **Whether `is_fan_running` should be implemented or deleted** — it has no
  hardware, and the thermal chain does eventually catch a dead fan. But
  deleting a fan-failure trip from a mains induction cooktop is an IEC
  60335-1 argument, not a refactor. **Needs the safety case owner.**
* **The intended `read_dc_bus_current` quantity** — the name says DC bus, the
  only sense element is a CT on the tank return. Whether the 40 A and 50 A
  thresholds were derived for RMS tank current, peak tank current, or an
  actual DC-bus measurement that was never built changes the conversion by a
  large factor. `docs/evidence/2026-08-15-firmware-interlock-citations.md`
  cites `config.yaml` for the numbers but not the quantity.
  **Needs whoever set the thresholds.**
