# Reset/transport boundary 14

This artifact explores a proposed timed reset boundary around the v13
handshake. It uses a reduced decoder, not an end-to-end integration of the
v13 source; full frame validation remains an input assumption. It is a timing contract model, not an electrical proof. The model is
standalone Rust and intentionally has no MCU, isolator, gate-driver or PCB
part selection.

## Block-level architecture

```text
SELV coordinator SOURCE_OK --[isolated, default-low path]--> HOT RESET_IN
                                                           |-- clears gate latch
decoded challenge/request/ack/start ---------------------->| command decoder
HOT rail health -------------------------------------------| independent trip
maintained PERMIT -----------------------------------------| independent trip
                                                           v
                                  final_permission = HOT_HEALTH
                                    AND MAINTAINED_PERMIT
                                    AND !INHIBIT_LATCHED
                                    AND GATE_LATCHED
```

`SOURCE_OK` is a maintained level, not a firmware pulse. The HOT side is
default-low while the source is absent. A sampled low is captured by the reset
path and schedules an independent inhibit; when it arrives, it clears the
output latch even if the decoded command state machine is frozen. The v13
challenge/ACK/START state machine still owns session and intent ordering, but
cannot override the inhibit. Software must separately observe reset and take
its decoder offline before a new session is installed.

The model's source-side reset/brownout role is hardware-level deassertion. A
source processor may request `SOURCE_OK`, but its reset or loss of supply must
remove that level without firmware cooperation. The receiver keeps the
persistent session counter and monotonic `last_session` role. The source keeps
its persistent last accepted challenge and generates a fresh local intent; the
model's `next_session` and `last_session` fields stand for those storage
contracts. Interrupted nonvolatile writes, wear, and actual challenge transport
are outside this artifact.

## Timing contract and limitation

The executable uses two abstract ticks from a *sampled* SOURCE_OK low to HOT
inhibit and two ticks from source recovery to release. They are proposed
placeholders, not measurements from ISO774x, a latch, or a gate driver. A
hardware review must replace them with measured worst-case propagation,
filtering, setup, and gate disable values. The input circuit must specify the
minimum low-pulse width that its sampler/latch guarantees to capture; this
model begins after that capture and does not claim arbitrary analog-glitch
detection. For a recognized/captured event at `t_capture`, the abstract contract is:

`t_inhibit <= t_capture + T_capture_to_inhibit`

The fault-to-capture detection interval must be added separately. An
unrecognized analog pulse has no bound from this model.

and the final permission must be false by that same observed inhibit event. A
START at exactly `t_inhibit` is processed first, then the reset edge clears the
latch; this is the conservative same-timestamp ordering. A measured example
with START at tick 5 and inhibit at tick 6 leaves one enabled model tick before
the latch clears. Therefore the global claim “a source reset can never permit
any in-flight START at any later instant” is not established. Even an
asynchronous abort path has finite physical propagation. The model exposes that ordered micro-event and finite window instead
of assigning it zero latency.

The available TI values do not close this contract. ISO774x logic-level limits
describe separate supply domains and output VOH/VOL, but do not establish this
whole shutdown path's worst-case delay. UCC27511A's published disable-input
propagation figure (about 23 ns at 12 V and 30 ns at 4.5 V under its stated
test load) is only driver input propagation; it is not a bound for the actual
split gate resistors, MOSFET charge, Miller plateau, latch, or brownout
detection. Those values therefore do not appear as synthetic limits in the
Rust model.

At power-up the model begins with SOURCE_OK low and no recovery permission; an
explicit low-to-high qualification is required before the first session. After
an observed fault low, a high release does not restore command operation. The
receiver must observe the release, the decoder must report reset, and a strictly
newer session plus fresh local intent must arrive before START. A held-high
command or stale START is rejected.

## Fault matrix

| Fault | Independent action | Test |
| --- | --- | --- |
| source brownout / disconnect | SOURCE_OK low schedules inhibit | `source_loss_clears_gate_after_declared_bound` |
| reconnect after observed low | release, then new session + intent | `disconnect_reconnect_after_observed_low_requalifies` |
| stuck-high decoded command | frozen decoder cannot re-latch output after trip | `stuck_high_command_does_not_restart_after_reset` |
| fault at offline/idle/request/START | inhibit clears latch independently | `resetting_each_phase_is_fail_closed` |
| HOT rail health loss | immediate local trip, no frame needed | `hot_health_and_permit_trip_without_command_frame` |
| reset conductor fails high | no inhibit observed | `reset_conductor_fail_high_is_explicit_single_fault_gap` |
| reset conductor open with qualified HOT pulldown/default | captured low asserts inhibit | `reset_conductor_open_trips_through_default_low` |

An open conductor is covered only under the stated qualified default-low
input contract. A failed-high conductor remains an explicit uncovered fault;
this is one maintained reset path, not redundant voting.
Physical decoder framing, open/short discrimination, isolator channel choice,
and the MCU/HOT mapping remain integration work.

There is also a channel-budget consequence. A separate SOURCE_OK reset path
consumes an isolated forward signal in addition to any command transmit,
maintained PERMIT, and relay/control channels. ISO7740 is four-forward only;
ISO7741F provides three-forward/one-reverse, which can carry an ACK direction
but does not automatically fit all of those independent signals. The block is
therefore a functional candidate, not a selected isolator pin map. A future
implementation may combine upstream health terms into a default-low
`PERMIT_TX = interlock_PERMIT AND SOURCE_OK AND external_watchdog_OK` signal to
fit the channel budget, but that would reduce fault diagnosability and must be
reviewed as a different architecture. A same-wire failed-high PERMIT_TX remains
an uncovered single fault unless a second independent trip path is added.

## Reproduction

```text
rustc --edition=2021 --test reset_timing.rs -o reset_timing_tests
./reset_timing_tests
rustc --edition=2021 reset_timing.rs -o reset_timing
./reset_timing > results.csv
```

The CSV is a small evidence table from the same executable. All latency numbers
are abstract ticks and must not be copied into a schematic as component limits.

Parent corrections after the worker handback: an open conductor now schedules
the default-low trip; all event entry points service an already-due hardware
trip even when a command is invalid. The special coincident START ordering is
retained, with inhibit serviced before the method returns. Independent tests
first demonstrated both defects in `reset_timing-worker-v2.rs` and then passed
against `reset_timing.rs`. The historical source is not an accepted candidate.

Boot in this model represents supplies already evaluated healthy and the
power-on low state established. Its first explicit high permits logical
qualification immediately; this does not measure or qualify physical boot
settling. Postfault release is two abstract ticks. A HOT health/permission
event is represented at the local trip observation, not zero physical delay
from rail voltage movement. `arm_authorized` represents a hardware-clearable
qualification state; keeping that flag only in ordinary MCU RAM would not
implement the frozen-decoder contract. Actual gate-driver output and MOSFET
turnoff are outside `output_enabled()`.
