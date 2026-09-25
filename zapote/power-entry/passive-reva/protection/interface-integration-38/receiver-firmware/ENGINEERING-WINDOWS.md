# AVR64DA32 engineering timing profile

**Status: offline target-build candidate, not a safety-time limit or a
programming instruction (2026-09-24).** `PROFILE=locked` remains the default
and retains zero protocol windows and impossible default fuse expectations.
`PROFILE=engineering` compiles the active receiver branches with a named
nonzero parameter set and the review-only fuse bytes from
`../AVR-FUSE-SCREEN.md`. The target has not been programmed or run.

## Communication budget used to choose test parameters

The fixed frame is 20 bytes and USART0 is configured for 115,200 bit/s,
8N1. One uninterrupted frame occupies `20 × 10 / 115200 = 1.736 ms` on
the wire; one request/response pair occupies at least 3.472 ms before any
source/receiver processing, queueing, I²C reads, EEPROM work, interrupt
latency, or clock/baud error. A 1 ms TCB tick quantizes deadlines. These
are *lower bounds* on transport time, not worst-case software latency.

| Parameter | Engineering value | Reason for this offline exercise | Missing acceptance input |
| --- | ---: | --- | --- |
| Byte gap | 10 ms | Greater than a whole nominal 1.736 ms frame, so host-driven interbyte pauses can exercise the invalidating gap path. | Maximum UART ISR/poll latency, interrupt masking and clock error; a 10 ms gap is not an accepted fault allowance. |
| Ping period | 20 ms | About 11 nominal frame times; generates multiple link-progress cycles before the candidate 75 ms receiver liveness check. | Worst source scheduling and PONG round trip, including I²C/UART ownership. |
| Receiver liveness window | 75 ms | Allows three 20 ms ping intervals plus 15 ms illustrative processing slack. It is shorter than the HOT TPS3431's earlier ideal-1-nF 119.82–144.98 ms device screen, but that screen is not an installed limit. | Guaranteed HOT watchdog and receiver clock/loop corners; independently allowable continued operation. |
| Preparation window | 250 ms | Wide enough for several nominal 3.472 ms frame pairs and EEPROM reservation in a protocol-development fixture. | Bounded EEPROM erase/write, physical disarm/readback, source scheduling and hazard-derived preparation allowance. |
| START window | 100 ms | Wide enough for nominal ACK/START exchange plus fixture scheduling; shorter than the preparation test window. | Exact last-bit-to-RUN path, queueing and independent first-start allowable time. |
| Sample-to-RUN pin bound | 5 ms | Permits target compilation of the fresh-sample check with one millisecond tick granularity. | Maximum sample latency, instruction/interrupt delay and loaded physical RUN clock arrival. |

The 15 ms ping slack and the 250/100/5 ms windows are **test hypotheses**.
They were not measured on the cooker ESP or AVR. Nothing in this table may
replace a hazard-derived allowable time, a verified installed-device
maximum, or the F2/VD conditional timing screen. The selected contract
permits a finite proven post-reset WDI feed tail; that tail is still
unbounded in `../timing-analysis.md`.

The engineering build expects fuse bytes `WDTCFG=0x05`, `BODCFG=0x65`,
`OSCCFG=0x00`, `SYSCFG0=0xC9`; source startup compares those exact bytes.
`AVR-FUSE-SCREEN.md` explains why their actual device behavior remains
unqualified. A blank or factory-fused part stays in lockout. This profile
also requires a provisioned, valid session journal and all physical safety
inputs before authorization. It has no special bypass of those checks.

## Build receipt and pin review

Microchip AVR 8-Bit Toolchain 4.0.0.52, avr-gcc 15.1.0, linked both
`PROFILE=locked` and `PROFILE=engineering` on 2026-09-24 with `-Wall
-Wextra -Werror -Wpedantic` for `-mmcu=avr64da32`:

```sh
make -f avr64da32.mk PROFILE=locked \
  AVR_GCC=/tmp/avr8-gnu-toolchain-darwin_universal/bin/avr-gcc \
  AVR_SIZE=/tmp/avr8-gnu-toolchain-darwin_universal/bin/avr-size
make -f avr64da32.mk PROFILE=engineering \
  AVR_GCC=/tmp/avr8-gnu-toolchain-darwin_universal/bin/avr-gcc \
  AVR_SIZE=/tmp/avr8-gnu-toolchain-darwin_universal/bin/avr-size
```

The locked ELF measured 16,050 text / 0 data / 8 BSS bytes, SHA-256
`4e5f8cdc72b749e41dd348de25343a01dcb833825e81b3586eeb9f60da916596`.
The engineering ELF measured 16,594 text / 0 data / 8 BSS bytes, SHA-256
`f7b13f821114a661ef2a83b50cab1c896e63a8f46030022626fa13113e1925bf`.
These identities cover compiler output for the current source and profile;
the ELF files are temporary, not release artifacts.

`avr64da32_target.c` initializes PA2/4/6, PC3, PD3/4/5/6 and PF1 output
latches low before enabling drivers. Its `output_port()` and `sample()`
mappings agree with the named AVR pads and physical TQFP-32 pin table in
`../receiver-selection.md`: PA0/PA1 USART0; PA2 relay; PA4 prep reset;
PA6 attempt valid; PC3 seen reset; PD3 abort; PD4 revalidate; PD5 RUN;
PD6 WDI; PF1 disarm sample; PD0/1/2/7, PC0/1/2, PA3 and PF0 feedback.
The compiled `source-build-05` receiver net and BOM are checked by the
145-case Rust pin audit, including deliberate pin/net mutations. This is
a source/netlist review, not a PCB land, device pin-state, or reset capture.

U5 remains **OPEN** until the timing inputs, exact programmed fuse
readback, target clock/UART and reset behavior, output pin captures, and
physical latch action have evidence appropriate to their acceptance gate.
