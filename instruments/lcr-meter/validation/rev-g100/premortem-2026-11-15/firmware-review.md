# Independent firmware review of a12077019 (2026-11-15)

A fresh Fable agent reviewed the pre-mortem firmware change (`firmware-rev-e/src`, `test/`, `CMakeLists.txt`, `build.sh`, `validation/firmware-pins/firmware_pins_check.py`) on `study/lcr-rev-g100`. It was read-only, compiled the host tests in a scratch directory, and disassembled the committed ELFs. Its report is reproduced below with line references as of a12077019. The fixes are in [DISPOSITIONS.md](DISPOSITIONS.md), "Independent firmware review".

**Verdict: nothing blocking. One MAJOR to fix before first power, and five MINORs.**

Checked beyond reading the code:
- The host tests compile and pass.
- `bin/temper-lcr-rev-g.elf` calls `gpio_set_pulls(13, …)` in `main`, and nothing waits on the pin before `stdio_init_all`.
- All four ELFs carry their own BUILD name.

## MAJOR

**M1. A low-reading USB_SENSE still hides the console 100 ms after USB starts** (`main.c:753-768`)
- After 100 ms low, the loop calls `tud_disconnect()` and then blocks in `while (!gpio_get(PIN_USB_VBUS)) sleep_ms(10)` forever.
- 100 ms is too short to enumerate, and the heartbeat stops, so the board looks dead again: the class the commit set out to remove.
- The board is bus-powered only (J1 → U16), so a real VBUS loss powers the MCU off. This branch can only fire on a misread: R5 open, R6 short, or VBUS near 4.0–4.1 V.
- Fix: never drop USB on this pin. Silence the source, turn ISO off, re-initialise the guard, set a flag reported in STATUS, and keep the loop running.

## MINOR

**m1.** The debounce collapses to one sample after any long command (`main.c:744, 753-754`), because `vbus_high_ms` is not refreshed while `process_command` runs. Separately, `main.c:627` rejects a capture on one undebounced sample.

**m2.** The LCUR zero's "at most 0.9 V, under 1.05 V" bound is on the reading, not true volts.
- With sense error E, a fault F present at the close is hidden while |F + E| ≤ 900 mV. At E = −222 mV that is F ≈ 1.12 V, which can hold R43 slightly over 0.1 W on the 100 Ω range.
- Suggested fix: ZERO_MAX 300 and TRIP_LC 400 (normal AC after the filter is at most about 0.09 V), with the error term in the host CHECK.

**m3.** The rails are never re-checked at run time: `main.c:515` and `727` are the only writes to `analog_ok`. So "FORCE drops on a rail fault" and "the guard opens on a rail fault" cannot happen after boot.

**m4.** FORCE defeats every trip, with no indicator or expiry. After an in-capture trip, the next idle poll closes the switches again.
- Suggested fixes: light FAULT while forced, expire after about 30 s, and refuse captures while forced.

**m5.** The `firmware_pins_check.py` gate is textual and can pass falsely:
- it matches inside comments and `#if 0` blocks, and a call placed after the first read;
- it sees only the literal `gpio_get(PIN_X)`;
- it checks the source, not the binaries.

It does catch the exact regression. Suggested fixes: strip comments, require the call before the first read, and assert that the ELF calls `gpio_set_pulls` with r0 = 13.

## NOTES (no action)

- **Zero arithmetic and state are clean.** The sum is int64, `zero_n == 0` is handled, each close resets it, and init on VBUS loss clears it. The open-jack float has decayed to about 18 mV at 60 ms.
- **A tone during the zero window** leaves tens of mV of zero error. Acceptable.
- **JACKS parsing:** no collisions with the `needs_analog` names. Malformed FORCE arguments fall through to `ERR command`.
- **The boot RESET on a rail fault is safe.** `stream_start()` has run, the buffers are zeroed, the DAC is off, and it adds about 100 ms before USB.
- **Timing:** the `jacks_check` bound is 29 iterations against at most 26 needed. The in-capture test is about 68 µs per 5 ms against a 4096-frame ring, and fits within the 375 kHz spare cycles.
- **RP2040-E5:** the workaround is off by default in SDK 2.2.0, and no enumeration-fix code is linked.
