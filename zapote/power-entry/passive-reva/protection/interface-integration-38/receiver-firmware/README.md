# Rev38 receiver firmware target

Target: Microchip `AVR64DA32-E/PT`, as selected in
`../receiver-selection.md`. This directory contains the fixed wire codec and
host-tested durable ID journal. It does not yet contain a device adapter or
full session state machine. The previous ATmega328P fixtures are input
evidence, not a firmware target.

Run the focused host tests from this directory:

```sh
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c tests/test_protocol.c -o /tmp/temper-rev38-wire-test
/tmp/temper-rev38-wire-test
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c journal.c tests/test_journal.c -o /tmp/temper-rev38-journal-test
/tmp/temper-rev38-journal-test
```

The journal test interrupts each of 64 erase/write byte calls for a single
reservation, then checks lockout or a strictly higher next ID. It also
rotates beyond two full rings and rejects a corrupted newest record. This
models byte-level failure, not an AVR NVMCTRL or brownout measurement.

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
