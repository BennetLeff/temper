# Rev38 receiver firmware target

Target: Microchip `AVR64DA32-E/PT`, as selected in
`../receiver-selection.md`. This directory contains the fixed wire codec,
host-tested durable ID journal, receiver session core, and host pin-sequencing
runtime. `avr64da32_target.c` now contains an engineering register backend for
the selected device: exact-pin GPIO, 24 MHz OSCHF/TCB0, USART0 8N1,
byte-addressed NVMCTRL EEPROM, and synchronous pulse ownership. The default
target image has zero timing windows and stays in LOCKOUT. There is no fuse
image or measured pin-timing receipt. The previous ATmega328P fixtures are
input evidence, not a firmware target.

The target checks four AVR64DA32 fuse bytes before enabling its runtime.
Build-time `PE_TARGET_EXPECTED_WDTCFG`, `PE_TARGET_EXPECTED_BODCFG`, and
`PE_TARGET_EXPECTED_SYSCFG0` default to zero; that combination always fails
the boot check. The OSCCFG expectation is zero for internal OSCHF. An
operational image requires an explicitly reviewed non-windowed internal WDT
period, continuous active BOD mode and level, PF6 external RESET
(`RSTPINCFG[3:2]=0b10`), a physical PF7 UPDI connection,
and EESAVE for the session journal. The image compares the programmed bytes
exactly to those expectations. It feeds the internal WDT only after a
completed receiver tick with no I/O fault; the external WDI still needs
local and matching link progress. USART receive activity alone feeds
neither watchdog. These checks do not select a WDT period or BOD threshold,
or prove reset behavior between valid digital supply levels.

Build the default locked image with Microchip AVR 8-Bit Toolchain 4.0.0.52
(avr-gcc 15.1.0):

```sh
make -f avr64da32.mk AVR_GCC=/path/to/avr-gcc AVR_SIZE=/path/to/avr-size
```

This checks AVR64DA32 header/linker compatibility and the C register adapter;
it does not qualify a programmed receiver. Preparation, START, watchdog,
USART byte-gap, ping-period, and sample-to-RUN bounds must be accepted before
any nonzero `PE_TARGET_*` values are programmed. The source rejects nonzero
values unless `PE_TARGET_OFFLINE_COMPILER_EXERCISE` is explicitly defined;
that flag is only for an offline compiler exercise. The relay output stays
low: relay policy,
boot/disarm behavior at real pins, and the fuse/BOD image remain open.
The fuse-readback adapter revision has not been rebuilt with `avr-gcc` in
this worktree because that compiler is unavailable in the current
environment. The earlier target build receipt applies to the preceding
register adapter only.

The GPIO map follows `../receiver-selection.md` and
`elec/src/receiver_isolation.ato`. PC2 reads active-low `HOT_FAULT_N`, PD3 is
`RECEIVER_ABORT_N`, and PD5 is the sole RUN-set output. The adapter clears
owned output latches before enabling their drivers; external pull-downs own
the reset and unpowered interval. A saved netlist/pin-state review and real
RESET/rail-collapse captures are still required. The EEPROM adapter follows
Microchip's [mapped EEPROM byte erase/write sequence](https://onlinedocs.microchip.com/oxy/GUID-51D4F2DF-E4D3-4379-8E03-9AAF2593C7DA-en-US-3/GUID-A7C0BF8A-FBED-40D7-8EF1-66D73278B2E3.html)
and reads each byte back. This is not a power-interruption proof on silicon.

Run the focused host tests from this directory:

