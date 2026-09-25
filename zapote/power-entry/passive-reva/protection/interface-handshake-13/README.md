# Interface handshake 13 — isolated command model and AUX decision

This round implements a two-endpoint logical start handshake and closes the AUX
review with explicit missing bounds. It does not produce an electrically
accepted interface. The latest compiled candidate remains **revision 11, 136
components**. Canonical electrical source and PCB are unchanged.

Final verification: **21 behavior checks passed**, plus one successful witness
of the known in-flight START limitation. Deliberately retaining an old session
in a temporary mutant caused two expected test failures. All nine frozen input
hashes remain unchanged.

## What changed

The command model exchanges a receiver session challenge, a request tied to
fresh local user intent, an acknowledgement, and a matching START. Independent
maintained PERMIT and rail health override the command exchange. Sessions must
never be reused across faults or receiver power cycles. The model treats decoded
frames and abstract clock ticks as inputs; it does not implement their hardware.

The first Luna implementation passed its own tests but contained a real restart
bug: the actual PERMIT-low frame handler cleared RUN without invalidating the
session. After recovery, replayed old Request and START frames re-enabled RUN.
`parent-v1-witness.rs` and its log preserve the independent reproduction. A
passing witness test means the rejected implementation exhibited the defect.
The corrected implementation is `command/handshake.rs`; `command/handshake-v1.rs`
is historical and must not be adopted.

The parent also added `parent-tests.rs` to exercise the actual PERMIT/health-loss
paths in all four active receiver phases, replay before/after recovery, exact
handshake expiry despite duplicate requests, fresh intent ordering, and receiver
object replacement using a retained persistent counter. The test harness is
built by concatenating these tests after the candidate source; no separate
engineering implementation is introduced.

## Acceptance boundary

Logical-model tests can accept behavior under the stated event contract. They
cannot demonstrate that an open or shorted conductor produces the required
link-fault event, that a frame decoder cannot manufacture a valid command, or
that an MCU samples PERMIT quickly enough. A source reset cannot retract a START
already in flight before the receiver observes reset/link loss. Detection latency
and permitted in-flight command behavior must be specified and qualified.

A real implementation still requires:

- A HOT receiver state machine and a bidirectional isolated transport. The
  shortlisted ISO7740 has four forward channels, no return channel; it does not
  provide the challenge/ACK path by itself.
- Atomic persistent session allocation that survives interrupted writes and
  power cycles. The in-memory counter object models this prerequisite only.
- Source-side fresh-intent qualification, a reliable clock, frame lifetime and
  reset/link detection deadlines; logical ticks are not qualified milliseconds.
- An independent electrical path by which maintained PERMIT/rail faults force
  gate disable, including boot and processor-failure behavior.

The executable `parent_boundary_witness` also demonstrates the reset window:
a START emitted before source reset can be accepted before the receiver sees
link loss; calling the link-fault observer then clears RUN and the session.
If the requirement forbids that window, this candidate is blocked until an
independent reset/abort path and its timing are established.

These functions have no integrated part count yet. A passing message-level test
is insufficient reason to add an assumed processor or isolator to the circuit.

## AUX decision

See [aux-decision.md](aux-decision.md). The TPS26601 static threshold fits, but
its 120 kΩ current setting is insufficient and output transient voltage is not
bounded. A relevant adjustable-clamp alternative, LT4363, also passes a
conditional static screen but lacks an accepted transient/SOA design. Neither
is adopted. The decisive missing quantity is the worst-case protected-output
peak, including delivered fault charge, effective downstream capacitance and
parasitics, against the 18 V driver limit.

## Reproduce and evidence

Use standalone `rustc --edition=2021 --test` on `command/handshake.rs`.
For independent checks, concatenate `command/handshake.rs` and
`parent-tests.rs` into a temporary Rust file, then compile it with the same flags.
Run `parent_review` to select the independent suite. Compile
`aux-clamp-screen.rs` as a standalone executable for the conditional arithmetic.

`receipt.json` records completed commands and outcomes. `input-identity.json`
checks all nine previously frozen source/contract inputs; commit identity alone
cannot identify these local, partly untracked artifacts. `artifact-hashes.json`
identifies this round's final evidence. No hardware test, schematic integration,
PCB edit, vendor contact, commit or push is claimed.
