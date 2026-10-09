# Round5 target firmware

Buildable, inhibited STM32G071RBT6 and ESP32-S3 targets. `commissioned=false`
remains; no hardware has been flashed. Current receipts are in
`output/temper-prototype-closure/round5/firmware/verification/`. Historical sibling
receipts and `evidence.json` are preserved and do not establish the changed image.

## Implemented corrections

- R5I002: POST requires two isolated four-wire branch measurements, each entire
  uncertainty interval inside23.75–26.25Ω, cold equilibrium, released contacts,
  discharge and operator confirmation. Records bind to boot/serial, expire60s,
  retire failed serials and are consumed on attempt/fault.
- R5I003 retained: DIN CRC follows command/register words; DOUT CRC at27/28.
- R5I004: PD3 heartbeat input; PD4 fail-low qualified output. Three alternating
  2–15ms edges qualify; glitches/timeouts latch invalid until rails disappear.
- R5I005: two immediate complete ADC reads drain both FIFO slots after startup
  settling; discard both and timestamp only subsequent DRDY. PA8 HSI16/2=8MHz,
  OSR1024,3906.25Hz. Actual peripheral behavior still needs measurement.
- R5I006: request low precedes all four GPIO-matrix disconnects downstream of
  deadtime inversion. Partial initialization also disconnects before inversion.
- Common-timer phase commits gate all shadow loads, stage comparator/actions,
  release on one TEZ; both endpoints work without live timer stop/restart.
  See [MCPWM-PROOF.md](MCPWM-PROOF.md) for actual SDK semantics.
- Actual energy core now permits100ms contact pickup (manufacturer max72.45ms),
  uses73ms mechanical pickup allowance before KT proof, and waits for completed
  loaded proof50ms within110ms. The total446ms source budget is unchanged.

## Product feedback and optional bench instrumentation

`fullbridge_adapter.h` distinguishes UNKNOWN, ONCHIP_REGISTER and BENCH_CAPTURE.
Unknown fails closed. On-chip feedback decodes actual divider/timer/operator,
compare/action/deadtime/pending registers; verifies counter progress, matrix and
output enables; and compares against the previous commanded cycle. No captured
edge arrays are synthesized. These are digital diagnostics, not physical pad
measurements. A scoped oscilloscope record ID, commissioned configuration and
actual physical guard predicates are all required; default app supplies none.

`power_target.c` installs the real `power_binding_t`, connecting register readback,
completed-cycle line telemetry and interpolation over a supplied characterized
phase map. The owner task wakes every250µs, inhibits on>1ms lateness and uses
nonblocking UART writes. Product targets do not compile or call FPGA capture,
SPI/reset/fault boot paths. Optional `fast_spi.c`/`bench_pins.h` retain the92byte,
5MHz,200ns setup,2µs idle bench contract; `optional_bench.required_for_product=false`.

A qualified boot can initialize PWM with authorization, bind a matching reviewed
context and then call boot-only `r5_pwm_prepare_capture` with REQUEST physically
inhibited. Its legacy name denotes zero-phase logic connection for scope
commissioning and on-chip diagnostics; no FPGA is required. Later fault inhibition
cannot be undone through that entrypoint. Default app remains disconnected.

## Shared target/model APIs

Compile these allocation-free C sources into both model and target; do not copy
estimators or fabricate target qualification from model outputs.

- `acquisition.h`: ADS CRC/frame acceptance plus `post_record_accept`,
  `post_record_fresh`, `post_record_consume`; measurement and physical confirmation
  are explicit inputs.
- `qualification.h`: gain/offset from zero/injection checked at a third independent
  point, clipping/stuck/residual rejection; calibrated scale with absolute error;
  supplied NTC coefficients/open-short checks and lag-qualified cold limit; heartbeat.
- `measurement.h`: `r5_measurement_init(error[8])`, then `r5_measurement_add` for
  VLINE,VPRE,VOUT,VBUS,VCATCH,VTANK,IPROOF,ILINE. `.complete`/`.serial` identify a
  completed cycle. Exact piecewise-linear squared integration, interpolated
  crossings,45–65Hz,200–350µs sample intervals; faults latch. Source limits include
  100–140Vrms,15Arms,230Vpeak and crest≤1.8. Two cycles/both crest polarities,
  uncertainty-bounded VPRE<5V/current<0.5A and bus/source≥0.95 qualify precharge.
  Proof requires entire-cycle excitation and0.9–1.1×VOUT/220Ω current interval.
  Qualifier withdrawal immediately removes permission. Catch proof needs initial
  discharge, observed rise and continuing bus/catch correlation.
- `sensor_frontend.h`: the same eight calibration records/ADS/measurement and two
  NTC paths are called by STM32; missing calibration is invalid.
- `line_telemetry.h`:28byte TLM1,sequence,cycleµs,RMSmV,RMSmA,flags1,CRC32, all
  fields big-endian; sequence and local arrival bounds prevent stale/reordered
  estimates. Coexists with20byte TE frames at115200baud. CRC is generic, not FPGA.
- `mirror.h`: source-off all-off/one-channel electrical challenge,100µs settling,
  150µs slots, complete five-channel scan≤1ms,2ms freshness. After stable released
  contacts, `r5_mirror_hold_static` sets all five EXC high and requires physical
  receivers high after settling. Excitation remains high through mechanical tests,
  source and RUN; static samples still expire2ms. TIM3 owns the50µs excitation
  schedule; ADC SPI polling cannot block it. Absolute slot deadlines avoid jitter
  accumulation; settling starts after actual GPIO writes. Host tests exercise
  0–20µs ISR-entry latency and5µs GPIO-write allocation, not measured WCET. KPA/PB use PD8/PD9 commands,
  PC13/PC14 inputs, PA12/PA15 excitation. Wetting/settling need physical verification.
