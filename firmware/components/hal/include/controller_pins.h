#ifndef TEMPER_CONTROLLER_PINS_H
#define TEMPER_CONTROLLER_PINS_H
/*
 * Integrated SELV controller (zapote/controller) pin map: the single source of truth for every
 * ESP32-S3 GPIO, ADC1 channel and TCA9555 expander bit the firmware uses on this board.
 *
 * Source: branch controller-layout, zapote/controller/elec/src/controller.ato (U4 "GPIO map" and
 * U8 expander blocks), DECISIONS C2, C3, C20, C23 (RUN_EN), C26 (R33 UI bus), C27 (R36 rim NTC)
 * and C28 (L3 blower). Layout L2 = R33 rebase + R36 rim NTC; the L3 schematic delta (blower PWM
 * on GPIO46, FAN_OFF on expander P15) is included and marked L3.
 *
 * Naming rule (checked by firmware/tools/check_controller_pinmap.py against the ato):
 *   CTRL_GPIO_<NET>  = GPIO number of the ato net <net> on the module (mcu.IOn / RXD0 / TXD0)
 *   CTRL_EXP_<NET>   = TCA9555 bit of the ato net <net>, 0..15 (Pxy -> 8*x + y)
 *   CTRL_ADC1_CH_<NET> = ADC1 channel of an analog net (ESP32-S3: GPIOn -> ADC1_CH(n-1))
 * Only numeric defines take part in the cross-check; aliases are defined from them.
 *
 * This is NOT the legacy elec/ board map (temper_pins.h), which stays unchanged for the tools
 * that read it. Controller firmware must not include temper_pins.h.
 *
 * Strap pins (ESP32-S3 DS Table 2-1; checked by firmware/test/test_controller_pins.c):
 *   GPIO0  I2C SCL. 4.7 k external pull-up holds SPI boot (1). Open-drain only, never an
 *          internal pull-down; the debug header may pull it low for download.
 *   GPIO3  Blower tach input. JTAG-select strap only with the STRAP_JTAG_SEL eFuse burnt (never).
 *   GPIO45 UI OLED D/C. 100 k external pull-down: VDD_SPI must read 0 (3.3 V flash). NEVER an
 *          internal pull-up, and the UI board must not pull D/C up.
 *   GPIO46 L3 blower PWM (L2: fan-off gate). 100 k external pull-down: ROM log / boot strap 0.
 *          Never an internal pull-up. Left untouched (reset input, pulled down) until the L3
 *          blower driver lands, which is the fail-safe "fan running" state on both L2 and L3.
 */

/* ---------------------------------------------------------------- J4 bridge drive (C2) */
#define CTRL_GPIO_PWM_HA_MCU        4   /* J4.5, 10 k pull-down */
#define CTRL_GPIO_PWM_LA_MCU        5   /* J4.6 */
#define CTRL_GPIO_PWM_HB_MCU       15   /* J4.7 */
#define CTRL_GPIO_PWM_LB_MCU       16   /* J4.8 */

/* ---------------------------------------------------------------- interlock (C2, C4, C23) */
#define CTRL_GPIO_IL_RESET_N       17   /* reset request, falling edge, idle high */
#define CTRL_GPIO_IL_WDI           18   /* TPS3823 heartbeat (state machine) */
#define CTRL_GPIO_RUN_EN           14   /* C23: PERMIT = latch AND RUN_EN (U37). 4.7 k pull-down
                                         * (R102); high = permitted. Output, push-pull, preset low.
                                         * Firmware can only REMOVE permission with it. */
#define CTRL_GPIO_BUS_FAULT_RB     21   /* via SN74LVC244A, high = fault */
#define CTRL_GPIO_RAIL_OK_RB       35   /* TPS3703 window, high = ok */
#define CTRL_GPIO_PERMIT_RB        36   /* final PERMIT (after U37), high = permitted */

/* ---------------------------------------------------------------- RTD / MCP3202 bus, SPI2 (C20) */
#define CTRL_GPIO_RTD_CS_N         10
#define CTRL_GPIO_RTD_SCK          11
#define CTRL_GPIO_RTD_SDO          12   /* MISO */
#define CTRL_GPIO_RTD_SDI          13   /* MOSI */
#define CTRL_GPIO_EXT_ADC_CS_N     42   /* MCP3202, 10 k pull-up */
#define CTRL_RTD_SPI_MODE           3   /* shared by the MAX31865 and MCP3202 (C20) */

