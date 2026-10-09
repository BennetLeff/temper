#ifndef TEMPER_N21_PINS_H
#define TEMPER_N21_PINS_H
/*
 * Integrated SELV controller (zapote/controller, frozen netlist c6666ded...) GPIO map for the
 * native-21 binding. Source: zapote/controller/evidence/verify.json "gpio_map" and DECISIONS C2,
 * C3, C20. This is NOT the legacy temper_pins.h board (whose SPI clock on GPIO8 is M12_ADC here).
 *
 * Firmware has no output into PERMIT's fan-in except IL_RESET_N (a reset *request* edge, which the
 * latch honours only with every source healthy). There is deliberately no PERMIT output pin here.
 */
#define N21_GPIO_PWM_HA        4   /* J4.5, 10 k pull-down on the controller */
#define N21_GPIO_PWM_LA        5   /* J4.6 */
#define N21_GPIO_PWM_HB       15   /* J4.7 */
#define N21_GPIO_PWM_LB       16   /* J4.8 */
#define N21_GPIO_IL_RESET_N   17   /* interlock reset request, falling edge */
#define N21_GPIO_IL_WDI       18   /* TPS3823 heartbeat (owned by the state machine) */
#define N21_GPIO_BUS_FAULT_RB 21   /* J4.10 via SN74LVC244A, high = fault */
#define N21_GPIO_RAIL_OK_RB   35   /* TPS3703 window, high = ok */
#define N21_GPIO_PERMIT_RB    36   /* J4.9 read-back, high = permitted */
#define N21_GPIO_SUP_RUN_OK_RB 37  /* TPS3823 WDT_RESET_N, high = ok */
#define N21_GPIO_CT_ZC        38   /* J4.13, TLV3201 push-pull */
#define N21_GPIO_LINE_ZC      39   /* J4.16, high near the line zero */
#define N21_GPIO_CT_MON_ADC    1   /* ADC1_CH0, ATTEN3 (0-2900 mV) */
#define N21_GPIO_VBUS_ADC      2   /* ADC1_CH1, ATTEN2 (0-1600 mV) */
#define N21_ADC1_CH_CT_MON     0
#define N21_ADC1_CH_VBUS       1
#define N21_GPIO_RTD_CS_N     10   /* MAX31865, shares the bus below */
#define N21_GPIO_SPI_SCK      11
#define N21_GPIO_SPI_MISO     12   /* RTD_SDO */
#define N21_GPIO_SPI_MOSI     13   /* RTD_SDI */
#define N21_GPIO_EXT_ADC_CS_N 42   /* MCP3202, 10 k pull-up */
#define N21_MCP3202_CH_RMS     0   /* AD8436 tank RMS, gain-4 buffer */
#define N21_MCP3202_CH_REF     1   /* LM4040A25 2.500 V (0.1 %) */
#endif
