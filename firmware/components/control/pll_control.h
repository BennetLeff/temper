/**
 * @file pll_control.h
 * @brief Phase-Locked Loop for Zero Voltage Switching (ZVS) tracking
 * 
 * Dynamically tracks resonant frequency of tank circuit to maintain
 * ZVS operation under varying load conditions.
 */

#ifndef PLL_CONTROL_H
#define PLL_CONTROL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief PLL frequency limits
 */
#define PLL_MIN_FREQ_HZ     30000   /**< Minimum switching frequency */
#define PLL_MAX_FREQ_HZ     50000   /**< Maximum switching frequency */
#define PLL_DEFAULT_FREQ_HZ 35000   /**< Default startup frequency */

/**
 * @brief PLL configuration structure
 */
typedef struct {
    float kp;               /**< Proportional gain */
    float ki;               /**< Integral gain */
    float target_phase_us;  /**< Target phase lag in microseconds */
    uint32_t min_freq_hz;   /**< Minimum allowed frequency */
    uint32_t max_freq_hz;   /**< Maximum allowed frequency */
} pll_config_t;

/**
 * @brief PLL context structure
 */
typedef struct {
    float current_freq;     /**< Current switching frequency */
    float integrator;       /**< PI integrator state */
    float target_phase_us;  /**< Target phase lag */
    float kp;               /**< Proportional gain */
    float ki;               /**< Integral gain */
    uint32_t min_freq;      /**< Minimum frequency limit */
    uint32_t max_freq;      /**< Maximum frequency limit */
    bool locked;            /**< PLL lock status */
    uint32_t lock_count;    /**< Consecutive cycles within lock tolerance */
    uint32_t unlock_count;  /**< Consecutive cycles outside lock tolerance */
    float resonant_freq;    /**< Expected resonant frequency (Hz) */
} pll_context_t;

/**
 * @brief Default PLL configuration
 */
#define PLL_DEFAULT_CONFIG() { \
    .kp = 2.0f,                \
    .ki = 50.0f,               \
    .target_phase_us = 1.5f,   \
    .min_freq_hz = 30000,      \
    .max_freq_hz = 50000       \
}

/**
 * @brief Initialize PLL controller
 * 
 * @param config Configuration (NULL for defaults)
 */
void pll_init(const pll_config_t *config);

/**
 * @brief Set MCPWM timer handle for frequency control
 * 
 * Must be called before pll_enable() to allow hardware frequency updates.
 * 
 * @param timer_handle MCPWM timer handle
 */
#ifdef ESP_PLATFORM
#include "driver/mcpwm_prelude.h"
void pll_set_timer(mcpwm_timer_handle_t timer_handle);
void pll_set_capture_channel(mcpwm_cap_channel_handle_t cap_chan);
#endif

/**
 * @brief Enable PLL tracking
 */
void pll_enable(void);

/**
 * @brief Disable PLL tracking
 */
void pll_disable(void);

/**
 * @brief Update PLL with measured phase lag
 * 
 * Called from high-priority task or ISR at ~1kHz rate.
 * Adjusts switching frequency to maintain target phase.
 * 
 * @param measured_lag_us Measured phase lag in microseconds
 * @param dt_sec Time since last update in seconds
 */
void pll_update_loop(float measured_lag_us, float dt_sec);

/**
 * @brief Simplified update using internal phase measurement
 */
void pll_update(void);

/**
 * @brief Get current switching frequency
 * 
 * @return Current frequency in Hz
 */
float pll_get_frequency(void);

/**
 * @brief Check if PLL is locked
 * 
 * @return true if phase error within tolerance
 */
bool pll_is_locked(void);

/**
 * @brief Set target phase lag
 * 
 * @param phase_us Target phase lag in microseconds
 */
void pll_set_target_phase(float phase_us);

/**
 * @brief Reset PLL to default frequency
 */
void pll_reset(void);

/**
 * @brief Get PLL context for debugging/monitoring
 */
const pll_context_t* pll_get_context(void);

/**
 * @brief Set expected resonant frequency for boundary checking
 *
 * @param freq_hz Expected resonant frequency in Hz
 */
void pll_set_resonant_frequency(float freq_hz);

/**
 * @brief Check if frequency is within safe operating bounds
 *
 * Returns true if current frequency is within acceptable range
 * of the resonant frequency (f_res - 5kHz to f_res + 10kHz).
 *
 * @return true if frequency is safe, false if out of bounds
 */
bool pll_is_frequency_safe(void);

/**
 * @brief Get detailed lock status
 *
 * @param lock_cycles Output: number of consecutive locked cycles
 * @param phase_error_us Output: current phase error in microseconds
 * @return true if locked
 */
bool pll_get_lock_status(uint32_t *lock_cycles, float *phase_error_us);

#ifdef __cplusplus
}
#endif

#endif /* PLL_CONTROL_H */
