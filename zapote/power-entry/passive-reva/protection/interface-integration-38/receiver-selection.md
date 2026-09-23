# Rev38 HOT receiver selection and protocol contract

Status: **engineering selection for the joined candidate**. Select
`AVR64DA32-E/PT` (Microchip, 32-pin TQFP, −40 to +125 °C). The manufacturer
marks AVR64DA32 In Production and lists the exact `-E/PT` ordering code.
This supersedes Rev35's ATmega328P fixture identity; it does not qualify the
HOT rail, EEPROM under power interruption, or any gate-timing path.

## Why this part fits the receiver role

The complete data sheet lists 64 KiB Flash, 8 KiB SRAM, 512 B EEPROM,
USARTs, internal high-frequency clock up to 24 MHz, POR, BOD, and a watchdog.
The 32-pin package exposes USART0 on PA0/PA1, at least the 12 other digital
signals allocated below, a dedicated UPDI pin, and a RESET pin. The EEPROM
is for a durable high-water session counter. The internal watchdog checks
receiver execution; the external HOT TPS3431 and physical latch clear remain
the protection path. The MCU never drives UCC27624 EN directly and cannot
reload HOT fault memory with an ordinary START.

Use the internal OSCHF initially. Final USART baud, clock accuracy across
supply/temperature, timer tick error, and START deadline must be checked
against the selected clock setting. If the internal clock cannot close those
bounds, fit a specified external timing source; do not silently widen the
command deadline. Configure BOD for continuous supervision, but keep the
external rail supervisor and default-low abort path responsible for the
unsafe intermediate-supply region. Fuse values and BOD threshold corners
belong to the U4 electrical review and U5 programmed-image receipt.

## Candidate pin and isolation contract

Physical numbers below are for the **32-pin TQFP** from Microchip's I/O
multiplexing table. U4 must recheck the saved symbol, footprint, and compiled
netlist against the manufacturer package, including supply, RESET, and UPDI.
The PT package outline is a 7 × 7 mm body at 0.80 mm lead pitch; candidate
KiCad footprint `Package_QFP:TQFP-32_7x7mm_P0.8mm` still needs land-pattern
comparison against Microchip's package drawing before native acceptance.

| Pin | MCU pad | Direction / function | Physical rule |
| ---: | --- | --- | --- |
| 30 | PA0 | USART0 TX, receiver response | Separate reverse isolated protocol channel; its idle level has no safety meaning. |
| 31 | PA1 | USART0 RX, source command | Forward isolated command; a stale frame cannot reload hardware fault memory. |
| 32 | PA2 | HOT relay-command output | System-control request; no PFC gate authorization from this signal. |
| 1 | PA3 | HOT permit-seen Q readback | Confirms historical high-PERMIT memory was cleared before revalidation; the memory also enters the asynchronous HOT clear equation. |
| 2 | PA4 | Preparation-abort memory reset request | Separate bounded edge pulse, completed before challenge publication; never clears a new trip during the pending attempt. |
| 10 | PD0 | Physical HOT PERMIT sense | Reads the HOT-side conductor, never only an MCU mirror. |
| 11 | PD1 | `HOT_SESSION_OK` Q sense | Required before READY and RUN-set; sensing is not a substitute for asynchronous clear. |
| 12 | PD2 | `HOT_RUN` Q sense | Confirms disarm and detects mismatch. |
| 13 | PD3 | `RECEIVER_ABORT_N` output | External HOT pull-down asserts both latch clears while reset, unpowered, or high impedance; MCU drives high only after boot qualification. |
| 14 | PD4 | One-shot revalidation request | Hardware consumes one edge; a held output cannot become a later clock after fault recovery. |
| 15 | PD5 | RUN-set request | Hardware gates the edge with current validity, PERMIT, deadline and fault-clear dominance. |
| 16 | PD6 | Qualified external watchdog WDI | One firmware owner, no timer/DMA/autonomous pulse source. |
| 17 | PD7 | HOT rail-good observation | Cannot replace external rail inhibit/POR. |
| 6 | PC0 | Physical disarm-seen input | Reads hardware memory of post-trip PERMIT low. |
| 7 | PC1 | Preparation-abort memory input | New trip during preparation cancels pending ID even when session Q is already low. |
| 8 | PC2 | Hardware fault summary input | Diagnostic only; each critical producer still clears the latches physically. |
| 9 | PC3 | HOT permit-seen history reset request | Separate bounded edge pulse after matching DISARM_ACK and before revalidation, with physical PERMIT and RUN low. It must not clear preparation-abort memory. |
| 26 | PF6 | RESET input | Keep reset enabled; external POR/rail path asserts it. |
| 27 | UPDI | Programming/debug | Reserve for production programming and fuse verification. |

Pins 18 (AVDD), 19 (GND), 28 (VDD), and 29 (GND) are supplies. Other GPIOs
remain unassigned and are not credited as fault producers. The active-low
abort output is deliberately **not** released merely because the MCU boots;
it waits for rail, storage, physical disarm, and session checks. The local
pull-down and intermediate-supply behavior need a corner calculation with
the actual latch/isolator input loading.

## Durable session high-water record

