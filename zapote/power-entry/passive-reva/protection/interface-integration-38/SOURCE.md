# Rev38 source authority fixture

`elec/src/source_authority.ato` is the SELV source-side candidate joined to
`receiver_isolation.ato`, `hot_watchdog.ato`, `hot_rails.ato`,
`f2_detector.ato`, `aux_window.ato`, `pfc_controller.ato`, `pfc_power.ato`,
`ac_input.ato` and `driver_stage.ato` by
`power_entry_integrated_38.ato`. The joined
Atopile build connects five physical source/receiver paths: source PERMIT
and health forward, STOP forward, and physical HOT PERMIT plus retained HOT
SESSION feedback reverse. The protocol and relay-request channels remain
assigned in the receiver fixture but have no ESP GPIO/driver producer yet.
The source and driver circuits are partial; this is not a U4 or protected-operation PASS.

`firmware/main/power_entry_authorization.c` now contains a host-tested
source protocol core. Its initial state requests STOP, no PERMIT-set edge,
and no source TPS3431 WDI edge. After low local and physical HOT readbacks,
a new durable challenge arms the source's permit-history reset. The caller
must apply `challenge_active`, take a fresh physical sample, request the raw
reset edge, then confirm the physical Q before `DISARM_ACK` can be sent.
READY requires retained HOT session readback. A button held before READY
cannot start; a release and later press requests one PERMIT-set edge, and
local plus HOT PERMIT readbacks precede REQUEST. Matching ACK before the
fixed deadline arms one START without emitting bytes. `pe_source_commit_start`
requires a fresh physical sample and a caller-provided bound from that sample
through the final START bit; expiry or readback loss aborts. The ESP UART
owner must call it at a synchronous, nonqueued write and prove that bound.
Reinitialization never retransmits START.

`firmware/main/power_entry_source_runtime.c` is the host-tested synchronous
action sequencer for that core. It writes STOP low before draining UART at
boot, leaves WDI untouched, applies challenge before the history-reset pulse,
separates the pulse
and physical Q confirmation across scheduler ticks, applies permit-set only
after a fresh readback, and commits START at the nonqueued UART write. The
validated heartbeat **request** rises before a blocking UART send; the
one-shot then supplies a falling WDI edge. The request is rejected if its
callback consumed the
configured sample-to-pin interval. An I/O failure requests STOP, cancels TX,
and permanently locks the runtime until reboot. These callbacks have no
selected ESP GPIOs or target implementation yet; their bounds are host
fixture parameters, not measured silicon guarantees. The target must use
one serialized owner and prove complete-frame UART and pulse timing.

Deliberate restart enters a separate stopped state: STOP remains requested,
no WDI edge is emitted, and a later physical low-PERMIT/HOT-session readback
must be sampled before `pe_source_disarmed_for_restart` can succeed.
The core's WDI action requires local and fresh link progress after
preparation. Its byte/idle entry points abort on invalidating decoder
errors. These are logical host results: no ESP GPIO assignment, UART driver,
source WDI pin owner, boot pin-level capture, or ESP-IDF target build is yet
present. The existing unconditional TPS3823 feed in `state_machine.c` remains
a different circuit and cannot be counted as the new TPS3431 feed.

The host runtime no longer drives a retained-high heartbeat-request GPIO low during boot:
its first WDI callback is permitted only after a fresh physical-disarm
sample and local safety progress. This removes one software-created feed
edge in the host sequence. The former direct buffer would still have made
a watchdog feed when a retained-high ESP pad became high impedance and its
pull-down took over during CPU reset. The joined source candidate now uses
the spare SN74LV221A-Q1 channel: A2 is low, B2 is the ESP request with a
100 kΩ pull-down, and active-low Q2_N drives WDI with a 100 kΩ pull-up.
Only a **rising** B2 request makes the finite low WDI pulse; a B2 fall on
reset cannot service TPS3431. The requested adapter pulse must begin low,
rise once, and return low even if the pad was retained high. The 10 kΩ/10 nF
timing pair targets approximately 100 µs in TI's 3.3 V example. ESP boot,
the other core, GPIO peripheral ownership, or a queued write could still
make an unintended **rising** request edge. No bootloader/other-core/pad-retention
capture yet bounds the actual post-reset feed tail or proves the external
STOP transition. Intermediate SELV rail loss could also change the one-shot
output while TPS3431 is active; this needs a rail-ordering test. Do not enter
zero for the post-reset feed-tail term in the reset inequality.

The core's `safety_ok` sample means external interlocks **excluding** WDO;
the source may need a first qualified WDI edge after physical disarm to
recover WDO before the reset/check hardware can accept a new challenge.
Mapping `safety_ok` to `SOURCE_HEALTH_Q` would create a boot deadlock. The
actual WDO behavior, feed timing, and pin ownership need target evidence.

The source candidate now uses the spare `SN74HCS21PWR` gate to produce
`SOURCE_PREWATCHDOG_OK = SOURCE_RESET_GOOD ∧ SOURCE_INTERLOCK_N ∧
SOURCE_RAIL_RESET_N`. A 10 kΩ pull-down gives that output a low default.
This is the proposed physical input for the runtime's pre-feed `safety_ok`
check; `rail_good` can separately sample `SOURCE_RAIL_RESET_N`. It excludes
WDO by construction. The standalone and joined netlist audits check that
separation and reject a deliberate WDO short. It is **not yet wired to an
ESP GPIO**, and reset-good and interlock still have no physical producers.
The target must verify threshold/loading, boot sampling, and the relationship
between this sample and the independently clearing source health gate.

