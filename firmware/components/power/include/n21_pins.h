#ifndef TEMPER_N21_PINS_H
#define TEMPER_N21_PINS_H
/*
 * Native-21 binding's view of the integrated SELV controller (zapote/controller, layout L2) pin map.
 * Every number comes from controller_pins.h, the board's single source of truth (cross-checked
 * against the controller ato by firmware/tools/check_controller_pinmap.py). This is NOT the legacy
 * temper_pins.h board (whose SPI clock on GPIO8 is M12_ADC here).
 *
 * Firmware has two outputs into PERMIT's fan-in, and neither can grant it:
 *   - IL_RESET_N, a reset *request* edge, which the latch honours only with every source healthy;
 *   - RUN_EN (L2, DECISIONS C23), ANDed with the latch output by U37 (4.7 k pull-down, low at reset),
 *     so firmware can only remove permission with it. It is the binding's run gate.
 * SUP_RUN_OK moved to TCA9555 P14 (C27); it is read from the expander cache, not a GPIO.
 */
#include "controller_pins.h"

#define N21_GPIO_PWM_HA        CTRL_GPIO_PWM_HA_MCU
#define N21_GPIO_PWM_LA        CTRL_GPIO_PWM_LA_MCU
#define N21_GPIO_PWM_HB        CTRL_GPIO_PWM_HB_MCU
#define N21_GPIO_PWM_LB        CTRL_GPIO_PWM_LB_MCU
#define N21_GPIO_IL_RESET_N    CTRL_GPIO_IL_RESET_N
#define N21_GPIO_IL_WDI        CTRL_GPIO_IL_WDI
#define N21_GPIO_RUN_EN        CTRL_GPIO_RUN_EN
#define N21_GPIO_BUS_FAULT_RB  CTRL_GPIO_BUS_FAULT_RB
#define N21_GPIO_RAIL_OK_RB    CTRL_GPIO_RAIL_OK_RB
#define N21_GPIO_PERMIT_RB     CTRL_GPIO_PERMIT_RB
#define N21_EXP_SUP_RUN_OK_RB  CTRL_EXP_SUP_RUN_OK_RB
#define N21_GPIO_CT_ZC         CTRL_GPIO_CT_ZC_MCU
#define N21_GPIO_LINE_ZC       CTRL_GPIO_LINE_ZC_MCU
#define N21_GPIO_CT_MON_ADC    CTRL_GPIO_CT_MON_ADC
#define N21_GPIO_VBUS_ADC      CTRL_GPIO_VBUS_ADC
#define N21_ADC1_CH_CT_MON     CTRL_ADC1_CH_CT_MON_ADC   /* ATTEN3 (0-2900 mV) */
#define N21_ADC1_CH_VBUS       CTRL_ADC1_CH_VBUS_ADC     /* ATTEN2 (0-1600 mV) */
/* Thermal channels sampled in the same ADC1 pattern (C12, C27); converted by thermal_mgmt. */
#define N21_ADC1_CH_HS         CTRL_ADC1_CH_HS_ADC
#define N21_ADC1_CH_COIL       CTRL_ADC1_CH_COIL_ADC
#define N21_ADC1_CH_M12        CTRL_ADC1_CH_M12_ADC
#define N21_ADC1_CH_RIM        CTRL_ADC1_CH_RIM_ADC
#define N21_GPIO_RTD_CS_N      CTRL_GPIO_RTD_CS_N   /* MAX31865, shares the bus below */
#define N21_GPIO_SPI_SCK       CTRL_GPIO_RTD_SCK
#define N21_GPIO_SPI_MISO      CTRL_GPIO_RTD_SDO
#define N21_GPIO_SPI_MOSI      CTRL_GPIO_RTD_SDI
#define N21_GPIO_EXT_ADC_CS_N  CTRL_GPIO_EXT_ADC_CS_N /* MCP3202, 10 k pull-up */
#define N21_MCP3202_CH_RMS     0   /* AD8436 tank RMS, gain-4 buffer */
#define N21_MCP3202_CH_REF     1   /* LM4040A25 2.500 V (0.1 %) */
#endif
