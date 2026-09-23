# Rev38 receiver firmware target

Target: Microchip `AVR64DA32-E/PT`, as selected in
`../receiver-selection.md`. This directory will contain the device firmware
and host-tested protocol core. The previous ATmega328P fixtures are input
evidence, not a firmware target.

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

No receiver firmware or physical test is claimed by this selection record.