`TPS3431SDRBR` is continuously enabled. Its open-drain WDO and ENOUT pins
share a 10 kΩ SELV pull-up. The source SN74LV221A-Q1's second channel shapes
one software-owned positive request edge into WDI's negative feed edge. The
installed candidate CWD is Murata
`GRM1885C1H102JA01D`, 1 nF C0G ±5% at 50 V. The source-health AND also
requires the SELV rail supervisor, reset-good, and interlock high. The
reset-good and interlock signals remain external inputs with local low
defaults. This is a bounded missing-edge detector, not proof that arbitrary
wrong code will stop feeding it. ESP CPU-only reset may retain GPIO state;
source firmware must withhold WDI through boot and physical disarm. No
accepted reset-to-off bound follows from the component timeout.

Physical HOT PERMIT feedback high asynchronously presets the SELV
`SOURCE_PERMIT_SEEN_Q` memory. Its later low level drives
`SOURCE_PERMIT_LOSS_OK` low through an HCS00 NAND. Source PERMIT Q is an
HCS74 memory with raw set clock, D and asynchronous CLR_N driven by the
AND of source health, STOP_N, retained HOT SESSION feedback, and the
readback-loss condition. A held set request cannot acquire a new clock when
the clear recovers. The seen memory's separate SN74LV221A-Q1 reset clock
loads zero only while source Q and physical feedback are low, set request
is inactive, source health is high, and firmware asserts challenge-active.
The receiver protocol must still verify the matching challenge before it
issues DISARM_ACK. The raw reset clock and physical preset are distinct;
coincident-event, pulse-width, and rail-ramp behavior remain unqualified.

The source pull resistors are provisional. The assembled circuit must
calculate loaded ESP GPIO high levels, isolator input loading, supervisor
threshold and delay, both one-shot widths at 3.3 V and rail corners,
readback pulse capture,
partial-power leakage, and fault-to-clear timing. Several parts use
`TBD_REVIEW_ONLY` footprint keys solely to prevent Atopile 0.2.69 from
merging unlike MPN metadata; no land pattern or BOM sourcing is approved.

Build each target separately; passing an entry path without `-b` invokes
every configured target in this version of Atopile:

```sh
uvx --from atopile==0.2.69 ato --non-interactive build -b isolation
uvx --from atopile==0.2.69 ato --non-interactive build -b source
uvx --from atopile==0.2.69 ato --non-interactive build -b driver
uvx --from atopile==0.2.69 ato --non-interactive build -b hot_watchdog
uvx --from atopile==0.2.69 ato --non-interactive build -b hot_rails
uvx --from atopile==0.2.69 ato --non-interactive build -b f2_detector
uvx --from atopile==0.2.69 ato --non-interactive build -b aux_window
uvx --from atopile==0.2.69 ato --non-interactive build -b pfc_control
uvx --from atopile==0.2.69 ato --non-interactive build -b pfc_power
uvx --from atopile==0.2.69 ato --non-interactive build -b ac_input
uvx --from atopile==0.2.69 ato --non-interactive build -b integrated
rustc --edition=2021 --test audit.rs -o /tmp/temper-rev38-isolation-audit
/tmp/temper-rev38-isolation-audit
rustc --edition=2021 audit.rs -o /tmp/temper-rev38-isolation-check
/tmp/temper-rev38-isolation-check
```

The Rust audit checks exact source, driver, and joined pin membership, MPN identity,
the WDO-to-health-to-source-clear path, physical-readback history,
independent raw set/reset clocks, and SELV/HOT domain separation. Mutation
tests remove WDO, HOT feedback, and readback-loss inputs, swap feedback,
and bridge the isolation boundary. HOT rail mutations remove RESET and sense
connections, disconnect AUX, and short AUX to logic5. F2 detector mutations
open a divider, swap an absolute-OV input, disconnect a cross-sense input,
and break the joined trip and supply. AUX window mutations open a divider,
swap the OV input, and break its output or shared reference. HOT watchdog
mutations remove WDI, WDO,
CWD, EN, or its pull-up. Driver mutations remove the ENA clamp,
base bias, receiver abort, and PowerPAD return or short the gate to AUX.
PFC-control mutations break the VSENSE ladder, inhibit FET, current-sense
clamp, permission join, or PWM-to-driver path.
Power-path mutations short F2, move the local capacitor to the bank, omit
one diode anode, or disconnect the switch/F2 sense joins. AC-input
mutations bypass the F1 holder/NTC, open the relay contact, reverse the
flyback diode, miswire the PE capacitor, or cut the bridge L/N and receiver
relay-control joins.
Connectivity does not establish logic
thresholds, capture minima, or power-stage shutdown.

Manufacturer inputs: [TI TPS3431](https://www.ti.com/lit/ds/symlink/tps3431.pdf),
[TI SN74HCS74](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf),
[TI SN74LV221A-Q1](https://www.ti.com/lit/ds/symlink/sn74lv221a-q1.pdf), and
[Murata GRM1885C1H102JA01D](https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/GRM1885C1H102JA01-01A.pdf).
