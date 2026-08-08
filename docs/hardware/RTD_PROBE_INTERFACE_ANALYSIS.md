# RTD Probe Interface — Missing Connector Analysis

**Date:** 2026-08-07
**Trigger:** `scripts/check_netlist_stage_checks.py` (merged from
`worktree-agent-aec4a46590b7d9ffa`), single-pin-net finding: `rtd_force_p`,
`rtd_force_n`, `rtd_sense_p`, `rtd_sense_n` each terminate at exactly one pin
(U9, the MAX31865) with nothing else on the net. Same finding for `usb_dn`/
`usb_dp` (U27, the ESP32-S3).
**Gates at risk:** PID-01, PID-02, PID-03, PID-04 (`docs/STRATEGY.md:109-112`).
**Verdict: real, not a false alarm.** No RTD probe connector exists anywhere
in `elec/src/*.ato`, the compiled netlist, or `pcb/temper.kicad_pcb`. All four
PID gates are unreachable on the current design as committed. USB is
independently confirmed vestigial — not a stalled feature, dead MCU-pin
wiring with no downstream consumer anywhere in the design or firmware.

---

## 1. What the RTD path is for

`RTDSensing` (`elec/src/modules.ato:1783-2082`, instantiated as `rtd_pan` in
`elec/src/main.ato:560`) is a MAX31865-based 4-wire PT100 interface. Its own
docstring calls it "MAX31865 RTD interface for PT100" and `main.ato:815`
labels the wiring block "RTD temperature sensing (**pan temperature**)".

This is a *process* sensor, not a *protection* sensor, and the firmware keeps
the two cleanly separate:

- `firmware/main/state_handlers.c` and `state_machine.c` call
  `read_pan_temperature()` for every PID computation
  (`state_handlers.c:205,272,353`: `float current_temp =
  read_pan_temperature(); ... pid_update(target_temperature, current_temp)`).
- Thermal protection instead calls `read_heatsink_temperature()`
  (`state_handlers.c:165,548,634`; `state_machine.c:391,518`), which is a
  distinct function reading a distinct sensor (`THM-01`, the heatsink NTC).
- The coil NTC (`THM-02`, `safety.coil_thermal` /
  `CoilThermalComparator`, `elec/src/modules.ato:1759-1849`) is not read by
  firmware **at all** — see §3.

