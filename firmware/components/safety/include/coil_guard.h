/**
 * @file coil_guard.h
 * @brief Induction Coil Fault Detection
 * 
 * Monitors coil health by analyzing:
 * - Resonant frequency shifts (Inductance monitoring)
 * - Q-factor changes (Loss monitoring)
 * - Coil temperature (if sensor available)
 * 
 * Primary goal is detecting inter-turn shorts which cause
 * inductance drops and local hot spots.
 */

#ifndef COIL_GUARD_H
#define COIL_GUARD_H

#include "hal_types.h"
#include "../../control/thermal_mgmt.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Safety thresholds
#define COIL_INDUCTANCE_DROP_WARN_PERCENT 10
#define COIL_INDUCTANCE_DROP_FAULT_PERCENT 20

/*
 * Coil temperature, aligned with R32 (enclosure CONTROLLER-SPEC "Fan law") and DECISIONS C28:
 *  - the fan's coil loop holds 140 C (FAN_COIL_SETPOINT_C);
 *  - tank power derates above 150 C, the mean winding limit, to 0 at 160 C (coil_tank_cap_pct(),
 *    the same function the fan law uses);
 *  - the hard trip is 165 C: the top of the derate band plus 5 K. At 160 C the derate already
 *    asks for zero tank power, so the trip only acts when the derate has failed or the coil keeps
 *    heating with no power (blower lost). 5 K clears the sensor's own spread near 150 C: R25
 *    +/- 2 % plus 6.2 % from the B tolerance (Vishay doc 29049 p. 12, 4190 K curve) at -2.5 %/K is
 *    about +/- 3.3 K, so normal operation at the band edge cannot nuisance-trip.
 */
#define COIL_SETPOINT_C   FAN_COIL_SETPOINT_C
#define COIL_DERATE_C     FAN_COIL_LIMIT_C
#define COIL_DERATE_END_C (FAN_COIL_LIMIT_C + FAN_COIL_LIMIT_BAND_K)
#define COIL_TRIP_MARGIN_K 5.0f
#define COIL_MAX_TEMP_C   (COIL_DERATE_END_C + COIL_TRIP_MARGIN_K)   /* 165 C hard trip */
/* Readings outside the converter's validity (open / short, NaN) are a sensor fault. */
#define COIL_TEMP_VALID_MIN_C (-20.0f) /* = THERMAL_NTC_COIL.t_open_c (checked by test_thermal_mgmt) */

/**
 * @brief Coil Guard Status
 */
typedef enum {
    COIL_GUARD_OK = 0,
    COIL_GUARD_WARN_INDUCTANCE_LOW = 1,
    COIL_GUARD_ERR_SHORTED = 2,
    COIL_GUARD_ERR_OVERTEMP = 3,
    COIL_GUARD_ERR_NULL = 4,
    COIL_GUARD_WARN_DERATING = 5,  /* 150..165 C: tank power capped by coil_tank_cap_pct() */
    COIL_GUARD_ERR_SENSOR = 6      /* NaN or implausible coil temperature: fail safe */
} coil_guard_status_t;

/**
 * @brief Coil Monitor Context
 */
typedef struct {
    float baseline_freq_hz;
    bool baseline_valid;
    float coil_temp_c;
} coil_guard_t;

/**
 * @brief Initialize Coil Guard
 * @param ctx Context
 */
void coil_guard_init(coil_guard_t *ctx);

/**
 * @brief Set baseline resonant frequency
 * 
 * Call this when system is stable with a known good pan,
 * or use a theoretical uncoupled frequency as reference.
 * 
 * @param ctx Context
 * @param freq_hz Measured frequency
 */
void coil_guard_set_baseline(coil_guard_t *ctx, float freq_hz);

/**
 * @brief Monitor coil health
 * 
 * Checks current operating frequency against baseline.
 * A significant INCREASE in frequency indicates inductance drop
 * (inter-turn short).
 * 
 * @param ctx Context
 * @param current_freq_hz Current PLL frequency
 * @param coil_temp_c Current coil temperature from the coil NTC (NaN if the reading is invalid:
 *                    treated as a sensor fault, never as "no sensor")
 * @return COIL_GUARD_OK or warning/error code
 */
coil_guard_status_t coil_guard_update(coil_guard_t *ctx, float current_freq_hz, float coil_temp_c);

#ifdef __cplusplus
}
#endif

#endif /* COIL_GUARD_H */
