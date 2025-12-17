/**
 * @file zvs_monitor.h
 * @brief Zero Voltage Switching (ZVS) verification and monitoring
 *
 * Per ticket temper-1lj.3:
 * Monitors switching node voltage at IGBT turn-on to verify ZVS operation.
 * Hard switching (high V_SW at turn-on) causes 10-100x switching losses
 * and can lead to rapid IGBT thermal failure.
 *
 * Detection Method:
 * - Sample V_SW just before high-side IGBT turn-on
 * - ZVS achieved if V_SW < 50V
 * - Hard switching if V_SW > 50V
 *
 * Response Strategy:
 * - 1-3 hard switches: Log warning, increase dead time
 * - >3 consecutive: Reduce power 50%
 * - >10 consecutive: Shutdown with fault
 */

#ifndef ZVS_MONITOR_H
#define ZVS_MONITOR_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief ZVS status codes
 */
typedef enum {
    ZVS_OK = 0,              /**< ZVS achieved */
    ZVS_WARNING,             /**< Occasional hard switching (1-3) */
    ZVS_POWER_REDUCTION,     /**< Frequent hard switching (>3) */
    ZVS_FAULT                /**< Critical hard switching (>10) */
} zvs_status_t;

/**
 * @brief ZVS monitor configuration
 */
typedef struct {
    float threshold_voltage;    /**< V_SW threshold for ZVS detection (V) */
    uint32_t warning_count;     /**< Consecutive hard switches for warning */
    uint32_t power_reduce_count; /**< Consecutive hard switches for power reduction */
    uint32_t fault_count;       /**< Consecutive hard switches for shutdown */
    float power_reduction_factor; /**< Power reduction multiplier (0.0-1.0) */
} zvs_config_t;

/**
 * @brief ZVS monitor context
 */
typedef struct {
    float threshold_voltage;
    uint32_t consecutive_hard_switches;
    uint32_t total_hard_switches;
    uint32_t total_measurements;
    zvs_status_t status;
    float last_vsw_voltage;
    bool power_reduced;
} zvs_context_t;

/**
 * @brief Default ZVS configuration
 */
#define ZVS_DEFAULT_CONFIG() {          \
    .threshold_voltage = 50.0f,         \
    .warning_count = 3,                 \
    .power_reduce_count = 3,            \
    .fault_count = 10,                  \
    .power_reduction_factor = 0.5f      \
}

/**
 * @brief Initialize ZVS monitor
 *
 * @param config Configuration (NULL for defaults)
 */
void zvs_init(const zvs_config_t *config);

/**
 * @brief Update ZVS monitor with switching node voltage measurement
 *
 * Should be called from ADC sampling ISR or high-priority task,
 * synchronized with high-side IGBT turn-on event.
 *
 * @param vsw_voltage Switching node voltage at turn-on (V)
 */
void zvs_update(float vsw_voltage);

/**
 * @brief Get current ZVS status
 *
 * @return ZVS status code
 */
zvs_status_t zvs_get_status(void);

/**
 * @brief Check if ZVS is healthy
 *
 * @return true if ZVS_OK or ZVS_WARNING, false otherwise
 */
bool zvs_is_healthy(void);

/**
 * @brief Get ZVS statistics
 *
 * @param hard_switches Output: consecutive hard switching events
 * @param total_switches Output: total hard switches since init
 * @param success_rate Output: ZVS success rate (0.0-1.0)
 */
void zvs_get_stats(uint32_t *hard_switches, uint32_t *total_switches, float *success_rate);

/**
 * @brief Get recommended power reduction factor
 *
 * Returns 1.0 for normal operation, or reduced value if power
 * reduction is recommended due to hard switching.
 *
 * @return Power reduction factor (0.0-1.0)
 */
float zvs_get_power_factor(void);

/**
 * @brief Reset ZVS monitor
 *
 * Clears all statistics and resets to ZVS_OK status.
 */
void zvs_reset(void);

/**
 * @brief Get ZVS context for debugging
 */
const zvs_context_t* zvs_get_context(void);

#ifdef __cplusplus
}
#endif

#endif /* ZVS_MONITOR_H */
