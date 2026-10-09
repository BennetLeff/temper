#ifndef TEMPER_N21_HW_H
#define TEMPER_N21_HW_H
#include "n21_binding.h"
/* ESP32-S3 implementation of n21_hw_ops_t (n21_hw_esp32.c, built only with
 * CONFIG_TEMPER_POWER_HW_BINDING). Call once from app_main after power_service_bootstrap() and
 * rtd_service_bootstrap() (the MCP3202 shares the MAX31865's SPI2 bus). Returns the init verdict;
 * only N21_INIT_BIND binds the power service. The PWM pads are low in every outcome. */
n21_init_t n21_hw_start(void);
/* For a bench console / telemetry. NULL before n21_hw_start(). */
n21_binding_t *n21_hw_binding(void);
#endif
