# Power-Active Mapping — Interface Contract

Plan: `docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md` (U8,
KTD6, assumption A2).

This document is the interface contract between the state-machine model
(`firmware/tools/transition_model.py`, U1), the property checks
(`firmware/tools/transition_model_checks.py`, U2, property P1), the
invariant proofs (`firmware/tools/invariants.yaml`, U6:
I-SENSOR-FAULT-BLOCKS-HEATING, I-NO-REENTRY, I-RUNAWAY-REACHES-SAFE-STATE),
and the actual C source (`firmware/main/state_handlers.c`). The single
source-of-truth constants live in `firmware/tools/power_active_mapping.py`;
every consumer imports them rather than redeclaring the sets, so the
mapping cannot silently drift between the model checks and the proofs
(KTD5's "one model, one engine" discipline applied to this abstraction).

## The mapping

```
power_active = {STATE_PREHEAT, STATE_HEATING}
faulted      = {STATE_FAULT, STATE_RUNAWAY_FAULT}
```

## What "power_active" actually means in the C source (read carefully)

The plan's own approach text for U8 says: "`power_active` states call
`power_enable()` in their entry handler and disable power in their exit
path." Taken completely literally against the real
`firmware/main/state_handlers.c`, **this is only exactly true for
`STATE_PREHEAT`.** The audit (`test_power_active_mapping.py`) checks the
REAL contract below, which is what the source actually does and is
provably safe given the manifest, not the plan's literal wording:

1. **`power_enable()` is called in exactly one entry handler:
   `state_preheat_entry()`.** `state_heating_entry()` does **not** call
   `power_enable()` — `STATE_HEATING` is only ever entered from
   `STATE_PREHEAT` (via `EVENT_NEAR_TARGET`) or from itself (the
   `EVENT_NEAR_TARGET` self-loop, "PID control continues"). Per the
   manifest (verified via `transition_model.py`'s
   `incoming_edges("STATE_HEATING", include_self_loops=False)`), the ONLY
   non-self-loop incoming edge to `STATE_HEATING` is from `STATE_PREHEAT` —
   itself already power-active. `STATE_HEATING` inherits power already
   enabled by `STATE_PREHEAT`'s entry handler rather than re-enabling it;
   there is no gap where power is off between the two. This is a
   model-verified fact, not an assumption: if a future manifest change ever
   added an edge into `STATE_HEATING` from a non-power-active state, the
   audit (which re-derives this from the model on every run) would start
   failing, because that new edge would need its own `power_enable()` call
   that doesn't exist.

2. There is no separate "exit handler" concept in this codebase's state
   machine at all — `state_machine.c`'s `transition_to()` calls only the
   NEW state's `_entry()` function; the old state has no `_exit()`
   callback. So "disable power in their exit path" is re-scoped to what
   the C architecture actually has: **every state that the manifest allows
   to be entered directly from a power-active state, and that is not
   itself power-active, must disable power (`power_set_level(0)` and/or
   `pwm_disable_all()`) in ITS OWN entry handler.** Verified (via the U1
   model's edges) for every such state on the current manifest:
   - `STATE_FAULT` (reached from PREHEAT/HEATING on multiple fault events):
     `state_fault_entry()` calls `power_set_level(0)`, `pwm_disable_all()`,
     `pll_disable()`.
   - `STATE_NO_PAN` (reached on `EVENT_PAN_REMOVED`):
     `state_no_pan_entry()` calls `power_set_level(0)`.
   - `STATE_COOLDOWN` (reached on `EVENT_STOP_BUTTON`/`EVENT_TIMER_EXPIRED`):
     `state_cooldown_entry()` calls `power_set_level(0)`,
     `pwm_set_duty_cycle(0)`, `pll_disable()`.
   - `STATE_RUNAWAY_FAULT` (reached via the KTD2 implicit interlock edges
     from every state, including PREHEAT/HEATING):
     `state_runaway_fault_entry()` calls `power_set_level(0)`,
     `pwm_disable_all()`, `pll_disable()`.

3. **`faulted` states call `pwm_disable_all()` in their entry handler.**
   True for both `STATE_FAULT` and `STATE_RUNAWAY_FAULT`
   (`state_fault_entry()`, `state_runaway_fault_entry()`).

## Scope of the audit's claim

Per the plan's Scope Boundaries: the audit inspects entry/exit handlers in
`firmware/main/state_handlers.c` ONLY. It cannot see power-enable paths in
other components (the main loop, timers, ISRs, or any future direct call
to `power_enable()`/`power_set_level()` from outside `state_handlers.c`).
A change to power behavior made anywhere else in the firmware is outside
what this audit can detect.

## Consumers of this mapping

- `firmware/tools/transition_model_checks.py` — P1 ("no edge from a
  faulted state to a power-active state").
- `firmware/tools/invariants.yaml` — I-SENSOR-FAULT-BLOCKS-HEATING,
  I-NO-REENTRY, I-RUNAWAY-REACHES-SAFE-STATE.
- `firmware/tools/test_power_active_mapping.py` — the audit itself.

## Change protocol

If `firmware/main/state_handlers.c`'s power-call pattern changes (e.g. a
new state is added, or `STATE_HEATING` starts calling `power_enable()`
directly), `test_power_active_mapping.py` MUST be re-run; a failure there
means either the C source changed in a way this document no longer
describes accurately (update this document and
`power_active_mapping.py`'s constants together, in the same change), or
the C change introduced a real defect (do not update the mapping to make
the audit pass silently).
