# Rev38 receiver firmware target

Target: Microchip `AVR64DA32-E/PT`, as selected in
`../receiver-selection.md`. This directory contains the fixed wire codec,
host-tested durable ID journal, and receiver session core. It does not yet
contain the AVR device adapter, fuse image, or pin driver. The previous
ATmega328P fixtures are input evidence, not a firmware target.

Run the focused host tests from this directory:

```sh
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c tests/test_protocol.c -o /tmp/temper-rev38-wire-test
/tmp/temper-rev38-wire-test
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c journal.c tests/test_journal.c -o /tmp/temper-rev38-journal-test
/tmp/temper-rev38-journal-test
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c journal.c receiver.c tests/test_receiver.c -o /tmp/temper-rev38-receiver-test
/tmp/temper-rev38-receiver-test
```

The journal test interrupts each of 64 erase/write byte calls for a single
reservation, then checks lockout or a strictly higher next ID. It also
rotates beyond two full rings and rejects a corrupted newest record. This
models byte-level failure, not an AVR NVMCTRL or brownout measurement.
The receiver-core test checks fixed START expiry despite WDI progress, the
physical abort command on STOP and preparation trip, session ID advancement,
and dual-source WDI feed. All time windows in the test are arbitrary logical
ticks; no numerical safety allowance follows from them.

`receiver.c` separates physical disarm observation from the two history
resets. It first requests PA6 attempt-valid high, then a PF1 disarm-sample
clock on a later call, then requires a fresh PC0 Q-high sample. Only then is
preparation-abort memory reset and read back before reserving the ID. The
challenge is published only
after a second physical sample following the EEPROM write. The matching
DISARM_ACK requests a separate HOT permit-seen reset; only after its Q is
read low and preparation-abort Q remains low does the core release abort and
request revalidation. These host events require the target adapter to take
fresh physical samples; reusing one earlier sample defeats the ordering.

The core also requests one RUN-set pulse and one high-then-low WDI pulse per
validated feed. TI's TPS3431 services a
**falling** WDI edge; alternating a GPIO level on successive feeds would
lose every second service event. The adapter must meet the device's minimum
WDI pulse width and post-enable setup time.
The target adapter must drive each pin low before and after the pulse, sample
the actual Q pins, and leave `RECEIVER_ABORT_N` low until the post-ack HOT
permit-seen reset has completed and its readback is low. The independent
latch clear and gate inhibit must dominate
any race between a sampled input and a pulse. The core alone does not prove
that race, AVR boot pin levels, or rail-loss behavior.

The core requests `attempt_valid` high when it enters disarm observation and
keeps it high for the current attempt; every lockout/STOP and boot requests
low. The future PA6 adapter must establish that high level before issuing
the PF1 disarm-sample edge and later preparation-abort reset edge, and must
default PA6 low while reset or
unpowered. This separates a new STOP or receiver reset during preparation
from `RECEIVER_ABORT_N`, which is already low at that time. The current
partial fixture joins PA6 to the abort preset and disarm clear; the target
GPIO sequence, live fault producers, and full joined hardware remain U4/U5
gates. PF1 must pulse from low to high once, return low, and never be
implemented as an eligibility-gated clock. The physical PC0 result after
that edge determines whether preparation may begin.

`pe_receiver_history_reset_complete` now requests **only** abort release.
The adapter must apply that pin level, obtain a fresh PF0/20 sample of the
physical `HOT_SESSION_CLEAR_N` node, and call `pe_receiver_revalidate`.
Only that later call can request the revalidation pulse. A low clear
readback, trip, or lost disarm locks the attempt out. Passing a cached
pre-release sample is invalid because abort itself holds the clear low.

The protocol core must expose explicit input events and requested outputs so
host tests can exercise reservation, interruption, cancellation, expiry and
reset without simulating a passing physical protection path. The target
adapter owns USART0, EEPROM NVMCTRL, a monotonic timer, the one external
WDI GPIO, and the assigned pins. Hardware latches, independent detectors,
default-low abort, and the source watchdog remain separate circuit owners.

Before target firmware can claim build/behavior PASS:

1. Freeze the frame bytes/CRC, EEPROM record bytes, BOD/clock fuses and
   watchdog feed conditions; inspect the programmed fuse and image receipt.
2. Host-test power loss at each EEPROM erase/write boundary, boot with a
   blank/corrupt/exhausted store, and restart after a published session ID.
3. Test STOP in READY, START after the fixed deadline despite healthy
   traffic, a qualified new trip during preparation, and receiver reset with
   the HOT latches powered. Verify `RECEIVER_ABORT_N` at the pin boundary.
4. Build with the exact AVR64DA32 device toolchain and compare assigned
   physical pins to the joined Rev38 netlist. This checkout currently has
   no `avr-gcc`; a host-only build cannot fulfill this step.

No AVR target build or physical test is claimed by this selection record.