Use 16 logical 32-byte slots in the 512-byte EEPROM. The host-tested
`receiver-firmware/journal.c` format is: bytes 0–3 `54 50 45 01`, bytes
4–11 the 64-bit high-water ID little endian, bytes 12–19 its complement,
bytes 20–23 CRC-32/ISO-HDLC over bytes 0–19, bytes 24–30 `FF`, and byte 31
the final `3C` commit marker. Manufacturing provisions ID zero in slot zero
once. Runtime code has no provision-blank path. The newest ID and physical
slot advance together modulo 16; scan rejects duplicate, gapped, or
out-of-order records.

Provision a valid initial high-water record during manufacturing. A fully
blank, ambiguous, exhausted, or corrupt store is **LOCKOUT**, never an
invitation to restart the counter at one. On boot, scan every slot. A slot
is either erased, completely valid, or corrupt. Any corrupt non-erased slot
locks out; among valid slots use the highest identifier and reject duplicates
or ordering ambiguity. Do not wrap the counter. The lifetime policy must
stop reservation before the EEPROM's specified per-byte endurance is used;
no field replacement may reset the identity without a controlled new epoch.

To reserve the next identifier, keep abort asserted and RUN low; choose a
slot that does **not** hold the current maximum, erase/write its bytes in the
documented NVM sequence, wait for completion, read back the full record and
rescan all slots. Only after the new maximum is uniquely valid may the MCU
publish PREPARE_CHALLENGE. A reset before verification exposes no new
challenge; a completed but unpublished reservation only skips a number.
A torn record that is neither erased nor valid leaves the receiver locked
out. The power-fail test must interrupt every byte/command boundary and
confirm that no identifier ever published can reappear after reboot.
The external abort stays asserted throughout all EEPROM operations.

The candidate software ceiling is ID 16,000, limiting each rotating slot to
roughly 1,000 overwrite cycles from manufacturing ID zero. That is a
conservative development policy, **not** a qualified endurance calculation:
the exact data-sheet limit at the selected temperature, NVM write-completion
semantics, brownout behavior, and field-use budget still need target review.

This scheme assumes a completed, verified EEPROM write retains its bits
under the specified supply and endurance conditions. A later arbitrary
bit loss of the maximum record is not proven impossible by CRC. Such a
condition is treated as storage failure and requires a separate hardware
or provisioning policy rather than a claimed fail-safe recovery.

## Wire and state rules for U3/U5/U6

- A frame is exactly 20 bytes, using the common `receiver-firmware/protocol.h`
  and `.c` codec: `A5` magic, version `01`, one-byte type, reserved zero byte,
  64-bit session ID little endian, 32-bit intent or sequence little endian,
  and CRC-32/ISO-HDLC little endian over bytes 0–15. UART is 8N1. Baud and
  clock-error budget remain open until the selected clock is qualified. CRC
  detects accidental corruption; it is not authentication. A decoder must
  discard incomplete and malformed frames and resynchronize on `A5`, never
  feed liveness for them.
- `PREPARE_CHALLENGE(id)` is sent only after a separate preparation-abort
  reset, durable reservation, and a fresh physical disarm/trip-memory sample.
  `DISARM_ACK(id)` is accepted only while that ID is pending and hardware
  remains safe. It requests a separate HOT permit-seen reset, which must be
  verified at its Q pin without erasing preparation-abort memory. A new trip,
  STOP or receiver reset discards the attempt.
- `READY(id)` follows one consumed revalidation and Q readback. The ESP
  observes a new button release/press, asserts PERMIT, verifies local and
  physical readback, then sends `REQUEST(id,intent)`.
- The receiver accepts one outstanding intent and starts a fixed monotonic
  deadline at REQUEST acceptance. `ACK(id,intent)` echoes it. `START(id,intent)`
  may issue exactly one RUN-set request only before that deadline and while
  the current hardware inputs remain valid. Acceptance consumes the intent;
  duplicate, cancelled, prior-session and late frames abort without RUN-set.
- Fresh numbered bidirectional liveness traffic is separate from local
  safety-loop progress. READY and RUNNING require both. Repeated traffic,
  malformed traffic, and mere USART activity do not feed either watchdog or
  extend the START deadline.
- `STOP` in READY, RUNNING or preparation drives `RECEIVER_ABORT_N` low,
  clears both retained latches physically, and discards all pending IDs and
  intents. Receiver reset or loss of its rail has the same external default.
- The source may have committed one START before an unexpected CPU-only reset.
  The receiver does not infer a reset from unchanged wires: that one frame
  may set RUN before expiry. The independent source watchdog still owns the
  original reset-to-off deadline. Rebooted source code must not send a second
  copy or re-service its WDI before physical disarm and a new session.

The executable model and target firmware must implement these rules. This
document assigns no numerical preparation, START, link-loss, or reset-to-off
time; those remain in `timing-analysis.md` until independently derived.

## Primary manufacturer evidence

- [AVR64DA32 product status](https://www.microchip.com/en-us/product/avr64da32)
- [AVR64DA28/32/48/64 complete data sheet](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/AVR64DA28-32-48-64-DataSheet-DS40002233.pdf), including ordering, BOD, NVMCTRL, clock and memory characteristics
- [32-pin I/O multiplexing table](https://onlinedocs.microchip.com/oxy/GUID-39CA96AF-092A-488F-B367-D24555D1E9C7-en-US-12/GUID-A7F733C9-DB47-4648-90B3-75618ED282E0.html)
- [Microchip PT package outline](https://ww1.microchip.com/downloads/aemDocuments/documents/package-outline-drawings/c04-00074d.pdf)
