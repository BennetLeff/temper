/**
 * @file thermal_io.c
 * @brief Target glue for the thermal inputs the state handlers read (ESP-IDF only).
 *
 * - read_rim_temperature(): R36 rim NTC on GPIO9 / ADC1_CH8 (DECISIONS C27). The channel is
 *   sampled in the native-21 binding's continuous ADC1 pattern (ninth slot), so it is available
 *   only with CONFIG_TEMPER_POWER_HW_BINDING; without it the rim reads invalid (no rim cap, the
 *   pan RTD still caps at 250 C).
 * - blower_power_cap_pct(): STUB. The J10 blower (4-wire per the request; 3-wire with FG per the
 *   controller L3 schematic, C28) is still in progress. Until its driver lands there is no tach
 *   to supervise, so the stall hook reports no derate. The pure stall detector it will call is
 *   blower_stall_update() in thermal_mgmt.c (host-tested).
 */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>

#include "sdkconfig.h"
#include "../components/control/thermal_mgmt.h"
#if CONFIG_TEMPER_POWER_HW_BINDING
#include "n21_hw.h"
#endif

/* Two control ticks: the ADC task refreshes the thermal means every frame (< 1 ms). */
#define RIM_MAX_AGE_US 20000u

bool read_rim_temperature(float *temp_c)
{
#if CONFIG_TEMPER_POWER_HW_BINDING
    float mv[N21_THERMAL_COUNT];
    if (!n21_hw_thermal_mv(mv, RIM_MAX_AGE_US)) return false;
    return ntc_channel_temp_c(&THERMAL_NTC_RIM, mv[N21_THERMAL_RIM], temp_c) == NTC_OK;
#else
    *temp_c = NAN;
    return false;
#endif
}

/* STUB (controller L3): replace with blower_stall_update(driven, tach_hz, ...) once the blower
 * PWM (GPIO46, LEDC) and tach (GPIO3, PCNT) drivers exist. */
uint8_t blower_power_cap_pct(void)
{
    return 100u;
}
