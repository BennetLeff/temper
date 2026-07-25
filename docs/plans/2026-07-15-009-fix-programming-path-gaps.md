---
title: "fix: ESP32 programming path and remaining P1 gaps"
type: fix
status: completed
date: 2026-07-15
origin: docs/audits/2026-07-15-atopile-electrical-design-audit.md
depends_on: []
blocks: []
swept: 2026-07-25
swept_basis: "already declared"
---

## Shipped

**Merged in [PR #214](https://github.com/BennetLeff/temper/pull/214) on 2026-07-16.** The fix for this plan shipped as part of the comprehensive atopile audit remediation (`fix(elec): resolve 8 P0/P1 electrical design bugs from atopile audit`). See the PR body's per-plan table for the specific changes attributable to this plan.

# fix: ESP32 Programming Path and Remaining P1 Gaps

## Summary

The ESP32-S3 module is unprogrammable via any standard method, and several
remaining P1 gaps block normal operation:

1. **P1-3:** GPIO19 (USB D-) and GPIO20 (USB D+) — the native USB OTG pins —
   are consumed as `relay_ctrl` and `fault_status_in` respectively. No IO0
   bootstrap circuit exists. No UART header exists. The board ships
   unprogrammed with no way to flash it.
2. **P1-4:** I2C bus (IO38/IO39) has no pull-up resistors and no connected
   peripherals in the `.ato` source. The entire UI exists only in the hand-
   drawn `pcb/user_interface.kicad_sch` — a source-of-truth split that means
   the generated netlist has no UI.

Both items are non-destructive but block any functional testing — you can't
program a board you can't talk to, and the I2C bus can't communicate without
pull-ups.

## Problem Frame

### P1-3: No programming path

**Current GPIO assignment (confirmed from `modules.ato`):**

| GPIO | Function | Native Role |
|------|----------|-------------|
| 19 | relay_ctrl | USB D- |
| 20 | fault_status_in | USB D+ |
| 0 | — (unused? check) | Boot strap (low = download mode) |

**Why this blocks programming:**
- USB D-/D+ (GPIO19/20) are the *only* native USB interface on the
  ESP32-S3-WROOM-1 module. They can't be both a USB port and GPIO outputs
  simultaneously.
- GPIO0 must be held low at reset to enter the ROM bootloader (download
  mode). Without an IO0 bootstrap circuit (button + pull-up, or auto-
  program circuit with DTR/RTS from USB-UART), the chip boots from flash
  and never enters programming mode.
- No UART header exists as a fallback (TX/RX on any GPIO pair).

**Fix options:**
- **Option A — Free USB D+/D-:** Move `relay_ctrl` and `fault_status_in` to
  different GPIOs. Add a USB-C or micro-USB connector on GPIO19/20. Use the
  ROM bootloader (native USB serial, no external UART chip needed). Requires
  IO0 bootstrap button or auto-program circuit.
- **Option B — Add UART header:** Keep GPIO19/20 as GPIOs. Add a USB-UART
  bridge (CP2102, CH340, FT232) with the auto-program circuit (DTR→EN,
  RTS→IO0 through 0.1µF caps). More components but leaves more GPIOs free.
- **Option C — Pre-programmed modules:** Order ESP32-S3-WROOM-1 modules
  pre-programmed from the supplier. Still need a programming header for
  firmware updates.

**Recommended:** Option A — free USB pins, add USB connector and IO0
bootstrap. Minimal additional BOM (USB connector, two buttons, two
capacitors for auto-reset). This is the standard ESP32-S3 dev board
approach.

### P1-4: I2C bus with no pull-ups, no peripherals

**Current state:**
```ato
# modules.ato — MCU module declares I2C on GPIO38/39
# No pull-up resistors exist in any module
# main.ato — I2C bus never connected to any peripheral
```

I2C requires pull-up resistors (typically 2.2k-4.7k to 3.3V) on both SDA
and SCL. Without them, the open-drain lines float and communication is
impossible. The bus is also declared but never connected to any I2C device
in the `.ato` source — the UI (OLED/LCD, rotary encoder with I2C expander)
only exists in the hand-drawn schematic.

**Fix:**
- Add 4.7k pull-up resistors to 3.3V on IO38 (SCL) and IO39 (SDA)
- Define the UI components in `.ato` source and instantiate them
- Or, if the UI is intentionally external (off-board module on a ribbon
  cable), add a connector with the I2C lines, 3.3V, and GND

### GPIO reassignment

**Current safety-critical GPIOs (must not change):**

| GPIO | Function | Note |
|------|----------|------|
| 6 | watchdog_in | Safety — keep |
| 7 | watchdog_kick | Safety — keep |
| 14 | reset_req_in | Safety — keep |
| 15 | runaway_cut | Safety — keep |
| 1 | adc_i_sense | ADC1 |
| 2 | adc_v_bus | ADC1 |
| 3 | adc_ntc | ADC1 |
| 4 | adc_rtd | ADC1 |
| 5 | shutdown | Safety — keep |
| 8 | pwm_h | PWM |
| 9 | pwm_l | PWM |
| 10 | rtd_cs | SPI CS |
| 11 | rtd_mosi | SPI MOSI |
| 12 | rtd_miso | SPI MISO |
| 13 | rtd_sck / zcd_in | SPI SCK |

**Pins to free for USB:**
- GPIO19 (relay_ctrl) → move to e.g., GPIO16
- GPIO20 (fault_status_in) → move to e.g., GPIO17

**Available GPIOs on ESP32-S3-WROOM-1:**
Check the pin map at `modules.ato:1225-1260` for unused pins. The module
has 36 GPIOs on the castellated pads; many are currently unused.

## Scope Boundaries

### In scope
- Free GPIO19/20 by moving relay_ctrl and fault_status_in to other pins
- Add USB connector, IO0 bootstrap circuit (button + pull-up + RC auto-reset)
- Add I2C pull-up resistors
- Define UI components (OLED/LCD, encoder) in `.ato` source OR add an I2C
  expansion header for off-board UI
- Update `elec/src/main.ato` with the new connections
- Verify no GPIO collisions after reassignment

### Deferred
- UI firmware (the display, buttons, and encoder firmware)
- USB firmware (TinyUSB stack for ESP32-S3)
- Bootloader configuration

### Out of scope
- Enclosure design for the USB connector and programming button
- Production programming fixture

## Implementation Units

### U1. Free USB pins (GPIO19/20)

**File:** `elec/src/modules.ato` — MCU module

```diff
-    signal relay_ctrl          # GPIO19
-    signal fault_status_in     # GPIO20
+    signal relay_ctrl          # GPIO16 (or next available)
+    signal fault_status_in     # GPIO17 (or next available)
```

Update the pin assignment comments/attributes to reflect the new GPIO
numbers.

### U2. USB connector and bootstrap circuit

**File:** `elec/src/modules.ato` — a new `USBBootstrap` module or add to MCU module

```ato
module USBBootstrap:
    # USB-C connector (or micro-USB)
    usb_conn = new USB_C_Receptacle  # or MicroUSB
    
    # IO0 bootstrap: button + 10k pull-up to 3.3V
    # Pressing button pulls IO0 to GND → enters download mode on reset
    boot_button = new TactileSwitch
    r_boot_pullup = new Resistor with value = 10kohm
    
    # Auto-reset circuit (for esptool auto-programming):
    # EN pin: 10k pull-up to 3.3V, 0.1µF from DTR (via USB-UART)
    # IO0: 0.1µF from RTS (via USB-UART)
    # For native USB ROM bootloader, EN reset button is sufficient
    
    # EN (reset) button
    reset_button = new TactileSwitch
    
    usb_conn.DP ~ mcu.usb_dp    # GPIO20
    usb_conn.DN ~ mcu.usb_dn    # GPIO19
    usb_conn.VBUS ~ (5V rail or not connected for bus-powered)
    usb_conn.GND ~ gnd
```

**File:** `elec/src/main.ato` — instantiate and wire

### U3. I2C pull-ups

**File:** `elec/src/modules.ato` — MCU module or a new I2CBus module

```ato
r_sda_pullup = new Resistor
r_sda_pullup.value = 4.7kohm
r_scl_pullup = new Resistor
r_scl_pullup.value = 4.7kohm

power.vcc ~ r_sda_pullup.p1
r_sda_pullup.p2 ~ i2c_sda

power.vcc ~ r_scl_pullup.p1
r_scl_pullup.p2 ~ i2c_scl
```

### U4. UI components in .ato source

**Goal:** Bring the UI into the ato source of truth so the generated
netlist includes it. The hand-drawn `pcb/user_interface.kicad_sch` should
be considered stale after this.

**Minimum UI for testing:**
- I2C OLED display (SSD1306, 128x64) — standard module available as a
  component or connector
- Rotary encoder with pushbutton (for temperature/power adjustment)
- Or: three tactile buttons (up/down/select) as a simpler alternative

**File:** `elec/src/components.ato` — add component entries
**File:** `elec/src/modules.ato` — add UserInterface module
**File:** `elec/src/main.ato` — instantiate and wire to MCU I2C bus

## Test Strategy

1. **GPIO collision check:** Run the firmware pin contract test
   (`firmware/test/`) against the new `.ato`-derived pin map. Verify no
   two functions share a GPIO.

2. **USB enumeration:** Plug the assembled board into a computer via USB.
   Verify the ESP32-S3 enumerates as a USB serial device (or enters
   download mode when IO0 is held low).

3. **Programming:** Flash a test firmware (blink an LED driven by an unused
   GPIO, or output a test pattern on the PWM pins at low duty cycle).
   Verify successful programming and execution.

4. **I2C scan:** With an I2C OLED or any I2C device connected, run an I2C
   scanner firmware to confirm the device is detected at its address.
   Verify pull-ups produce clean rising edges (scope SCL/SDA).

5. **Bootstrap:** Hold IO0 low, press EN (reset), verify the ROM bootloader
   mode is entered (USB enumerates as a download device).

## Open Questions

1. **USB connector type:** USB-C (modern, reversible) or micro-USB
   (ubiquitous, simpler routing)? USB-C requires 5.1k CC resistors;
   micro-USB is 4 pins. For a prototype, micro-USB is simpler.
2. **UI strategy:** On-board OLED + encoder (self-contained) or off-board
   via I2C connector (flexible for prototyping)? An I2C header (4-pin:
   GND, VCC, SDA, SCL) is minimal and allows connecting any I2C display
   module.
3. **5V from USB:** Should the board be USB-powered for programming
   (without mains)? The 3.3V buck needs input — if the aux supply (plan
   005) is absent during programming, a diode-OR from USB 5V to the 3.3V
   buck input could power the MCU for flashing only.

## References

- Master audit: `docs/audits/2026-07-15-atopile-electrical-design-audit.md`
- ESP32-S3-WROOM-1 datasheet: pin layout, strapping pins, USB interface
- `elec/src/modules.ato:1225-1280` — MCU module pin assignments
- `firmware/test/` — GPIO collision contract tests
