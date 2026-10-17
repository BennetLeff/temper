#ifndef TEMPER_N21_HW_H
#define TEMPER_N21_HW_H
#include "n21_binding.h"
/* ESP32-S3 implementation of n21_hw_ops_t (n21_hw_esp32.c, built only with
 * CONFIG_TEMPER_POWER_HW_BINDING). Call once from app_main after power_service_bootstrap() and
 * rtd_service_bootstrap() (the MCP3202 shares the MAX31865's SPI2 bus). Returns the init verdict;
 * only N21_INIT_BIND binds the power service. The PWM pads are low in every outcome. */
n21_init_t n21_hw_start(void);
/* Latest ADC1 frame means (mV) of the thermal channels, in this order: heatsink, coil, M12, rim
 * (GPIO6/7/8/9). False if no fresh frame within max_age_us. Converted by thermal_mgmt.h. */
enum { N21_THERMAL_HS = 0, N21_THERMAL_COIL, N21_THERMAL_M12, N21_THERMAL_RIM, N21_THERMAL_COUNT };
bool n21_hw_thermal_mv(float mv[N21_THERMAL_COUNT], uint32_t max_age_us);
/* For a bench console / telemetry. NULL before n21_hw_start(). */
n21_binding_t *n21_hw_binding(void);
#endif