```sh
cc -std=c99 -Wall -Wextra -Werror -pedantic avr64da32_boot_contract.c tests/test_avr64da32_boot_contract.c -o /tmp/temper-rev38-avr-boot-test
/tmp/temper-rev38-avr-boot-test
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c tests/test_protocol.c -o /tmp/temper-rev38-wire-test
/tmp/temper-rev38-wire-test
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c journal.c tests/test_journal.c -o /tmp/temper-rev38-journal-test
/tmp/temper-rev38-journal-test
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c journal.c receiver.c tests/test_receiver.c -o /tmp/temper-rev38-receiver-test
/tmp/temper-rev38-receiver-test
cc -std=c99 -Wall -Wextra -Werror -pedantic protocol.c journal.c receiver.c runtime.c tests/test_runtime.c -o /tmp/temper-rev38-runtime-test
/tmp/temper-rev38-runtime-test
```

The journal test interrupts each of 64 erase/write byte calls for a single
reservation, then checks lockout or a strictly higher next ID. It also
rotates beyond two full rings and rejects a corrupted newest record. This
models byte-level failure, not an AVR NVMCTRL or brownout measurement.
The fuse test uses example bytes only. It rejects missing RESET, UPDI,
EESAVE, continuous BOD, OSCHF, or internal WDT. Its example 2.85 V BOD
level and 1 s WDT period are **not** selected operating values.
The receiver-core test checks fixed START expiry despite WDI progress, the
physical abort command on STOP and preparation trip, session ID advancement,
and dual-source WDI feed. A decoded START now enters `PE_RX_START_ARMED`
without a RUN pulse. `pe_receiver_commit_run` requires a new monotonic-clock
reading and physical input sample immediately before the adapter drives
the RUN-set pin; a queued write that reaches that point at or after the
REQUEST deadline aborts. The host test delays that commit through healthy
traffic and injects a fault after frame receipt. The target adapter must
still bound its sample-to-pin latency and rely on independent hardware
clear dominance if a trip coincides with the edge. All time windows in the
test are arbitrary logical
ticks; no numerical safety allowance follows from them.

The byte-stream interface distinguishes incomplete input from a malformed
complete frame or interrupted partial frame. `pe_receiver_byte` aborts the
attempt on an invalidating decoder result; `pe_receiver_stream_idle` detects
a partial frame that stalls with no next byte. The AVR loop must call the
idle entry point on its periodic tick and use the byte entry point for USART
data. Noise before a frame marker does not count as link progress. The host
tests exercise bad CRC and an idle gap through the receiver state machine.

`runtime.c` is the host-tested pin-sequencing boundary. Boot requests low on
every owned safety/pulse output and the relay output. Each preparation step
samples physical inputs afresh after the preceding output action; the
history reset and abort release are separated from the revalidation pulse.
The normal output path rejects a RUN-set request. Only `commit_run` can
issue that pulse synchronously after fresh samples and after checking a
configured sample-to-pin latency bound against the fixed deadline. The
fixture proves the requested call order, one RUN edge, late/fault
cancellation, and decoder idle abort. Its latency value is an arbitrary
host-test tick. A third clock/input sample now follows the final output
callback before RUN-set, because that callback can consume the remaining
START window; the host fixture forces this case. The AVR backend must prove
its real bound and pulse widths at the pins. The AVR loop counts a completed
receiver tick as local progress, sends numbered PINGs at its configured
interval, and checks the matching PONG before an external WDI pulse can be
requested. This policy needs target execution evidence. The runtime does not
yet drive the relay high. The USART adapter passes framing, parity, and
overrun flags to `pe_runtime_serial_error`, which requests physical abort
before parsing more bytes.

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
The partial hardware drives the permit-history D input low only when
physical disarm Q is high, RUN/PERMIT are low, preparation is healthy, and
receiver abort is still asserted. The adapter must hold those conditions
through the reset clock edge and verify the Q response; the source ACK is
checked in this core, not in the gate's D path.

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
4. Rebuild with the exact AVR64DA32 device toolchain after every adapter
   change, compare assigned physical pins to the joined Rev38 netlist, and
   inspect a programmed image plus fuse readback. Rebuild the present
   fuse-check revision before counting target compilation as passed.

No programmed AVR behavior or physical test is claimed by this record.
