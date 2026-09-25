# Source reset policy prototype

This is a portable C policy model for the SELV source. It is not linked into
the ESP32-S3 firmware and has no GPIO, frame decoder, scheduler, or transport
driver. The output `request_permit_low` must drive the source-health clear path
(for example by driving `SOURCE_RESET_GOOD` low); the integrator must provide a
separate, electrically qualified input reading the physical latch Q1/PERMIT_TX.
The input `reset_good` is feedback after that clear request is released. The
model allows the latch-low observation while `reset_good` is low, avoiding a
software deadlock between requesting clear and waiting for its feedback.

On boot or reset, heartbeat edge requests and re-arm are inhibited until the
physical permit latch is observed low. A new peer session must then be
established. Only complete, accepted frames in that session can request WDI
falling edges. After observing the start button released, a later press edge
can issue one re-arm pulse if the external watchdog reports good. Loss of
health, watchdog-good, session, or physical permit returns to lockout.
This is a **policy contract**: the caller must report `reset_event` on every
boot, force `new_session_established` false until a genuinely new validated
handshake after that boot, and turn each `heartbeat_edge_request` into one
electrically valid TPS3431 WDI falling edge. No autonomous timer or peripheral
may generate those edges. An ESP CPU-only reset may leave its output GPIO high
until firmware restarts; withholding WDI lets the independent watchdog clear
the external latch after its own timeout.

The tests cover retained-high CPU reset, physical latch readback, held start,
new-session gating, accepted-frame-only heartbeat, health loss, clear
feedback, session loss, and coincident session/start events. A handshake
frame itself does not request a heartbeat edge. Reproduce:

```sh
cc -std=c11 -Wall -Wextra -Werror -pedantic \
  test_source_policy.c source_policy.c -o /tmp/temper35-policy-test
/tmp/temper35-policy-test
```

The worker's original test-first negative control, which removed the readback
heartbeat gate, failed the CPU-reset test as expected. Its temporary mutant
remains outside this candidate; it is not production source.

Before using this in real firmware, define and test the on-wire protocol,
session persistence, ESP pin mapping, latch readback electrical levels,
WDI pulse generation and cadence, start-button edge integration, timeout
handling, and boot ordering. The existing `watchdog_hardware_feed()` drives a
different TPS3823 watchdog unconditionally and cannot serve this function.
