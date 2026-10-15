/**
 * @file hal_timer.h
 * @brief Timer Hardware Abstraction Layer
 * 
 * Provides platform-independent timer operations for:
 * - Periodic callbacks (control loops)
 * - One-shot delays
 * - Microsecond timestamping
 * - Capture/compare for ZCD edge timing
 * 
 * Used by:
 * - Control loop timing (10Hz PID, 1kHz PLL)
 * - Watchdog timing
 * - Phase measurement for ZVS
 */

#ifndef HAL_TIMER_H
#define HAL_TIMER_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Capture event data
 */
typedef struct {
    hal_time_us_t timestamp;    /**< Capture timestamp */
    hal_gpio_level_t edge;      /**< Edge that triggered capture */
} hal_capture_event_t;

/**
 * @brief Capture callback function
 */
typedef void (*hal_capture_callback_t)(const hal_capture_event_t *event, void *arg);

/**
 * @brief Timer operations interface
 */
typedef struct {
    /**
     * @brief Initialize timer
     * 
     * @param timer Timer identifier
     * @param config Timer configuration
     * @return HAL_OK on success
     */
    hal_status_t (*init)(hal_timer_t timer, const hal_timer_config_t *config);
    
    /**
     * @brief Start timer
     * 
     * @param timer Timer identifier
     * @return HAL_OK on success
     */
    hal_status_t (*start)(hal_timer_t timer);
    
    /**
     * @brief Stop timer
     * 
     * @param timer Timer identifier
     * @return HAL_OK on success
     */
    hal_status_t (*stop)(hal_timer_t timer);
    
    /**
     * @brief Get current timer count
     * 
     * @param timer Timer identifier
     * @return Current count value
     */
    uint64_t (*get_count)(hal_timer_t timer);
    
    /**
     * @brief Set timer period
     * 
     * @param timer Timer identifier
     * @param period_us Period in microseconds
     * @return HAL_OK on success
     */
    hal_status_t (*set_period)(hal_timer_t timer, uint32_t period_us);
    
    /**
     * @brief Configure input capture
     * 
     * Sets up edge capture on a GPIO pin for timing measurements.
     * 
     * @param timer Timer identifier
     * @param pin GPIO pin for capture input
     * @param edge Edge to capture on
     * @param callback Capture event callback
     * @param arg Callback argument
     * @return HAL_OK on success
     */
    hal_status_t (*configure_capture)(hal_timer_t timer, hal_pin_t pin,
                                      hal_gpio_intr_t edge,
                                      hal_capture_callback_t callback, void *arg);
    
    /**
     * @brief Get time since boot in microseconds
     * 
     * High-resolution timestamp for timing measurements.
     * 
     * @return Microseconds since boot
     */
    hal_time_us_t (*get_time_us)(void);
    
    /**
     * @brief Get time since boot in milliseconds
     * 
     * @return Milliseconds since boot
     */
    hal_time_ms_t (*get_time_ms)(void);
    
    /**
     * @brief Blocking delay in microseconds
     * 
     * @param us Microseconds to delay
     */
    void (*delay_us)(uint32_t us);
    
    /**
     * @brief Blocking delay in milliseconds
     * 
     * @param ms Milliseconds to delay
     */
    void (*delay_ms)(uint32_t ms);
    
    /**
     * @brief Deinitialize timer
     * 
     * @param timer Timer identifier
     * @return HAL_OK on success
     */
    hal_status_t (*deinit)(hal_timer_t timer);
} hal_timer_ops_t;

/**
 * @brief Global timer operations pointer
 */
extern const hal_timer_ops_t *hal_timer;

/**
 * @brief Set timer operations implementation
 */
void hal_timer_set_ops(const hal_timer_ops_t *ops);

/* ============================================================================
 * Convenience Macros
 * ============================================================================ */

/**
 * @brief Get current time in microseconds (convenience wrapper)
 */
#define HAL_TIME_US() \
    (hal_timer ? hal_timer->get_time_us() : 0)

/**
 * @brief Get current time in milliseconds (convenience wrapper)
 */
#define HAL_TIME_MS() \
    (hal_timer ? hal_timer->get_time_ms() : 0)

/**
 * @brief Delay in microseconds (convenience wrapper)
 */
#define HAL_DELAY_US(us) \
    do { if (hal_timer) hal_timer->delay_us(us); } while(0)

/**
 * @brief Delay in milliseconds (convenience wrapper)
 */
#define HAL_DELAY_MS(ms) \
    do { if (hal_timer) hal_timer->delay_ms(ms); } while(0)

#ifdef __cplusplus
}
#endif

#endif /* HAL_TIMER_H */