- `bypass.h`: `r5_bypass_loaded` requires completed proof and uncertainty-bounded
  VPRE<1Vrms. Current ratio alone passes a220Ω load mistakenly fed through12.5Ω;
  VPRE rejects that failure. Historical first proof is valid only while KB remains
  commanded and its NC mirror stays open.
- `supervisor_binding.h`: common wrapper embeds the actual energy core and
  `../protection-closure/isolation.c`; public energy enum/wire values stay unchanged.
  Consumes POST at source-isolated mechanical-test START; retains the immutable
  token for delayed core START. PC15 ADMIT starts the hardware attempt only after
  mechanical tests; K1/K2 stay off until actual PB4 ATTEMPT and PB6 TOTAL_WINDOW
  acknowledge within5ms. Prior-high windows fail; acknowledgment wait counts in
  the446ms budget. After first loaded proof, opens both isolators,
  waits first KT edge+131433µs AND actual PB8 PROOF_WINDOW low2ms, then starts a
  second KT pulse. A new completed-cycle serial and50ms continuous loaded proof
  are required for final permission. Source budget stays446ms through reproof. Only the merged qualified RUN command latches software session qualification, including subsequent zero demand. Completing second proof without first RUN still times out at446ms. OFF, fault, a new attempt, lost isolation or lost PWM qualification clears the session. ATTEMPT and all live guards remain mandatory. This is a software command history, not physical SUP_RUN readback: native hardware independently captures actual SUP_RUN and requires live RUNTIME_HEALTHY for the budget escape. Isolation loss clears native RUN/PERMIT immediately; before TOTAL expiry source contactors may remain commanded until firmware faults or the deadline, while after expiry the hardware budget also drops them.
  Caller must honor `.consume_post`; simulated physical inputs remain simulation.

## Verification and limits

Run `IDF_PATH=/private/tmp/temper-r5-esp-idf ./verify.sh`. Tests use ASan/UBSan,
240ADS/736bench/224telemetry bit corruptions, analog/protocol/fault fixtures,
actual SDK register layouts,801phase positions and mixed-shadow interleavings.
Recorded red baselines cover old POST, retained measurement qualifiers,50ms
pickup, circular bypass proof and unspecified feedback provenance. Shared wrapper
exercises two pulses, physical rearm, static loss, cached proof and global deadline.

STM32 links with official CMSIS and ArmGNU13.2; ESP links with IDF5.2.3/Xtensa13.2.
Use isolated output directories. Register models and linked images establish
software/API compatibility, not actual silicon timing. Final board pin exports
must be explicitly reconciled with `pin-contract.json` before accepting its check.

Remaining digital work: provision validated calibration/operator POST records;
complete physical rail/interlock acquisition; install measured phase
map; verify option bytes/BOR/flash, stack and execution bounds. Board admission and
second-pulse permits must match the wrapper and final reviewed export. Missing
predicates stay false. Loading calibration alone does not make this image operable.

Remaining physical evidence: installed ADC uncertainty/drift/injection coverage,
NTC lag/cold equilibrium, contact wetting/timing, all four reset/inhibit levels,
scope measurements of live phase changes/endpoints/nonoverlap, clock/load/DRDY
behavior, two-pulse proof-load thermal qualification and staged tank/pan tests.

The target reads AUX health from PB9 BASIC_HEALTHY: the native gate includes the
24V window, PG5 reset,3.3V watchdog/reset and other hardware limits/diagnostics.
This is the same common gate path as hardware_ok, not redundant rail sensing.
MCU_HEALTHY is driven from acquisition health so it does not wait on its own
BASIC_HEALTHY feedback. No voltage value is inferred from that logic level.

`common/supervisor_outputs.h` exports the exact wire projection used by STM32 and
model. Qualified RESET remains observable while faulted, with all energizing
outputs low. STOP_DONE is an end/abort/fault latch, not the OFF enum; a safe released
RESET clears STOP_DONE before the fresh reset edge. It stays low through all
source-off selftests and admission. Catch-charge history lives in the common
wrapper, clears at new attempt/end/fault and survives normal bus valleys while
live sensor validity, catch≥100V and absolute limits remain enforced. Final proof
PB13 rises while the second KT pulse is retained for one owner iteration, providing
setup/hold before KT withdrawal. GPIO projection tests model discrete latch truth
tables; they do not establish actual native gate propagation or analog qualification.

The remaining provider work is software implementation, separate from physical
qualification: STM32 currently has no factory calibration/NTC record loader, boot
nonce and operator POST submission service, or commissioning-record loader;
`post_record_accept` and sensor validation are implemented but their target records
start empty. ESP32's context has no factory scope/phase-map loader or live rail and
interlock sensing provider, and this standalone image does not connect application
power demand to `power_set_level`. These are not completed target features. Missing
records remain zero/invalid; commissioning and physical inhibit verification stay
false. VPRE factory calibration must use the board's revised801:1 divider.

The existing UART/request/heartbeat interface is now connected: STM32 accepts
controller diagnostics only with a fresh fault-free command and qualified changing
heartbeat, and accepts heat intent only with the dedicated physical REQUEST wire
and matching command flag. This communicates the controller's commissioned on-chip
diagnostics, not an independent physical waveform measurement. ESP32 emits these
signals only after its bound service and physical qualifier context are valid.
Initial telemetry/guard acquisition is allowed before first service tick; subsequent
loss latches inhibition. Dedicated physical hardware guards continue to dominate.
