/**
 * @file mock_timer.c
 * @brief Mock Timer implementation for testing
 * 
 * Provides simulated timers with:
 * - Controllable time progression
 * - Callback triggering
 * - Capture event simulation
 */

#include "../include/hal_timer.h"
#include <string.h>
#include <stdbool.h>
#include <stddef.h>

/* Maximum timers */
#define MOCK_TIMER_MAX 8

/* Timer state */
typedef struct {
    bool initialized;
    bool running;
    hal_timer_config_t config;
    uint64_t count;
    hal_capture_callback_t capture_callback;
    void *capture_arg;
} mock_timer_t;

static mock_timer_t s_timers[MOCK_TIMER_MAX];
static hal_time_us_t s_current_time_us = 0;
static uint32_t s_call_count_get_time = 0;

/* ============================================================================
 * Mock Control Functions
 * ============================================================================ */

void mock_timer_reset(void)
{
    memset(s_timers, 0, sizeof(s_timers));
    s_current_time_us = 0;
    s_call_count_get_time = 0;
}

void mock_timer_set_time(hal_time_us_t time_us)
{
    s_current_time_us = time_us;
}

void mock_timer_advance(hal_time_us_t delta_us)
{
    s_current_time_us += delta_us;
    
    /* Check for timer callbacks that should fire */
    for (int i = 0; i < MOCK_TIMER_MAX; i++) {
        if (s_timers[i].initialized && s_timers[i].running && 
            s_timers[i].config.callback) {
            /* Simplified: just call callback on any advance if timer is running */
            /* In real impl, would track accumulated time vs period */
        }
    }
}

void mock_timer_trigger_callback(hal_timer_t timer)
{
    if (timer >= 0 && timer < MOCK_TIMER_MAX) {
        mock_timer_t *t = &s_timers[timer];
        if (t->initialized && t->config.callback) {
            t->config.callback(timer, t->config.callback_arg);
        }
    }
}

void mock_timer_inject_capture(hal_timer_t timer, hal_time_us_t timestamp, 
                               hal_gpio_level_t edge)
{
    if (timer >= 0 && timer < MOCK_TIMER_MAX) {
        mock_timer_t *t = &s_timers[timer];
        if (t->capture_callback) {
            hal_capture_event_t event = {
                .timestamp = timestamp,
                .edge = edge
            };
            t->capture_callback(&event, t->capture_arg);
        }
    }
}

uint32_t mock_timer_get_time_call_count(void) { return s_call_count_get_time; }

bool mock_timer_is_running(hal_timer_t timer)
{
    if (timer >= 0 && timer < MOCK_TIMER_MAX) {
        return s_timers[timer].running;
    }
    return false;
}

/* ============================================================================
 * HAL Implementation
 * ============================================================================ */

static hal_status_t mock_timer_init(hal_timer_t timer, const hal_timer_config_t *config)
{
    if (timer < 0 || timer >= MOCK_TIMER_MAX || !config) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_timers[timer].initialized = true;
    s_timers[timer].config = *config;
    s_timers[timer].running = false;
    s_timers[timer].count = 0;
    
    return HAL_OK;
}

static hal_status_t mock_timer_start(hal_timer_t timer)
{
    if (timer < 0 || timer >= MOCK_TIMER_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_timers[timer].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    s_timers[timer].running = true;
    return HAL_OK;
}

static hal_status_t mock_timer_stop(hal_timer_t timer)
{
    if (timer < 0 || timer >= MOCK_TIMER_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_timers[timer].running = false;
    return HAL_OK;
}

static uint64_t mock_timer_get_count(hal_timer_t timer)
{
    if (timer < 0 || timer >= MOCK_TIMER_MAX) {
        return 0;
    }
    
    return s_timers[timer].count;
}

static hal_status_t mock_timer_set_period(hal_timer_t timer, uint32_t period_us)
{
    if (timer < 0 || timer >= MOCK_TIMER_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_timers[timer].config.period_us = period_us;
    return HAL_OK;
}

static hal_status_t mock_timer_configure_capture(hal_timer_t timer, hal_pin_t pin,
                                                  hal_gpio_intr_t edge,
                                                  hal_capture_callback_t callback, 
                                                  void *arg)
{
    if (timer < 0 || timer >= MOCK_TIMER_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_timers[timer].capture_callback = callback;
    s_timers[timer].capture_arg = arg;
    (void)pin;  /* Not used in mock */
    (void)edge;
    
    return HAL_OK;
}

static hal_time_us_t mock_get_time_us(void)
{
    s_call_count_get_time++;
    return s_current_time_us;
}

static hal_time_ms_t mock_get_time_ms(void)
{
    s_call_count_get_time++;
    return (hal_time_ms_t)(s_current_time_us / 1000);
}

static void mock_delay_us(uint32_t us)
{
    s_current_time_us += us;
}

static void mock_delay_ms(uint32_t ms)
{
    s_current_time_us += (uint64_t)ms * 1000;
}

static hal_status_t mock_timer_deinit(hal_timer_t timer)
{
    if (timer < 0 || timer >= MOCK_TIMER_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    memset(&s_timers[timer], 0, sizeof(mock_timer_t));
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_timer_ops_t hal_timer_mock_ops = {
    .init = mock_timer_init,
    .start = mock_timer_start,
    .stop = mock_timer_stop,
    .get_count = mock_timer_get_count,
    .set_period = mock_timer_set_period,
    .configure_capture = mock_timer_configure_capture,
    .get_time_us = mock_get_time_us,
    .get_time_ms = mock_get_time_ms,
    .delay_us = mock_delay_us,
    .delay_ms = mock_delay_ms,
    .deinit = mock_timer_deinit
};
