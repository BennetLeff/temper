/**
 * @file guard_base.h
 * @brief Base class for safety guards with common patterns (ADDITIVE, non-breaking)
 * 
 * This header provides common patterns for all safety guards:
 * - ADC guard
 * - Fan guard
 * - NTC guard
 * - PWM guard
 * - Coil guard
 * 
 * Usage:
 *     // In guard header (e.g., fan_guard.h)
 *     typedef struct {
 *         guard_context_t base;  // Embedded base context
 *         float current_power_w;        // Fan-specific fields
 *         float ambient_temp_c;
 *         uint32_t current_rpm;
 *         // ... more specific fields
 *     } fan_guard_t;
 *     
 *     // In guard implementation (e.g., fan_guard.c)
 *     void fan_guard_init(fan_guard_t *ctx, const guard_config_t *cfg) {
 *         guard_base_init(&ctx->base, cfg);
 *         // Fan-specific init
 *         ctx->current_power_w = 0.0f;
 *     }
 *     
 *     fan_guard_status_t fan_guard_update(fan_guard_t *ctx, ...) {
 *         if (!guard_should_update(&ctx->base, now_ms)) {
 *             return FAN_GUARD_OK;
 *         }
 *         // ... guard-specific logic
 *         guard_mark_updated(&ctx->base, now_ms);
 *     }
 * 
 * Important: This is ADDITIVE - existing guards continue to work unchanged.
 * They can adopt the base class incrementally when ready.
 */

#ifndef GUARD_BASE_H
#define GUARD_BASE_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

// Forward declaration for HAL time function (to avoid circular dependency)
extern uint32_t hal_get_tick_ms(void);

/* ================================
 * Guard Status Codes (Common)
 * ================================
 * 
 * Each guard can define its own status codes, but this provides
 * a base set for consistency. Guard-specific codes should extend
 * from these base values.
 */
typedef enum {
    GUARD_OK = 0,
    GUARD_ERR_NULL = 1,
    GUARD_ERR_RANGE = 2,
    GUARD_ERR_STUCK = 3,
    GUARD_ERR_STALE = 4,
    GUARD_ERR_TIMEOUT = 5,
    GUARD_ERR_FAILURE = 6,
    GUARD_WARN_RESTRICTED = 7,
} guard_status_t;

/* ================================
 * Guard Configuration
 * ================================
 * 
 * Timing and behavior configuration for guards.
 * All timing values are in milliseconds.
 */
typedef struct {
    uint32_t check_interval_ms;  // How often to run guard update logic
    uint32_t timeout_ms;         // Watchdog timeout (stale detection)
    uint32_t history_size;         // For guards that use history buffers
    bool enabled;                 // Guard enable/disable flag
} guard_config_t;

/* ================================
 * Guard Context Base
 * ================================
 * 
 * Base context that should be embedded in each guard's
 * specific context structure. This provides common timing
 * and state management.
 */
typedef struct {
    uint32_t last_check_ms;     // Last time guard_update() ran
    uint32_t last_update_ms;     // Last time data was updated (watchdog)
    guard_config_t config;       // Guard configuration
    uint16_t error_count;        // Consecutive error counter
} guard_context_t;

/* ================================
 * Default Configurations
 * ================================
 * 
 * Pre-configured defaults for common guard types.
 * Guards can use these or provide custom values.
 */

#define GUARD_CONFIG_FAST { .check_interval_ms = 100, .timeout_ms = 1000, .history_size = 8, .enabled = true }
#define GUARD_CONFIG_NORMAL { .check_interval_ms = 500, .timeout_ms = 5000, .history_size = 8, .enabled = true }
#define GUARD_CONFIG_SLOW { .check_interval_ms = 1000, .timeout_ms = 10000, .history_size = 16, .enabled = true }

/* ================================
 * Base Functions - Implementation
 * ================================
 */

/**
 * @brief Initialize guard base context
 * 
 * @param ctx Guard context pointer (must not be NULL)
 * @param cfg Configuration for the guard (can be NULL for defaults)
 * 
 * This function:
 * - Clears all context fields with memset
 * - Sets configuration (uses default if NULL)
 * - Initializes timing to current system time
 * - Resets error counter
 * 
 * Usage:
 *     guard_base_init(&fan_guard->base, &GUARD_CONFIG_NORMAL);
 *     guard_base_init(&adc_guard->base, NULL);  // Use defaults
 */
static inline void guard_base_init(guard_context_t *ctx, const guard_config_t *cfg) {
    if (!ctx) return;
    
    // Clear all context fields
    memset(ctx, 0, sizeof(guard_context_t));
    
    // Set configuration (use defaults if NULL)
    if (cfg) {
        ctx->config = *cfg;
    } else {
        ctx->config = GUARD_CONFIG_NORMAL;
    }
    
    // Initialize timing to current time
    ctx->last_check_ms = hal_get_tick_ms();
    ctx->last_update_ms = hal_get_tick_ms();
}

