# Revision 27: logical fault reset versus retained hardware RUN

Status: **integration counterexample and output contract, not a changed
circuit**. Date: 2026-09-22. Revision 26 compiles the AUX clamp, but its
`hot_permit` and `hot_arm` producers are still external. This review tests
whether the existing Revision 13 command model's fault reset would, by itself,
turn off Revision 11's retained latch. It would not.

## Causal chain

The [Revision 13 receiver](../interface-handshake-13/command/handshake.rs)
sets its logical `Running` state after a matching START and calls
`invalidate()` on `link_fault()`. That call changes only model state. It emits
no electrical output or event to Revision 11.

In the [compiled Revision 26 source](../interface-integration-26/source-candidate/elec/src/power_entry_f2_shutdown_revb.ato),
`arm` reaches the first SN74HCS74 clock through `arm_buf`; `latch.D1` is tied
high. The latch's asynchronous clear takes `clear_ok`, which includes the
buffered maintained `permit` plus rail/health terms. The final enable gate is
`run AND clear_ok`. There is no link-fault input in that source. With the
other health terms and PERMIT still high, taking ARM low after a link fault
does not clear RUN; the final enable stays high. A separate AUX or watchdog
fault might also clear it, but that cannot be assumed for a command-link
fault with otherwise healthy rails.

The [executable boundary witness](latch-boundary-tests.rs) appends two tests
to the frozen Revision 13 model. The first accepts a fresh START, sets a
minimal model of the Revision 11 latch, calls `Receiver::link_fault()`, and
observes **receiver Running=false while modeled hardware enable=true** when
`clear_ok` remains high. The second shows `clear_ok=false` clears the modeled
latch and that restoring `clear_ok` without a new ARM edge does not restart
it. Both are expected-pass tests of the boundary; neither simulates analog
timing or proves a selected part's fault response.

## Required output contract before control integration

| Event | Required action at the Revision 11 boundary |
|---|---|
| Boot, unqualified receiver, or open link | ARM low; hardware permission/clear low by a specified, verified path. |
| Source health loss, source reset, or link/decoder fault | Force `clear_ok` low through maintained PERMIT or an independent HOT health input; bound detection and propagation time against gate/relay turn-off requirements. Merely clearing the receiver's software state is insufficient. |
| Fresh session with stable health and PERMIT | Permit may become high after the receiver and source are qualified. ARM stays low until an accepted matching START. |
| Accepted matching START | Emit one bounded rising ARM pulse while `clear_ok` is valid; then return ARM low. Never mirror a maintained command level to ARM. |
| Recovery after any invalidation | Require a new session and deliberate local intent; reasserting PERMIT alone must not make RUN true. |

Two possible electrical ways to meet the fault-clear row need further design:
the isolated PERMIT channel could be proven to fall on every relevant link
fault, or an independent HOT link-health/watchdog signal could enter the
hardware clear aggregation. Neither exists in the compiled Revision 26
candidate. A held-high PERMIT conductor or a fault confined to the command
channel must be included in the failure analysis; a software `link_fault()`
callback is not evidence the hardware path will fall.

The Revision 13 [in-flight START witness](../interface-handshake-13/parent-tests.rs)
is a separate open timing problem: START may arrive after source reset but
before the receiver detects it. The source-reset output path must drive a
hardware disable quickly enough for the eventual product requirement. No
source-reset/disable propagation bound has been established here.

## Reproduce

From the worktree root:

```sh
cat \
  zapote/power-entry/passive-reva/protection/interface-handshake-13/command/handshake.rs \
  zapote/power-entry/passive-reva/protection/interface-integration-27/latch-boundary-tests.rs \
  > /tmp/temper-rev27-latch-boundary.rs
rustc --edition=2021 --test /tmp/temper-rev27-latch-boundary.rs \
  -o /tmp/temper-rev27-latch-boundary
/tmp/temper-rev27-latch-boundary
```

Observed: **19 passed**, including the two boundary tests. The Revision 13
source was not edited. There is no new Atopile module, PCB change, ERC claim,
isolator selection, physical command receiver, or bench measurement. The
[Revision 26 control map](../interface-integration-26/control-binding.md)
contains the exact compiled latch/enable identities and Rev16 fixture mapping.
