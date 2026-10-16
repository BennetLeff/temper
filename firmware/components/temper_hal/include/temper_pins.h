/**
 * @file temper_pins.h
 * @brief ESP32-S3 pin map of the zapote/controller board
 *
 * The one place firmware names a GPIO, an ADC1 channel or a TCA9555 pin.
 * Every value below comes from the controller netlist, not from this file:
 * firmware/tools/check_board_pin_map.py derives the board's map from
 * zapote/controller/frozen/default.net and controller_parts.ato (branch
 * controller-c1-crs at 467917c38) into firmware/tools/zapote_controller_pins.json
 * and fails CI when a define here disagrees, when a wired GPIO or expander
 * pin has no define, or when a source outside this file hard-codes GPIO_NUM_n.
 *
 * Each define carries one tag on its own line, which the check reads:
 *   @net NAME       GPIO <value> carries board net NAME
 *   @adc1 NAME      ADC1 channel <value> (GPIO <value>+1) carries NAME
 *   @exp NAME       TCA9555 pin <value> = 8 * port + bit carries NAME
 *   @not-gpio NAME  the board puts NAME on no GPIO (value HAL_PIN_INVALID)
 *   @host-mock      host-test-only line, value above GPIO48 (no pad)
 *
 * The legacy (pre-zapote) map this replaces put the heatsink NTC on GPIO3
 * (the blower tach), MAX31865 DRDY on GPIO9 (the rim NTC), the RTD SPI clock
 * on GPIO8 (the M12 ADC), and the TPS3823 WDI / RESET_N and a runaway-cut
 * output on GPIO7 / 6 / 15 (the coil ADC, the heatsink ADC and the leg-B
 * high-side gate). output/temper-sensor-r3/firmware/DECISIONS.md D-PINS.
 */

#ifndef TEMPER_PINS_H
#define TEMPER_PINS_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Gate commands to native-21 (J4), full bridge: leg A = HA/LA, leg B = HB/LB.
 * They pass PERMIT (= interlock latch OK AND RUN_EN, DECISIONS C23) on the
 * power board. The capacitive-mode detector (C39) samples CT_ZC on the leg-A
 * turn-off commands.
 * ============================================================================ */

#define PIN_PWM_HA              4   /**< @net pwm_ha_mcu leg A high-side command */
#define PIN_PWM_LA              5   /**< @net pwm_la_mcu leg A low-side command */
#define PIN_PWM_HB              15  /**< @net pwm_hb_mcu leg B high-side command */
#define PIN_PWM_LB              16  /**< @net pwm_lb_mcu leg B low-side command */

/** Gate enable (C23): high = permitted. 4.7 k pull-down, low at reset. May
 *  only rise with the PWM idle (C39; power_gate.c). */
#define PIN_RUN_EN              14  /**< @net RUN_EN */

/* ============================================================================
 * Interlock (C4: the MCU observes protective nets, never drives them).
 * ============================================================================ */

/** TPS3823 WDI heartbeat (C42), 1 k pull-down. Toggled only by the WDI
 *  supervisor task (wdi_supervisor.c). */
#define PIN_IL_WDI              18  /**< @net IL_WDI */
/** Interlock latch reset request (falling edge). */
#define PIN_IL_RESET_N          17  /**< @net IL_RESET_N */
#define PIN_PERMIT_RB           36  /**< @net PERMIT_RB final PERMIT read-back */
#define PIN_BUS_FAULT_RB        21  /**< @net BUS_FAULT_RB */
#define PIN_RAIL_OK_RB          35  /**< @net RAIL_OK_RB */

/* ============================================================================
 * Zero-cross inputs
 * ============================================================================ */

/** Tank-current zero cross from native-21 (CT_ZC, high = current positive). */
#define PIN_CT_ZC               38  /**< @net CT_ZC_MCU */
#define PIN_LINE_ZC             39  /**< @net LINE_ZC_MCU */

/* ============================================================================
 * ADC1 inputs (ESP32-S3: ADC1_CHn is GPIO n+1)
 * ============================================================================ */

#define PIN_ADC_CT_MON          1   /**< @net CT_MON_ADC */
#define PIN_ADC_VBUS            2   /**< @net VBUS_ADC */
#define PIN_ADC_HS_NTC          6   /**< @net HS_ADC heatsink NTC (D-HSNTC) */
#define PIN_ADC_COIL            7   /**< @net COIL_ADC */
#define PIN_ADC_M12             8   /**< @net M12_ADC */
#define PIN_ADC_RIM_NTC         9   /**< @net RIM_ADC rim NTC (D-RIM) */

