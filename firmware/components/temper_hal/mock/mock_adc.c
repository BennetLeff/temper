/**
 * @file mock_adc.c
 * @brief Mock ADC implementation for testing
 * 
 * Provides simulated ADC with:
 * - Programmable return values
 * - Queued readings for sequences
 * - Calibration simulation
 */

#include "../include/hal_adc.h"
#include <string.h>
#include <stdbool.h>
#include <stddef.h>

/* Maximum channels and queue depth */
#define MOCK_ADC_MAX_CHANNELS 16
#define MOCK_ADC_QUEUE_SIZE 32

/* Per-channel state */
typedef struct {
    bool initialized;
    hal_adc_atten_t atten;
    hal_adc_width_t width;
    bool calibrated;
    bool continuous;
    uint32_t sample_rate;
    
    /* Value injection */
    uint16_t current_raw;
    float current_voltage_mv;
    
    /* Queue for sequence testing */
    uint16_t value_queue[MOCK_ADC_QUEUE_SIZE];
    uint8_t queue_head;
    uint8_t queue_tail;
    uint8_t queue_count;
} mock_adc_channel_t;

static mock_adc_channel_t s_channels[MOCK_ADC_MAX_CHANNELS];
static uint32_t s_call_count_read = 0;

/* ============================================================================
 * Mock Control Functions
 * ============================================================================ */

void mock_adc_reset(void)
{
    memset(s_channels, 0, sizeof(s_channels));
    s_call_count_read = 0;
}

void mock_adc_set_value(hal_adc_channel_t channel, uint16_t raw, float voltage_mv)
{
    if (channel >= 0 && channel < MOCK_ADC_MAX_CHANNELS) {
        s_channels[channel].current_raw = raw;
        s_channels[channel].current_voltage_mv = voltage_mv;
    }
}

void mock_adc_queue_value(hal_adc_channel_t channel, uint16_t raw)
{
    if (channel >= 0 && channel < MOCK_ADC_MAX_CHANNELS) {
        mock_adc_channel_t *ch = &s_channels[channel];
        if (ch->queue_count < MOCK_ADC_QUEUE_SIZE) {
            ch->value_queue[ch->queue_tail] = raw;
            ch->queue_tail = (ch->queue_tail + 1) % MOCK_ADC_QUEUE_SIZE;
            ch->queue_count++;
        }
    }
}

uint32_t mock_adc_get_read_count(void) { return s_call_count_read; }

/* ============================================================================
 * HAL Implementation
 * ============================================================================ */

static hal_status_t mock_adc_init(const hal_adc_config_t *config)
{
    if (!config || config->channel < 0 || config->channel >= MOCK_ADC_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    mock_adc_channel_t *ch = &s_channels[config->channel];
    ch->initialized = true;
    ch->atten = config->atten;
    ch->width = config->width;
    
    return HAL_OK;
}

static hal_status_t mock_adc_read_raw(hal_adc_channel_t channel, uint16_t *value)
{
    s_call_count_read++;
    
    if (channel < 0 || channel >= MOCK_ADC_MAX_CHANNELS || !value) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    mock_adc_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Return queued value if available, otherwise current value */
    if (ch->queue_count > 0) {
        *value = ch->value_queue[ch->queue_head];
        ch->queue_head = (ch->queue_head + 1) % MOCK_ADC_QUEUE_SIZE;
        ch->queue_count--;
    } else {
        *value = ch->current_raw;
    }
    
    return HAL_OK;
}

static hal_status_t mock_adc_read_voltage(hal_adc_channel_t channel, float *voltage_mv)
{
    s_call_count_read++;
    
    if (channel < 0 || channel >= MOCK_ADC_MAX_CHANNELS || !voltage_mv) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    mock_adc_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    *voltage_mv = ch->current_voltage_mv;
    return HAL_OK;
}

static hal_status_t mock_adc_calibrate(hal_adc_channel_t channel)
{
    if (channel < 0 || channel >= MOCK_ADC_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_channels[channel].calibrated = true;
    return HAL_OK;
}

static hal_status_t mock_adc_start_continuous(hal_adc_channel_t channel, uint32_t sample_rate_hz)
{
    if (channel < 0 || channel >= MOCK_ADC_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_channels[channel].continuous = true;
    s_channels[channel].sample_rate = sample_rate_hz;
    return HAL_OK;
}

static hal_status_t mock_adc_stop_continuous(hal_adc_channel_t channel)
{
    if (channel < 0 || channel >= MOCK_ADC_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_channels[channel].continuous = false;
    return HAL_OK;
}

static hal_status_t mock_adc_get_latest(hal_adc_channel_t channel, uint16_t *value)
{
    return mock_adc_read_raw(channel, value);
}

static hal_status_t mock_adc_deinit(hal_adc_channel_t channel)
{
    if (channel < 0 || channel >= MOCK_ADC_MAX_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    memset(&s_channels[channel], 0, sizeof(mock_adc_channel_t));
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_adc_ops_t hal_adc_mock_ops = {
    .init = mock_adc_init,
    .read_raw = mock_adc_read_raw,
    .read_voltage = mock_adc_read_voltage,
    .calibrate = mock_adc_calibrate,
    .start_continuous = mock_adc_start_continuous,
    .stop_continuous = mock_adc_stop_continuous,
    .get_latest = mock_adc_get_latest,
    .deinit = mock_adc_deinit
};