/* ---------------------------------------------------------------- zero-cross captures */
#define CTRL_GPIO_CT_ZC_MCU        38   /* J4.13, TLV3201 push-pull */
#define CTRL_GPIO_LINE_ZC_MCU      39   /* J4.16, high near the line zero */

/* ---------------------------------------------------------------- ADC1 (C12, C27) */
#define CTRL_GPIO_CT_MON_ADC        1
#define CTRL_GPIO_VBUS_ADC          2
#define CTRL_GPIO_HS_ADC            6   /* heatsink NTC (thermal-sense block) */
#define CTRL_GPIO_COIL_ADC          7   /* coil NTC (thermal-sense block) */
#define CTRL_GPIO_M12_ADC           8   /* M12 probe NTC */
#define CTRL_GPIO_RIM_ADC           9   /* R36 rim NTC (C27), built like the coil channel */
#define CTRL_ADC1_CH_CT_MON_ADC     0
#define CTRL_ADC1_CH_VBUS_ADC       1
#define CTRL_ADC1_CH_HS_ADC         5
#define CTRL_ADC1_CH_COIL_ADC       6
#define CTRL_ADC1_CH_M12_ADC        7
#define CTRL_ADC1_CH_RIM_ADC        8

/* ---------------------------------------------------------------- I2C to the TCA9555 (C27) */
#define CTRL_GPIO_I2C_SDA          37   /* GPIO matrix, no strap; 4.7 k external pull-up */
#define CTRL_GPIO_BOOT_IO0          0   /* I2C SCL on the boot strap (net I2C_SCL_BOOT) */
#define CTRL_GPIO_I2C_SCL          CTRL_GPIO_BOOT_IO0
#define CTRL_I2C_HZ            400000
#define CTRL_TCA9555_ADDR        0x20   /* A2..A0 = 0 */

/* ---------------------------------------------------------------- UI bus J7, SPI3 (C26) */
#define CTRL_GPIO_UI_SCK           40
#define CTRL_GPIO_UI_MOSI          41
#define CTRL_GPIO_UI_MISO          44   /* the module's RXD0 / U0RXD: UART0 console is NOT usable */
#define CTRL_GPIO_UI_CS_OLED_N     47   /* 10 k pull-up here */
#define CTRL_GPIO_UI_CS_EXP_N      48   /* 10 k pull-up here; MCP23S08 on the UI board */
#define CTRL_GPIO_UI_DC            45   /* strap, see above */

/* ---------------------------------------------------------------- blower J10 (L3, C28) */
#define CTRL_GPIO_FAN_PWM          46   /* L3: LEDC PWM into the buck FB; duty 0 = full speed */
#define CTRL_GPIO_FAN_TACH          3   /* FG, open collector, 1 k / 1 nF, PCNT; 0 Hz = stalled */

/* ---------------------------------------------------------------- console / debug (C26) */
#define CTRL_GPIO_USB_DN           19   /* USB-Serial-JTAG: console and download */
#define CTRL_GPIO_USB_DP           20
#define CTRL_GPIO_UART_TX          43   /* module TXD0, ROM log only (J11.3) */
/* GPIO44 (U0RXD) is UI_MISO, so the UART0 console must stay disabled; sdkconfig.defaults selects
 * CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG. Checked by test_controller_pins.c. */
#define CTRL_CONSOLE_UART0_ALLOWED  0

/* ---------------------------------------------------------------- TCA9555 bits (C23, C26-C28) */
#define CTRL_EXP_RTD_DRDY           7   /* P07, MAX31865 DRDY, active low (moved off GPIO14, C23) */
#define CTRL_EXP_LATCHED_FAULT_RB   8   /* P10, high = latched fault (interlock QBAR) */
#define CTRL_EXP_RTD_FAULT_RB       9   /* P11, high = RTD_HW_FAULT */
#define CTRL_EXP_HS_FAULT_RB       10   /* P12, high = heatsink trip */
#define CTRL_EXP_COIL_FAULT_RB     11   /* P13, high = coil trip */
#define CTRL_EXP_SUP_RUN_OK_RB     12   /* P14, high = TPS3823 run ok (C27; not in the trip path) */
#define CTRL_EXP_FAN_OFF           13   /* P15, L3: high = blower buck off; 10 k gate pull-down
                                         * keeps the blower running while the pin is an input */
#define CTRL_EXP_RTD2_CS_RESERVED   6   /* P06, reserved for a second MAX31865 CS (C14); input */

#endif
