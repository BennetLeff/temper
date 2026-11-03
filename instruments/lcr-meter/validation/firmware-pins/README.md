# Firmware pins against the board (2026-11-03)

`firmware_pins_check.py` traces every `PIN_*` in `firmware-rev-e/src/pins.h` through `cad/design.json` to the part it drives. `independent_check.py` already ties design.json to the built board, and `../pinout-ledger/` ties its pin maps to the datasheets. This check closes the last link, from the firmware to the design.

Run it with `python3 validation/firmware-pins/firmware_pins_check.py`. It writes `firmware-pins-check.json` and exits 1 on any finding.

**Result: 73 pass, 0 findings.**

| What | Result |
|---|---|
| GPIO → U1 pad → net | All 19 `PIN_*` land on the expected net. Every U1 GPIO with a net on it is claimed by pins.h, so no wiring is left that the firmware never drives. |
| RP2040 function select (datasheet 2.19.2, table parsed from `sources/new/RP2040-datasheet.txt`) | I2C0 SDA/SCL on GPIO 8/9 and UART0 TX/RX on GPIO 28/29 exist; `main.c` initialises `i2c0`. MON12/MON_N12 are ADC0/ADC1 (GPIO 26/27), which is what `rails_wait` reads. PIO side-set: FSYNC = BCLK + 1. |
| Relays | `relay.c` 100 / 5k / 100k → SET_LO / SET_MED / SET_HI → R78/R76/R102 → Q4/Q5/Q3 gates → the SET− coil of K1/K2/K3, which `design.json ranges` names for those ranges; each relay's NO1/NO2 reach that range's Rg/Rf. REF → Q6 → K4 SET−; RESET → Q2 → all four RST− coils. SET+/RST+ on VRLY. |
| LEDs | STATUS → R12 → D4 anode; FAULT → R118 → D20; HEARTBEAT → R117 → D19. Cathodes on GND, so all are active high. |
| Codec | I2S DIN/DOUT/BCLK/FSYNC and I2C SDA/SCL land on the TAC5112 pins of the same name. ADDR is on GND, which is address 0x50 (SLASF24A Table 7-72), matching the firmware. One 3V3 pull-up per I2C line. |
| Rail monitors | MON12: 100k/10k to GND, and `rails.c` scales by 11. MON_N12: 150k from −12 V and 10k to 3V3, which is the 160/150 formula in `rails.c`. |
| USB_SENSE | 100k/100k: VBUS 4.4 V gives 2.20 V (VIH 2.0 V), and 5.5 V gives 2.75 V. |

**Mutation tests,** run on scratch copies with `LCR_ROOT`:
- SET_HI and SET_LO swapped: 4 findings, including "100 ohm → K3, expected K1".
- Codec address 0x51: 1 finding.
- FSYNC on GPIO 12: 3 findings, covering the net, the unclaimed pad and the side-set.
