# Common-timer phase transaction

Scope: ESP32-S3, ESP-IDFv5.2.3 commitc9763f62dd00c887a1a8fafe388db868a7e44069,
standalone exclusive MCPWMgroup0 owner. This is a register-contract argument,
SDK compile/link evidence and host interleaving test; it is not a pad measurement.

The real SDK `components/soc/esp32s3/include/soc/mcpwm_struct.h` defines:

- `update_cfg.global_up_en`: global enable of updates of **all active registers**.
- `gen_stmp_cfg.gen_a_upmethod` / `gen_b_upmethod`: bit0 means load onTEZ.
- `gen_cfg0.gen_cfg_upmethod`: bit0 means load generator actions onTEZ.
- `gen_a_shdw_full` / `gen_b_shdw_full`: pending until active value takes shadow.

`mcpwm_new_comparator` sets the actual operator's update method from
`update_cmp_on_tez`. `mcpwm_new_operator` configures generator-action update from
`update_gen_action_on_tez`. Both operators are connected to the same timer.
`mcpwm_comparator_set_compare_value` writes shadow values; it does not force a
shadow flush. The generator action setter also writes its shadow configuration.
These are the actual SDK APIs used and compiled by the target.

`apply()` waits for the previous transaction to load, clears the single global
update-enable bit, performs every compare/action write, executes XtensaMEMW,
and sets that one enable bit. At a TEZ during staging the active set remains
unchanged. At a TEZ after release every member loads its completed shadow. A TEZ
coincident with the enable write either sees the old gate or the new gate for the
entire group: there is no per-operator enable sequence. No ISR timing deadline is
used for atomicity. The timer runs continuously. A bounded pending-status wait
rejects a stopped/stuck timer. Stop/restart is absent from live updates.

Initial setup, with request low and pads disconnected, is the only path using
the SDK's group flush. Group0 must have no second owner; the standalone project
allocates timer0/operators0+1/comparators0+1 and uses no other MCPWM component.
Changing this ownership invalidates the direct pending-status register indices.

Each raw leg rises at `shift`, falls at `(shift+half)%period`; A shift is0 and
B shift is0..half inclusive. EMPTY is high only for shift0, otherwise low.
Thus at phase1 the B falling edge is at EMPTY/compare0, its rising edge at half;
no compare at the inaccessible end of a cycle is needed. RED delays the high
rising edge and FED plus inversion delays the complementary low rising edge.
For1600ticks and10ticks input deadtime, all four steady pulses last790ticks.
The host test exhausts all801 representable phase positions, checking pulse
length and same-leg nonoverlap, and demonstrates24 mixed-state observations
when TEZ is allowed during ungated writes versus zero with the global gate.
This mathematical register model does not prove ESPsilicon's event ordering or
transient pad pulse lengths on large phase steps; those remain scope tests.

Inhibit first removes PWM_REQUEST. It sets each GPIO output latch low, explicitly
connects the pad to `SIG_GPIO_OUT_IDX` with no inversion, and enables GPIO output.
The matrix disconnect is downstream of MCPWM's deadtime inverter. Every newly
allocated generator is disconnected before deadtime configuration, so partial
initialization cannot expose inverted low-side outputs. No raw-generator force
is used as proof of a low physical pad. A failed staged transaction inhibits
before reopening the update gate. Commissioning remains false, no API can raise
request, and pads stay disconnected in this exact binary. A one-time
`r5_pwm_prepare_capture` entry point can reconnect the actual SDK signal matrix
only at zero differential phase with request low and caller-supplied physical
inhibit verification. The default application supplies false. Preparation is
one-use per boot: a later inhibit cannot be undone by calling it again.

Required physical follow-through: confirm four pad levels through reset and
partial initialization, phase0/1 and fast phase transitions, minimum pulse and
nonoverlap timing, pending-bit behavior, update-gate event ordering, simultaneous
fault/shutdown, and worst-case interrupt/flash/load latency. This source does
not assert that those measurements have happened.

Runtime product diagnostics explicitly use ONCHIP_REGISTER feedback. The readback
helper checks both operator update enables, common timer selection, fixed S3
PLL160M divider programming, running up-counter, no sync or shadow period updates,
all compare pending bits cleared, TEZ action updates, expected rise/fall action
words, no software force/carrier/brake, RED/FED delays/inversion, counter progress,
and four output matrix selections/enables. It derives the reported cycle from
registers and compares it with the previous commanded cycle. The host SDK-layout
test decodes801 phases and injects register faults. This detects digital corruption;
it does not measure clock accuracy, pad propagation, deadtime silicon behavior or
external gate drivers. Product feedback never populates physical capture arrays.