`firmware/components/sensors/max31865.c` and `rtd_service.c` are a real,
non-stub production driver (SPI2 on GPIO8/11/12, CS10, DRDY on GPIO9,
100 ms silent-DRDY timeout, correct 15-bit threshold-register encoding — see
`docs/hardware/RTD_SAFETY_DUAL_PATH.md`). `docs/SENSOR_MOUNT_DESIGN.md`
documents a spring-loaded mechanical assembly ("Spring-Loaded Pan Sensor
Mount", REQ-MECH-01) whose entire purpose is to hold a PT100 element against
the underside of the cooktop glass for "accurate closed-loop temperature
control." So: **the RTD is the dedicated pan/food-temperature probe that
closes the PID loop**; the two NTCs are fixed-threshold hardware protection
sensors for the heatsink and coil respectively, structurally and functionally
unrelated to PID.

## 2. The external probe interface genuinely does not exist

Searched, in order:

1. **`elec/src/*.ato`.** `RTDSensing.adc.FORCE_P/FORCE_N/RTDIN_P/RTDIN_N`
   connect only to the module's own `rtd_force_p/n`, `rtd_sense_p/n` signals
   (`modules.ato:2079-2082`), which are wired straight through to `Top`-level
   signals of the same name in `main.ato` and never referenced again. The
   *only* connector instantiated anywhere in `elec/src` is a single 2-pin
   `PinHeader_1x02` for the fan (`j_fan`, `modules.ato:1672`). There is no
   `Connector`/`Header`/`JST` component tied to any `rtd_*` signal — confirmed
   by grep across `elec/src/*.ato` for `PT100`, `probe`, `Connector`,
   `Header`, `Terminal`, `JST`, `RTD_CONN`.
2. **Compiled netlist** (`elec/build/default.net`, rebuilt fresh for this
   analysis via `make netlist`). `rtd_force_p`, `rtd_force_n`, `rtd_sense_p`,
   `rtd_sense_n` are each a genuine single-pin net (`U9.12`, `U9.8`, `U9.11`,
   `U9.10`) — this is exactly what the netlist-stage check flagged, and it
   reproduces after a clean rebuild.
3. **`pcb/temper.kicad_pcb`.** No footprint matching `J_RTD`, `RTD1`, `RTD2`,
   or `B4B-XH` (the JST part named below) exists on the board.
4. **`docs/CONNECTORS_AND_WIRING.md`** (repo root, not `docs/hardware/`).
   This document *does* specify the intended connector — `J_RTD1` ("Pan
   Sensor", JST XH `B4B-XH-A`/`XHP-4`, 4-pin, pinned "Bias+/Sense+/Sense-/
   Bias-", which maps 1:1 onto MAX31865 `FORCE+`/`RTDIN+`/`RTDIN-`/`FORCE-`)
   and `J_RTD2` for the heatsink NTC. So **intent to add a connector is
   documented** — this is not an oversight nobody thought about. But the
   document is a target specification that the atopile source was never
   updated to match: none of its 8 listed connectors (`J_IN`, `J_COIL`,
   `J_RTD1`, `J_RTD2`, `J_PROG`, `J_UI`, `J_DEBUG`) appear in `elec/src`
   except `J_FAN`, and even that one is under-implemented relative to the
   doc (doc specifies a 4-pin Molex KK with tach/PWM; source instantiates a
   generic 2-pin header). The doc is aspirational/spec-stage, not as-built.
5. **`docs/SENSOR_MOUNT_DESIGN.md`** confirms the mechanical intent (a
   probe that presses against the glass and must be wired out) but contains
   no electrical connector detail — it is a mechanical spec, not evidence of
   an electrical termination.
6. **Independent corroboration already in the codebase.** Two places outside
   this analysis and outside the merged netlist-check branch had already
   found and recorded the same gap:
   - `docs/hardware/RTD_SAFETY_DUAL_PATH.md:292-299` ("Four-wire analogue
     connection"): *"`FORCE+`/`RTDIN+` and `FORCE-`/`RTDIN-` stay as separate
     conductors **to the RTD connector**"* — written as though the connector
     exists, but it doesn't; this line documents the intended topology, not
     built hardware.
   - `packages/temper-placer/tests/router_v6/test_routability_check.py:459-478`,
     a pre-existing code comment explaining why the routability test's
     `TEMP_SENSE` net-name anchor is deliberately left unmapped: *"all four
     RTD force/sense nets are single-pad on `pcb/temper.kicad_pcb` (no RTD
     probe connector is instantiated anywhere in `elec/src` — confirmed by
     grep)"* and, for USB, *"grepping `elec/src/*.ato` for a USB connector
     turns up none... That is a real design gap (no USB connector
     instantiated), not a mapping bug."* This predates the netlist-stage
     check and reaches the identical conclusion independently.

**Conclusion: not a false alarm.** The physical probe interface is
documented as intended (`CONNECTORS_AND_WIRING.md`'s `J_RTD1`) and even
named in prose as though present (`RTD_SAFETY_DUAL_PATH.md`), but was never
instantiated in the atopile source, the netlist, or the PCB. A user has
nothing to plug a PT100 probe into.

## 3. Consequence for PID-01 through PID-04

All four temperature-control gates (`docs/STRATEGY.md:109-112`,
`FUNCTIONAL_TEST_CRITERIA.md` §1.3) require closing a control loop against
"a calibrated reference" at specific setpoints (100°C steady-state, 60°C
hold, 25°C→100°C step). The firmware's only closed-loop temperature input is
`read_pan_temperature()`, which is the RTD path. With no external interface,
there is no way to attach a PT100 probe (or a calibrated reference
substitute) to the board — the signal genuinely dead-ends at the ADC IC's
pins. **PID-01, PID-02, PID-03, and PID-04 cannot be bench-measured on the
current board, regardless of firmware quality**, because the sensor input
they depend on has no physical access point. This is consistent with, and
gives a root cause for, `docs/STRATEGY.md:97`'s existing "zero of 22 gates
measured" honest-state note — for these four specifically, "not yet
measured" would currently mean "not measurable," not merely "not yet
scheduled."

### Could an NTC substitute?

No, for two independent reasons — either alone is sufficient:

**(a) Wrong measurand, wrong location.** Both NTCs sense component
temperature (heatsink, coil) for over-temperature shutdown, not pan/food
temperature. PID-01 requires ±2°C accuracy at 100°C measured against "a
calibrated reference" — i.e., accuracy of the *process variable itself*.
Heatsink or coil temperature has no fixed, characterizable relationship to
pan-surface temperature (it depends on load, duty cycle, ambient, thermal
mass, airflow); substituting one for the other doesn't approximately meet
the spec, it answers a different question.

**(b) Not electrically wireable as a substitute either way:**
- The heatsink NTC (`THM-01`) *is* digitized — `safety.ntc_sense.line ~
  mcu.adc_ntc` (`main.ato:851`) — but even if repurposed it would still fail
  (a), and it is already committed to protection duty (85°C trip / 70°C
  recovery, `FUNCTIONAL_TEST_CRITERIA.md` §2.3).
- The coil NTC (`THM-02`) is **not digitized at all**. `CoilThermalComparator`
  is a pure analog window-comparator circuit that only asserts a binary fault
  bit into `fault_any_or` (`modules.ato:1759-1849`); there is no
  `mcu.adc_*` connection to it anywhere in `main.ato`. Firmware has no way to
  read a coil-NTC value even for experimentation — there is no ADC path to
  read.
- The coil NTC additionally trips at 120.3°C against the
  `NTCALUG01A104GA` part's own +125°C maximum rating
  (`docs/hardware/BOM.md:430`) — a 4.7°C / **3.8%** margin. Even setting
  aside (a) and (b), running this sensor continuously near 100°C (close to
  its 120.3°C fixed trip and within single-digit percent of its absolute
  maximum rating) is not a sound basis for a precision ±2°C control loop.

**No NTC is a viable PID substitute, on measurand grounds alone; the
digitization and thermal-margin points are independent, reinforcing
reasons.**

## 4. USB (`usb_dn` / `usb_dp`) — briefer verdict: vestigial, not stalled

- `elec/src/modules.ato:3377-3379`: `usb_dn ~ mcu.IO19`, `usb_dp ~
  mcu.IO20` — comment says "native USB on GPIO19 = D-, GPIO20 = D+", wired
  straight from the MCU's native-USB-capable pins to `Top`-level signals in
  `main.ato:927-928`, and nowhere else.
- No connector: `docs/CONNECTORS_AND_WIRING.md`'s connector table has no USB
  entry at all — programming/service access is specified there as `J_PROG`,
  a UART header (2.54mm, FTDI-style pinout: GND/CTS/VCC/TXD/RXD/RTS), not
  USB. `mcu.TXD0`/`mcu.RXD0` (the UART path) are themselves wired
  (`modules.ato:3452-3453`) but also terminate as single-pin nets at the MCU
  (`rx`/`tx` in the check output) — `J_PROG` is documented but, like
  `J_RTD1`/`J_RTD2`, not instantiated in source either.
- No firmware consumer: `grep -rli usb firmware/` returns nothing. No USB
  stack, no TinyUSB/CDC config, no `config.yaml` entry, no documented flow
  (programming, service, or firmware update) depends on it.
- Independently confirmed dead by `test_routability_check.py:475-478`
  (quoted in §2.6): "a real design gap (no USB connector instantiated), not
  a mapping bug."

**Verdict:** vestigial MCU-pin wiring, not a stalled feature. The documented
service-access path is UART (`J_PROG`), which is itself unimplemented in
source (same pattern as `J_RTD1`/`J_RTD2`) but is at least the *intended*
mechanism per `CONNECTORS_AND_WIRING.md`. USB has no such documented role
anywhere and should not be treated as a gap blocking any gate — no gate
references it. Unlike the RTD finding, this does not gate release; it is
inert wiring that costs nothing to leave as-is, or can be removed if this
document's audit trail is preferred over silent inertness.

## 5. Recommendation

**Add the probe interface — do not re-scope PID-01..04.** The gates
correctly require a calibrated-reference-verifiable measurement; re-scoping
them to accept an NTC proxy would mean shipping a temperature-control claim
that cannot be honestly verified (per §3, no NTC answers the same physical
question). `docs/CONNECTORS_AND_WIRING.md` already specifies exactly what is
needed (`J_RTD1`: JST XH `B4B-XH-A` 4-pin, mating `XHP-4`) and even names the
correct pinout (Bias+/Sense+/Sense-/Bias- = MAX31865 `FORCE+`/`RTDIN+`/
`RTDIN-`/`FORCE-`) — this is implementation work against an existing spec,
not a new design decision:

1. Instantiate a 4-pin connector in `elec/src/modules.ato` (or a new
   sub-module) matching `CONNECTORS_AND_WIRING.md`'s `J_RTD1` spec, and wire
   `rtd_force_p`/`rtd_force_n`/`rtd_sense_p`/`rtd_sense_n` to it instead of
   leaving them as bare `Top`-level signals.
2. Re-run `make netlist && python3 scripts/check_netlist_stage_checks.py`
   to confirm the four RTD nets move from single-pin to multi-pin and drop
   out of the finding.
3. `docs/SENSOR_MOUNT_DESIGN.md`'s mechanical assembly (spring-loaded probe
   button) still needs a matching cable/connector on the sensor side — this
   is a BOM/harness item per `CONNECTORS_AND_WIRING.md` §3.3 ("Shielded
   Twisted Pair... 500mm max"), not a schematic one, and should be tracked
   alongside the schematic change so the two ends actually mate.
4. Leave USB unwired, or remove `usb_dn`/`usb_dp` if the project prefers an
   explicit "not implemented" over silent dead pins — neither choice affects
   any gate. Do not conflate its cleanup with the RTD work; they are
   unrelated in cause (RTD is a documented-but-unbuilt intent, USB has no
   documented intent at all) and in consequence (RTD blocks four gates, USB
   blocks none).

This document does not modify `elec/`, `pcb/`, `firmware/`, or
`docs/FUNCTIONAL_TEST_CRITERIA.md` — analysis only, per task constraints.
