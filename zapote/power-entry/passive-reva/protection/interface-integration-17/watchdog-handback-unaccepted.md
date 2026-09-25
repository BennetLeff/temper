# Existing watchdog audit for revision16 source-health contracts

Scope: read-only audit of the existing Temper TPS3823-33 circuit and firmware
against revision16's `SOURCE_RESET_GOOD` and `SOURCE_WATCHDOG_GOOD` inputs.
This does not select a new part or claim hardware qualification. The revision16
fixture itself says these producers are still unimplemented (interface-capture-16/README.md,
"Remaining integration and physical work", item 2) and that its reset ERC
findings include an external existing-health producer.

## Existing hardware and pin map

The existing compiled electrical design does instantiate a `TPS3823-33DBVR`:
`elec/src/components.ato:578-605` defines the part, SOT-23-5 footprint,
1.6 s watchdog, and pins GND=1, RESET_N=2, MR_N=3, WDI=4, VDD=5. The
`InterlockWatchdog` wrapper repeats the same map at
`elec/src/interlock_unit.ato:79-89`. The generated board schematic contains
U20 with value `TPS3823-33DBVR`, SOT-23-5, at
`pcb/safety_interlock.kicad_sch:1608-1615`.

The existing module connects VDD and a 100 nF bypass to 3V3, GND to 3V3
ground, MR_N to VDD, WDI to the watchdog heartbeat, and RESET_N to the
interlock reset net (`elec/src/modules.ato:3026-3041`). In the top-level
interlock, WDI is driven by `wdt_kick` and RESET_N becomes `wdt_reset_n`
(`elec/src/modules.ato:3331-3333`). The generated schematic labels identify
the actual board nets as `WDT_KICK`, `WDT_RESET_N`, `+3V3`, and `gnd`
(`pcb/safety_interlock.kicad_sch:1623-1637`).

TI's current official datasheet (TPS382x Rev O, SLVS165O, March 2025,
https://www.ti.com/lit/ds/symlink/tps3823.pdf) confirms: TPS3823 has a
push-pull active-low RESET output; pin 1 RESET, pin 2 GND, pin 3 MR, pin 4
WDI, pin 5 VDD (pp. 3-4). WDI timeout is nominal 1.6 s, with 0.9 s minimum
and 2.5 s maximum; reset power-on delay is 200 ms nominal, 120-300 ms; the
TPS3823-33 VDD falling threshold is 2.86/2.93/3.00 V min/typ/max over
-40..85 C. WDI must remain driven high or low to detect a failure; if left
floating, the device internally generates pulses and prevents a watchdog
reset. MR has an internal approximately 90 kOhm pull-up and a low MR asserts
RESET. These details are also transcribed in `elec/src/components.ato:584-599`.

## Firmware evidence

The firmware uses this device as a heartbeat watchdog, not as an independent
source-health producer. GPIO7 is WDI, GPIO6 is an input from RESET_N, and
GPIO15 is a separate active-high runaway-cut output
(`firmware/components/safety/safety.h:163-175`). `watchdog_hardware_init()`
sets GPIO7 as an output initially low and GPIO6 as an input with an added
pull-up (`firmware/components/safety/safety.c:462-498`). Each
`state_machine_update()` toggles GPIO7 (`firmware/main/state_machine.c:214-220`;
implementation `firmware/components/safety/safety.c:505-512`).

The firmware only samples GPIO6 after boot and during safety checks. It enters
safe mode when the sampled RESET_N is low
(`firmware/components/safety/safety.c:204-213`, `277-285`, `368-373`). The
comment explicitly admits that this is not a true MCU reset path unless RESET_N
is also tied to ESP32 EN (`firmware/components/safety/safety.c:204-208`). The
existing electrical design instead maps GPIO6 as an input and keeps the
explicit MCU reset request on GPIO14 separate
(`elec/src/modules.ato:3687-3690`). Therefore an external TPS3823 timeout does
not, by this evidence, reset the MCU or itself clear the revision16 permission
latch; it asserts the existing interlock fault path and is observed by firmware.

## Contract decision

**Reuse as `SOURCE_WATCHDOG_GOOD`: conditional, only after net separation.**
The TPS3823 is a real selected existing component and its push-pull RESET_N is
a usable active-low fault indication. A qualified adapter could define
`SOURCE_WATCHDOG_GOOD = WDT_RESET_N` (high means no observed rail/watchdog
fault) and retain the existing WDI heartbeat. The revision16 source-health AND
input must be driven from that signal with the documented 10 kOhm default-low
behavior. Do not call the current firmware GPIO6 read a producer; it is merely
an observer.

**Reject as the complete source-health solution.** TPS3823 RESET_N combines
VDD supervision and missed-WDI timeout on one output. It cannot independently
prove `SOURCE_RESET_GOOD` versus `SOURCE_WATCHDOG_GOOD`. Its 2.93 V typical,
2.86-3.00 V specified falling threshold and only 30 mV typical hysteresis also
do not meet the separate UVL-02 2.9 V falling / 3.0 V rising requirement; the
repo's `LogicUVLOComparator` documentation records that failure
(`elec/src/modules.ato:3043-3050`, `3118-3122`). The dedicated TPS3700-based
logic-rail UVLO is a distinct fault path, not currently exported as the
revision16 `SOURCE_RESET_GOOD` level.

**Do not use a firmware GPIO as either independent good signal.** GPIO7 is the
heartbeat source and can be stuck or misconfigured with the MCU; GPIO6 is only
a sampled input. The revision15 reset design correctly states that a firmware
GPIO is not independent reset/watchdog evidence (`interface-active-15/reset/design.md:12-19`).

**Reset/permission limitation remains open.** The existing watchdog can force
the old fault OR/latch path through `wdt_reset_n` (the module connects
`wdt.reset_n` into the fault aggregation at `elec/src/interlock_unit.ato:292-304`
and the SafetyInterlock latch chain), but the evidence does not show that a
TPS3823 assertion produces the revision16 HOT-latch-clear observation or a
fresh source permission edge. The revision16 rearm sequence therefore still
needs an independently measured/implemented low interval and a real
`SOURCE_REARM_PULSE` producer.

## Concrete hookup if retained

Keep the existing U20 TPS3823, MR_N tied high, WDI on the existing GPIO7
heartbeat, and its fault/shutdown path intact. Fan out RESET_N only through a
qualified, rail-compatible interface into the revision16 source-health logic,
and label that derived level `SOURCE_WATCHDOG_GOOD` (default low when the
producer or rail is absent). Add a separate supervisor/UVLO output for
`SOURCE_RESET_GOOD`; do not derive it from GPIO6, from firmware state, or by
renaming the combined TPS3823 RESET_N. Verify the 0.9-2.5 s watchdog timeout,
200 ms reset delay, startup WDI behavior, and the actual permission-latch clear
path on the bench before treating either signal as qualified.

Bottom line: one existing TPS3823 can be reused as a conditional watchdog-good
source, but the current 136-component design does not yet provide the two
independent revision16 source-health producers or prove that an MCU reset
clears permission.
