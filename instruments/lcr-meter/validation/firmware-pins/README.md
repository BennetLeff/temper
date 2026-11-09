# Firmware pins against the board (2026-11-03)

`firmware_pins_check.py` traces every `PIN_*` in `firmware-rev-e/src/pins.h` through `cad/design.json` to the part it drives. `independent_check.py` already ties design.json to the built board, and `../pinout-ledger/` ties its pin maps to the datasheets. This check closes the last link, from the firmware to the design.

Run it with `python3 validation/firmware-pins/firmware_pins_check.py`. It writes `firmware-pins-check.json` and exits 1 on any finding.

**Result: 73 pass, 0 findings** (Rev F). **Rev G (2026-11-09): 81 pass, 0 findings**, below.

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

## Rev G (2026-11-09)

The check now evaluates `pins.h`'s `#if` / `#else` blocks for the board it reads. `design.json`'s revision G selects the `LCR_REV_G=1` image; any other revision selects the default one (`LCR_FS_375K=0`). Before this change, the last `#define` of each name won, so a Rev G board was checked against a mix of the two images. The Rev G additions:

| What | Result |
|---|---|
| Build | Revision G: the Rev G pins are present and the UART header pins are absent. J6 is not on the board, and the UART function-select rows are skipped. |
| Jack senses | PIN_JACK_HC / PIN_JACK_LC are GPIO 28 / 29 = ADC2 / ADC3, and `main.c` reads `rail_sum(PIN_JACK_x - 26u)`. Each divider is R_TOP from the CUR jack (JK_HCUR, JK_LCUR), R_BIAS to 3V3, R_GND to GND and one C to GND. R_TOP × G and R_TOP / R_BIAS, × 10⁶, are computed from `design.json` values and equal `jackguard.h`'s `JG_RTOP_G_PPM` / `JG_RTOP_RBIAS_PPM` (13 500 000 / 6 250 000). |
| Isolation drive | PIN_ISO_DRIVE → R134 → ISO_G → Q7 gate, with R135 to GND as the pull-down. Q7's source is on GND and its drain is ISO_SINK. ISO_SINK is the cathode end of both two-LED strings, (U18, U19) and (U21, U20), and each string is fed from VRLY by one resistor (R132, R133). All four photoMOS are in a string. |
| Isolation switches | Each photoMOS has one drain on a jack net, and together they cover JK_HCUR, JK_HPOT, JK_LPOT and JK_LCUR. |

**Mutation tests** (scratch copies, `LCR_ROOT`):

| Mutation | Result |
|---|---|
| `JG_RTOP_G_PPM` back to the 1 MΩ divider's value | 2 findings, one per sense |
| R135 to 3V3 | 1 finding (no gate pull-down) |
| U20's LED reversed | 1 finding (the string stops at U21) |
| Revision F on the Rev G board | 3 findings (UART pins on JACK_HC / JACK_LC; GPIO 15 unclaimed) |

