/**
 * @file mock_pwm.c
 * @brief Mock PWM implementation for testing
 * 
 * Provides simulated PWM with:
 * - State tracking for verification
 * - Emergency stop simulation
 * - Frequency/duty verification
 */

#include "../include/hal_pwm.h"
#include <string.h>
#include <stdbool.h>
#include <stddef.h>

/* Maximum PWM channels */
#define MOCK_PWM_MAX_CHANNELS 8

/* Per-channel state */
typedef struct {
    bool initialized;
    hal_pwm_config_t config;
    hal_pwm_state_t state;
} mock_pwm_channel_t;

static mock_pwm_channel_t s_channels[MOCK_PWM_MAX_CHANNELS];
static bool s_emergency_stopped = false;
static uint32_t s_call_count_set_duty = 0;
static uint32_t s_call_count_set_freq = 0;
static uint32_t s_call_count_emergency_stop = 0;

/* ============================================================================
 * Mock Control Functions
 * ============================================================================ */

void mock_pwm_reset(void)
{
    memset(s_channels, 0, sizeof(s_channels));
    s_emergency_stopped = false;
    s_call_count_set_duty = 0;
    s_call_count_set_freq = 0;
    s_call_count_emergency_stop = 0;
}

bool mock_pwm_is_running(hal_pwm_channel_t channel)
{
    if (channel >= 0 && channel < MOCK_PWM_MAX_CHANNELS) {
        return s_channels[channel].state.running;
    }
    return false;
}

float mock_pwm_get_duty(hal_pwm_channel_t channel)
{
    if (channel >= 0 && channel < MOCK_PWM_MAX_CHANNELS) {
        return s_channels[channel].state.duty_percent;
    }
    return 0.0f;
}

uint32_t mock_pwm_get_frequency(hal_pwm_channel_t channel)
{
    if (channel >= 0 && channel < MOCK_PWM_MAX_CHANNELS) {
        return s_channels[channel].state.frequency_hz;
    }
    return 0;
}

uint16_t mock_pwm_get_dead_time(hal_pwm_channel_t channel)
{
    if (channel >= 0 && channel < MOCK_PWM_MAX_CHANNELS) {
        return s_channels[channel].state.dead_time_ns;
    }
    return 0;
}

bool mock_pwm_is_emergency_stopped(void) { return s_emergency_stopped; }
uint32_t mock_pwm_get_set_duty_count(void) { return s_call_count_set_duty; }
uint32_t mock_pwm_get_set_freq_count(void) { return s_call_count_set_freq; }
uint32_t mock_pwm_get_emergency_stop_count(void) { return s_call_count_emergency_stop; }

/* ============================================================================
 * HAL Implementation
 * ============================================================================ */

static hal_status_t mock_pwm_init(hal_pwm_channel_t channel, const hal_pwm_config_t *config)
{
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS || !config) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    mock_pwm_channel_t *ch = &s_channels[channel];
    ch->initialized = true;
    ch->config = *config;
    ch->state.frequency_hz = config->frequency_hz;
    ch->state.duty_percent = config->duty_percent;
    ch->state.dead_time_ns = config->dead_time_ns;
    ch->state.complementary = config->complementary;
    ch->state.running = false;
    
    return HAL_OK;
}

static hal_status_t mock_pwm_set_frequency(hal_pwm_channel_t channel, uint32_t freq_hz)
{
    s_call_count_set_freq++;
    
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_channels[channel].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    if (s_emergency_stopped) {
        return HAL_ERROR; /* Cannot change while emergency stopped */
    }
    
    s_channels[channel].state.frequency_hz = freq_hz;
    return HAL_OK;
}

static hal_status_t mock_pwm_set_duty(hal_pwm_channel_t channel, float duty_percent)
{
    s_call_count_set_duty++;
    
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_channels[channel].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    if (s_emergency_stopped) {
        return HAL_ERROR; /* Cannot change while emergency stopped */
    }
    
    /* Clamp duty cycle */
    if (duty_percent < 0.0f) duty_percent = 0.0f;
    if (duty_percent > 100.0f) duty_percent = 100.0f;
    
    s_channels[channel].state.duty_percent = duty_percent;
    return HAL_OK;
}

static hal_status_t mock_pwm_set_dead_time(hal_pwm_channel_t channel, uint16_t dead_time_ns)
{
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_channels[channel].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    s_channels[channel].state.dead_time_ns = dead_time_ns;
    return HAL_OK;
}

static hal_status_t mock_pwm_start(hal_pwm_channel_t channel)
{
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_channels[channel].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    if (s_emergency_stopped) {
        return HAL_ERROR; /* Cannot start while emergency stopped */
    }
    
    s_channels[channel].state.running = true;
    return HAL_OK;
}

static hal_status_t mock_pwm_stop(hal_pwm_channel_t channel)
{
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_channels[channel].state.running = false;
    s_channels[channel].state.duty_percent = 0.0f;
    return HAL_OK;
}

static hal_status_t mock_pwm_emergency_stop(void)
{
    s_call_count_emergency_stop++;
    s_emergency_stopped = true;
    
    /* Stop all channels */
    for (int i = 0; i < MOCK_PWM_MAX_CHANNELS; i++) {
        s_channels[i].state.running = false;
        s_channels[i].state.duty_percent = 0.0f;
    }
    
    return HAL_OK;
}

static hal_status_t mock_pwm_get_state(hal_pwm_channel_t channel, hal_pwm_state_t *state)
{
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS || !state) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    *state = s_channels[channel].state;
    return HAL_OK;
}

static hal_status_t mock_pwm_deinit(hal_pwm_channel_t channel)
{
    if (channel < 0 || channel >= MOCK_PWM_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    memset(&s_channels[channel], 0, sizeof(mock_pwm_channel_t));
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_pwm_ops_t hal_pwm_mock_ops = {
    .init = mock_pwm_init,
    .set_frequency = mock_pwm_set_frequency,
    .set_duty = mock_pwm_set_duty,
    .set_dead_time = mock_pwm_set_dead_time,
    .start = mock_pwm_start,
    .stop = mock_pwm_stop,
    .emergency_stop = mock_pwm_emergency_stop,
    .get_state = mock_pwm_get_state,
    .deinit = mock_pwm_deinit
};