/**
 * @brief Check if guard needs update (interval-based)
 * 
 * @param ctx Guard context pointer
 * @param now_ms Current system time in milliseconds
 * @return true if enough time has elapsed since last check
 * 
 * This prevents running guard logic too frequently,
 * reducing CPU overhead.
 */
static inline bool guard_should_update(guard_context_t *ctx, uint32_t now_ms) {
    if (!ctx) return false;
    
    uint32_t dt_ms = now_ms - ctx->last_check_ms;
    return dt_ms >= ctx->config.check_interval_ms;
}

/**
 * @brief Check if guard is stale (timeout-based watchdog)
 * 
 * @param ctx Guard context pointer
 * @param now_ms Current system time in milliseconds
 * @return true if data hasn't been updated within timeout window
 * 
 * Stale detection prevents using stale sensor data for
 * critical decisions.
 */
static inline bool guard_is_stale(guard_context_t *ctx, uint32_t now_ms) {
    if (!ctx) return true;  // NULL guard is always stale
    
    if (!ctx->config.enabled) {
        return false;  // Disabled guards are not stale
    }
    
    uint32_t dt_ms = now_ms - ctx->last_update_ms;
    return dt_ms >= ctx->config.timeout_ms;
}

/**
 * @brief Mark guard as updated (reset watchdog)
 * 
 * @param ctx Guard context pointer
 * @param now_ms Current system time in milliseconds
 * 
 * Call this after successfully reading/updating data
 * to prevent stale detection.
 */
static inline void guard_mark_updated(guard_context_t *ctx, uint32_t now_ms) {
    if (!ctx) return;
    ctx->last_update_ms = now_ms;
}

/**
 * @brief Increment error counter
 * 
 * @param ctx Guard context pointer
 * 
 * Use this to track consecutive failures for retry logic.
 */
static inline void guard_increment_error(guard_context_t *ctx) {
    if (!ctx) return;
    if (ctx->error_count < 0xFFFF) {  // Prevent overflow
        ctx->error_count++;
    }
}

/**
 * @brief Reset error counter
 * 
 * @param ctx Guard context pointer
 * 
 * Call this after a successful operation to reset failure tracking.
 */
static inline void guard_reset_errors(guard_context_t *ctx) {
    if (!ctx) return;
    ctx->error_count = 0;
}

/**
 * @brief Get current error count
 * 
 * @param ctx Guard context pointer
 * @return Current consecutive error count
 */
static inline uint16_t guard_get_error_count(guard_context_t *ctx) {
    if (!ctx) return 0;
    return ctx->error_count;
}

/**
 * @brief Enable or disable guard
 * 
 * @param ctx Guard context pointer
 * @param enabled true to enable, false to disable
 * 
 * Disabled guards return OK for all operations without checking.
 * Useful for testing or maintenance modes.
 */
static inline void guard_set_enabled(guard_context_t *ctx, bool enabled) {
    if (!ctx) return;
    ctx->config.enabled = enabled;
}

/**
 * @brief Check if guard is enabled
 * 
 * @param ctx Guard context pointer
 * @return true if guard is enabled
 */
static inline bool guard_is_enabled(guard_context_t *ctx) {
    if (!ctx) return false;
    return ctx->config.enabled;
}

/* ================================
 * Utility Macros
 * ================================
 */

/**
 * @brief Get current time and check if update needed
 * 
 * Usage in guard update function:
 *     uint32_t now_ms = hal_get_tick_ms();
 *     if (!guard_should_update(&ctx->base, now_ms)) {
 *         return GUARD_OK;
 *     }
 *     // ... guard logic ...
 *     guard_mark_updated(&ctx->base, now_ms);
 */
#define GUARD_UPDATE_BEGIN(ctx) \
    uint32_t now_ms = hal_get_tick_ms(); \
    if (!guard_should_update(&ctx->base, now_ms)) { \
        return GUARD_OK; \
    }

#define GUARD_UPDATE_END(ctx) \
    guard_mark_updated(&ctx->base, now_ms);

/**
 * @brief Check guard state and return error if NULL
 * 
 * Usage:
 *     GUARD_CHECK_PTR(ctx);
 *     // ... guard logic
 */
#define GUARD_CHECK_PTR(ctx) \
    if (!(ctx)) { \
        return GUARD_ERR_NULL; \
    }

/**
 * @brief Return early if guard is stale
 * 
 * Usage:
 *     GUARD_CHECK_STALE(ctx);
 *     // ... continue only if fresh
 */
#define GUARD_CHECK_STALE(ctx, stale_status) \
    if (guard_is_stale(&ctx->base, hal_get_tick_ms())) { \
        return stale_status; \
    }

#endif /* GUARD_BASE_H */
