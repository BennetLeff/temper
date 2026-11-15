# G100 pre-mortem: dispositions (2026-11-15)

The pre-mortem ([PREMORTEM.md](PREMORTEM.md)) was run by an independent Fable agent on board `49ba0a39…d716` at 1ea381450. Its verdict: **order now, copper unchanged.** Every recommendation in its §4 (a) is done below, and none touches the board. The board hash and Gerber zip are unchanged.

## Firmware (`firmware-rev-e`)

| Item | Disposition | Evidence |
|---|---|---|
| 1. USB_SENSE: pad pull-down halves the level (critical) | **Fixed and confirmed.** The RP2040 datasheet's PADS_BANK0 table gives "PDE: Pull down enable RW 0x1" (reset on) and RPD 50–80 kΩ. pico-sdk 2.2.0's `gpio_init()` (gpio.c:273) does not touch the pulls. So with R5 / R6 100 k / 100 k the pin sat at 1.10–1.54 V, against VIH 2.0 V, and `main()` waited on it before `stdio_init_all()`: every board would have looked dead. `main()` now calls `gpio_disable_pulls(PIN_USB_VBUS)` (2.20 V at VBUS 4.40 V) and starts USB without waiting on the pin. In the loop, a VBUS loss must last 100 ms (`VBUS_LOSS_MS`), so a dip does not drop the host. The same bug is in every image built from this source before today, Rev E and Rev F included. | The disassembly shows `movs r0, #13; bl gpio_set_pulls` in the new image and no such call in the old one. |
| 1. Gate for the class | **Added.** `validation/firmware-pins/firmware_pins_check.py` now reads the PDE reset value and RPD from the datasheet text. It computes USB_SENSE with the strongest pull-down unless `main.c` disables it, and fails any pin read with `gpio_get()` whose pulls the firmware does not set (ADC pins are exempt, since `adc_gpio_init()` disables them). | With the fix removed, the check reports 2 findings (`usb sense` 1.10 V; `input pulls` PIN_USB_VBUS). With the fix, 83 pass, 0 findings. |
| 2. Jack-sense error against the 0.5 V LCUR trip | **Fixed.** (a) LCUR zero: each close averages LCUR from 60 ms to 100 ms after closing. LCUR is then the TIA's virtual ground, so the reading is the sense's own error. The mean is clamped to ±400 mV and subtracted before the 0.5 V test. The clamp keeps a fault present at the close at 0.9 V or less, under R43's 1.05 V (G-AFE-01). A stored per-board zero was not needed. (b) The in-capture test averages 16 conversions per jack, after one discarded, about 70 µs per 5 ms. (c) `JACKS FORCE 1\|0` (bring-up only, needs the rails up, cleared on VBUS loss and reset). `JACKS` now also reports the zero and the force flag. Captures wait 100 ms after a close instead of 40. | `test/test_host.c`: a +450 mV board (clamped zero, stays closed, 1.0 V trips), a −250 mV board, a 0.8 V and a 1.0 V fault present at the close, and a fresh zero on each close. PASS in all four builds. |
| 4. RP2040-E5 fix on GPIO15 | **No change: the finding does not hold.** In SDK 2.2.0 `TUD_OPT_RP2040_USB_DEVICE_ENUMERATION_FIX` is undefined unless `PICO_RP2040_USB_DEVICE_ENUMERATION_FIX` is set (rp2040_usb.h:16; tinyusb CMakeLists "off by default"), so `dcd_rp2040.c:306` never calls the fix. `rp2040_chip_version` is linked for other reasons. | `arm-none-eabi-nm` finds no `rp2040_usb_device_enumeration_fix` in any image. |
| 9. Boot RESET even on a rail fault | **Done.** On a rails timeout, `main()` still runs `select_relays(100000, false, true)`: VRLY comes from 5 V, and K4 with R107 is on the jack side of the switches. | `main.c` |
| 10. No Rev G 375 kHz image | **Built.** `build.sh` makes four images. `bin/temper-lcr-rev-g-375k.uf2` (FS 375 kHz, `LCR_REV_G=1`) has the hot-loop bound of 209 against a 288-cycle budget. | `verification/hot-loop.txt`, `uf2.txt` |
| Image identity (respin list) | **Done in firmware.** A new `BUILD` command replies `BUILD <image> <fs> <rev_g>`, since `INFO` says `E-codec` in every image. It is additive and the host does not send it. | `strings` on each ELF shows its own image name. |
| 10. No watchdog | **Backlog.** A watchdog first run on an untested board risks reboot loops: the stdout timeout is 5 s and captures run up to 60 s. Revisit after first light. | — |
| 6. DVDD droop fallback | **Recorded** as a bench fallback (`vreg_set_voltage(VREG_VOLTAGE_1_20)`), not applied blind. | PREMORTEM.md §3 |

## Bring-up (`docs/bring-up-rev-g.md`, "G100 first power")

| Item | Disposition |
|---|---|
| 8. Fit J4 and have a CMSIS-DAP probe | Added (before first power, board 1). |
| 3. Codec asleep with ±12 V up | Added: scope C60 on the first blank power-up, before the other boards; above 3.9 V, stack 1 kΩ on C61. |
| 9. K4 latched on the jack side | Added: nothing on the jacks until `INFO` says PASS. |
| 10. Stale test-pad table | Added: the G100 table (TP1–TP22) read from the board, with a pointer from bring-up-rev-e.md §1. |
| 2. G2 / G4 had no command | G2 and G4 use `JACKS FORCE 1 / 0`; G5 records the LCUR zero. |
| Spares | Listed with each part's use. R83's trim value is left to the bench: the pre-mortem's "same trim" does not apply, because R83 is 240 k, not 430 k. |
| `BUILD` check after flashing | Added. |

## Not done, by decision

- **(b) Pareto copper changes:** the pre-mortem found none.
- **(c) trades** (Schottky 3V3A → 3V3, UART / trigger pads, snubber lands, R5 / R6 10 k): on the respin list in `docs/rev-g100-plan.md`. R5 / R6 10 k is rejected: with RPD 50 k it gives 2.0 V at VBUS 4.40 V, no margin, and the firmware fix is better.
