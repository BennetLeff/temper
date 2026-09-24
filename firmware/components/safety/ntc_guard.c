/**
 * @file ntc_guard.c
 * @brief Implementation of NTC safety checks
 */

#include "ntc_guard.h"
#include "hal_adc.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

// External dependency
extern uint32_t hal_get_tick_ms(void);

/* NTC parameters. MUST match the schematic part, not a generic 10k thermistor.
 *
 * Schematic (elec/src/modules.ato:2459-2469): Vishay BCcomponents
 * NTCALUG01A104GA lug sensor -- R25 = 100 kOhm +/-2%, B25/85 = 4190 K +/-1.5%.
 * Divider (modules.ato:2487-2492): VCC -> r_ntc_fixed (10 kOhm +/-1%) ->
 * ntc_sense -> NTC -> GND, i.e. the NTC is the bottom leg, which is what
 * convert_adc_to_temp() below assumes.
 *
 * These were previously 10 kOhm / B3950 (an NCU18XH103F6SRB, a part that is
 * not in this design). That under-read by roughly 60 C on a thermal
 * protection path: at the THM-01 85 C trip point the schematic puts
 * ntc_sense at 1.607 V, and the 10k/B3950 constants converted that to
 * ~26 C. See test_ntc_guard.c, which pins all three schematic-cited points.
 *
 * Cross-check against the schematic's own stated V_sense values, using the
 * ratiometric divider (these are the vectors in test_ntc_guard.c):
 *   3.000 V (adc 3723) -> 24.98 C   (schematic says 25 C)
 *   1.607 V (adc 1994) -> 85.02 C   (schematic says 85 C, THM-01 trip)
 *   0.828 V (adc 1027) -> 120.04 C  (schematic says 120 C)
 * simulation/harness/run_thm01_sim.py:97 and run_thm02_sim.py:94 independently
 * use the same R25 = 100k / B = 4190.
 */
#define NTC_R25 100000.0f
#define NTC_B 4190.0f
#define NTC_R_PULLUP 10000.0f
/* NOTE: this assumes the 12-bit full scale corresponds to the divider's top
 * rail. hal_adc_esp32.c currently uses ADC_ATTEN_DB_11 (~3.1 V usable), so the
 * counts->volts scaling still needs deciding; see docs/FIRMWARE_LINK_TRIAGE.md.
 * Deliberately not changed here -- it is a separate decision from the part
 * number, and the conversion is ratiometric so the two are independent. */
#define ADC_MAX_COUNTS 4095.0f

static float convert_adc_to_temp(uint16_t adc_val) {
    if (adc_val == 0) return 999.0f; // Prevent div by zero
    
    // Voltage divider: V_out = Vcc * R_ntc / (R_ntc + R_pullup)
    // ADC = 4095 * R_ntc / (R_ntc + R_pullup)
    // R_ntc = R_pullup * ADC / (4095 - ADC)
    // Assumes NTC is bottom resistor (to GND)
    
    float r_ntc = NTC_R_PULLUP * (float)adc_val / (ADC_MAX_COUNTS - (float)adc_val);
    
    // Beta equation: 1/T = 1/T0 + 1/B * ln(R/R0)
    float t_kelvin = 1.0f / (1.0f / 298.15f + 1.0f / NTC_B * logf(r_ntc / NTC_R25));
    return t_kelvin - 273.15f;
}

void ntc_guard_init(ntc_guard_t *ctx, hal_adc_channel_t channel) {
    if (!ctx) return;
    memset(ctx, 0, sizeof(ntc_guard_t));
    ctx->adc_channel = channel;
    ctx->valid = false;
}

ntc_guard_status_t ntc_guard_read_safe(ntc_guard_t *ctx, float *temp_c) {
    if (!ctx || !temp_c) return NTC_GUARD_ERR_NULL;
    
    uint16_t raw_val;
    hal_status_t status = HAL_ADC_READ_RAW(ctx->adc_channel, &raw_val);
    
    if (status != HAL_OK) return NTC_GUARD_ERR_NULL;
    
    // 1. Raw Range Check (Open/Short)
    if (raw_val < NTC_ADC_MIN) return NTC_GUARD_ERR_SHORT; // Short to GND
    if (raw_val > NTC_ADC_MAX) return NTC_GUARD_ERR_OPEN;  // Open / Short to VCC
    
    // 2. Convert to Temperature
    float t = convert_adc_to_temp(raw_val);
    *temp_c = t;
    
    // 3. Physical Range Check
    if (t < NTC_TEMP_MIN_C || t > NTC_TEMP_MAX_C) {
        return NTC_GUARD_ERR_RANGE;
    }
    
    // 4. Rate of Change Check
    uint32_t now = hal_get_tick_ms();
    if (ctx->valid) {
        float dt = (now - ctx->last_read_ms) / 1000.0f;
        if (dt > 0.1f) { // Only check if enough time passed
            float rate = fabsf(t - ctx->last_temp_c) / dt;
            if (rate > NTC_MAX_RATE_C_PER_SEC) {
                return NTC_GUARD_ERR_RATE;
            }
        }
    }
    
    // Update history
    ctx->last_temp_c = t;
    ctx->last_read_ms = now;
    ctx->valid = true;
    
    return NTC_GUARD_OK;
}

ntc_guard_status_t ntc_guard_cross_check(float heatsink_temp, float ambient_temp, bool is_heating) {
    // Basic plausibility
    if (is_heating) {
        // Heatsink significantly cooler than ambient is impossible while heating
        // Allow margin for sensor error (-5C)
        if (heatsink_temp < (ambient_temp - 5.0f)) {
            return NTC_GUARD_ERR_PLAUSIBILITY;
        }
    }
    return NTC_GUARD_OK;
}
