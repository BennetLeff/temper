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
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Safety thresholds
#define COIL_INDUCTANCE_DROP_WARN_PERCENT 10
#define COIL_INDUCTANCE_DROP_FAULT_PERCENT 20
#define COIL_MAX_TEMP_C 120.0f  // Litz wire insulation limit

/**
 * @brief Coil Guard Status
 */
typedef enum {
    COIL_GUARD_OK = 0,
    COIL_GUARD_WARN_INDUCTANCE_LOW = 1,
    COIL_GUARD_ERR_SHORTED = 2,
    COIL_GUARD_ERR_OVERTEMP = 3,
    COIL_GUARD_ERR_NULL = 4
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
 * @param coil_temp_c Current coil temperature (optional, use -999 if unknown)
 * @return COIL_GUARD_OK or warning/error code
 */
coil_guard_status_t coil_guard_update(coil_guard_t *ctx, float current_freq_hz, float coil_temp_c);

#ifdef __cplusplus
}
#endif

#endif /* COIL_GUARD_H */
