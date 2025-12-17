/**
 * @file fan_guard.h
 * @brief Fan Airflow and Cooling Efficiency Monitoring
 * 
 * Infers airflow health by monitoring temperature dynamics:
 * - Rate-of-rise vs. Power
 * - Thermal equilibrium check
 * - Fan-Temperature response correlation
 */

#ifndef FAN_GUARD_H
#define FAN_GUARD_H

#include "hal_types.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Safety limits
#define FAN_MAX_TEMP_RISE_RATE_C_PER_S 0.5f
#define FAN_CHECK_INTERVAL_MS 1000
#define FAN_EQUILIBRIUM_TOLERANCE_C 20.0f
#define FAN_RTH_HEATSINK 1.0f // C/W approx

/**
 * @brief Fan Guard Status
 */
typedef enum {
    FAN_GUARD_OK = 0,
    FAN_GUARD_WARN_RESTRICTED = 1, // Temp rising faster than expected
    FAN_GUARD_WARN_DEGRADED = 2,   // Equilibrium temp higher than expected
    FAN_GUARD_ERR_BLOCKED = 3,     // Critical airflow blockage detected
    FAN_GUARD_ERR_NULL = 4
} fan_guard_status_t;

/**
 * @brief Fan Monitor Context
 */
typedef struct {
    float last_temp_c;
    uint32_t last_check_ms;
    float current_power_w;
    float ambient_temp_c;
    bool fan_running;
} fan_guard_t;

/**
 * @brief Initialize Fan Guard
 * @param ctx Context
 */
void fan_guard_init(fan_guard_t *ctx);

/**
 * @brief Update monitoring with latest data
 * 
 * Should be called periodically (e.g. 1Hz)
 * 
 * @param ctx Context
 * @param heatsink_temp_c Current heatsink temperature
 * @param power_w Current input power
 * @param ambient_temp_c Current ambient temperature
 * @param fan_on Fan state
 * @return FAN_GUARD_OK or warning/error code
 */
fan_guard_status_t fan_guard_update(fan_guard_t *ctx, float heatsink_temp_c, float power_w, float ambient_temp_c, bool fan_on);

#ifdef __cplusplus
}
#endif

#endif /* FAN_GUARD_H */