#define ADC_CH_CT_MON           0   /**< @adc1 CT_MON_ADC */
#define ADC_CH_VBUS             1   /**< @adc1 VBUS_ADC */
#define ADC_CH_HS_NTC           5   /**< @adc1 HS_ADC */
#define ADC_CH_COIL             6   /**< @adc1 COIL_ADC */
#define ADC_CH_M12              7   /**< @adc1 M12_ADC */
#define ADC_CH_RIM_NTC          8   /**< @adc1 RIM_ADC */

/* ============================================================================
 * RTD SPI bus (SPI2): MAX31865 and the MCP3202 rail ADC
 * ============================================================================ */

#define PIN_SPI_CS_RTD1         10  /**< @net RTD_CS_N MAX31865 chip select */
#define PIN_SPI_CLK             11  /**< @net RTD_SCK */
#define PIN_SPI_MISO            12  /**< @net RTD_SDO MAX31865 SDO into the MCU */
#define PIN_SPI_MOSI            13  /**< @net RTD_SDI MCU out to MAX31865 SDI */
#define PIN_SPI_CS_EXT_ADC      42  /**< @net EXT_ADC_CS_N MCP3202 chip select */

/** MAX31865 DRDY is not on a GPIO: it is TCA9555 P07 (EXP_RTD_DRDY, C23).
 *  PIN_RTD_DRDY is invalid on the target, so rtd_service polls P07 through
 *  the TCA9555 each control tick (DECISIONS.md D-DRDY). The host suites keep
 *  a mock line above the last pad for the GPIO-edge tests. */
#ifdef ESP_PLATFORM
#define PIN_RTD_DRDY            HAL_PIN_INVALID /**< @not-gpio RTD_DRDY */
#else
#define PIN_RTD_DRDY            63  /**< @host-mock */
#endif

/* ============================================================================
 * I2C (TCA9555 only). GPIO0 is also the SPI-boot strap; its 4.7 k pull-up
 * holds it high.
 * ============================================================================ */

#define PIN_I2C_SDA             37  /**< @net I2C_SDA */
#define PIN_I2C_SCL             0   /**< @net I2C_SCL_BOOT */

/** TCA9555 address: A2..A0 tied low. */
#define TEMPER_EXPANDER_I2C_ADDR 0x20

/* TCA9555 pins, 8 * port + bit. Spare: P02-P05, P17; P06 reserved (C14). */
#define EXP_CM_HA_OK_RB         0   /**< @exp CM_HA_OK_RB capacitive-mode, leg A HS (1 = healthy) */
#define EXP_CM_LA_OK_RB         1   /**< @exp CM_LA_OK_RB capacitive-mode, leg A LS (1 = healthy) */
#define EXP_RTD_DRDY            7   /**< @exp RTD_DRDY MAX31865 DRDY, active low */
#define EXP_LATCHED_FAULT_RB    8   /**< @exp LATCHED_FAULT_RB */
#define EXP_RTD_FAULT_RB        9   /**< @exp RTD_FAULT_RB */
#define EXP_HS_FAULT_RB         10  /**< @exp HS_FAULT_RB */
#define EXP_COIL_FAULT_RB       11  /**< @exp COIL_FAULT_RB */
#define EXP_SUP_RUN_OK_RB       12  /**< @exp SUP_RUN_OK_RB TPS3823 RESET_N read-back */
#define EXP_FAN_OFF             13  /**< @exp FAN_OFF */
#define EXP_BLW_PG              14  /**< @exp BLW_PG */

/* ============================================================================
 * Blower (C28)
 * ============================================================================ */

/** LEDC speed command; GPIO46 is a strap (100 k pull-down, low = full speed). */
#define PIN_FAN_PWM             46  /**< @net FAN_PWM */
#define PIN_FAN_TACH            3   /**< @net FAN_TACH PCNT input */

/* ============================================================================
 * UI bus to the fascia board (J7, C26): OLED + MCP23S08 on one SPI host
 * ============================================================================ */

#define PIN_UI_SCK              40  /**< @net UI_SCK */
#define PIN_UI_MOSI             41  /**< @net UI_MOSI */
#define PIN_UI_MISO             44  /**< @net UI_MISO U0RXD pad */
#define PIN_UI_DC               45  /**< @net UI_DC strap, 100 k pull-down */
#define PIN_UI_CS_OLED_N        47  /**< @net UI_CS_OLED_N */
#define PIN_UI_CS_EXP_N         48  /**< @net UI_CS_EXP_N */

/* ============================================================================
 * Debug (TC2050 land J11, C41)
 * ============================================================================ */

#define PIN_UART_TX             43  /**< @net UART0_TX console */
#define PIN_USB_DN              19  /**< @net USB_DN USB Serial/JTAG */
#define PIN_USB_DP              20  /**< @net USB_DP USB Serial/JTAG */

#ifdef __cplusplus
}
#endif

#endif /* TEMPER_PINS_H */
