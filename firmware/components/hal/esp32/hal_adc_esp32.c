/**
 * @file esp32_adc.c
 * @brief ESP32 ADC HAL Implementation
 * 
 * Wraps ESP-IDF ADC driver (v5.x API) for analog measurements.
 * Supports both one-shot and continuous modes with calibration.
 */

#include "../include/hal_adc.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_continuous.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "hal_adc";

/* Maximum number of ADC channels to track */
#define MAX_ADC_CHANNELS    10

/* ADC unit handle (ADC1 only, ADC2 conflicts with WiFi) */
static adc_oneshot_unit_handle_t s_adc1_handle = NULL;

/* Calibration handles per channel */
static adc_cali_handle_t s_cali_handles[MAX_ADC_CHANNELS];

/* Continuous mode handle */
static adc_continuous_handle_t s_continuous_handle = NULL;

/* Track channel configurations */
typedef struct {
    bool initialized;
    adc_atten_t atten;
    adc_bitwidth_t bitwidth;
} channel_config_t;

static channel_config_t s_channel_configs[MAX_ADC_CHANNELS];

/* Latest continuous mode values */
static volatile uint16_t s_continuous_values[MAX_ADC_CHANNELS];

/* ============================================================================
 * Helper Functions
 * ============================================================================ */

/**
 * @brief Map HAL attenuation to ESP-IDF
 */
static adc_atten_t map_atten(hal_adc_atten_t atten)
{
    switch (atten) {
        case HAL_ADC_ATTEN_0dB:     return ADC_ATTEN_DB_0;
        case HAL_ADC_ATTEN_2_5dB:   return ADC_ATTEN_DB_2_5;
        case HAL_ADC_ATTEN_6dB:     return ADC_ATTEN_DB_6;
        case HAL_ADC_ATTEN_11dB:    
        default:                    return ADC_ATTEN_DB_11;
    }
}

/**
 * @brief Map HAL bitwidth to ESP-IDF
 */
static adc_bitwidth_t map_bitwidth(hal_adc_width_t width)
{
    switch (width) {
        case HAL_ADC_WIDTH_9BIT:    return ADC_BITWIDTH_9;
        case HAL_ADC_WIDTH_10BIT:   return ADC_BITWIDTH_10;
        case HAL_ADC_WIDTH_11BIT:   return ADC_BITWIDTH_11;
        case HAL_ADC_WIDTH_12BIT:   return ADC_BITWIDTH_12;
        case HAL_ADC_WIDTH_13BIT:   
        default:                    return ADC_BITWIDTH_13;
    }
}

/* ============================================================================
 * HAL Implementation Functions
 * ============================================================================ */

static hal_status_t esp32_adc_init(const hal_adc_config_t *config)
{
    if (!config || config->channel < 0 || config->channel >= MAX_ADC_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    /* Create ADC1 unit handle if needed */
    if (!s_adc1_handle) {
        adc_oneshot_unit_init_cfg_t init_cfg = {
            .unit_id = ADC_UNIT_1,
            .ulp_mode = ADC_ULP_MODE_DISABLE,
        };
        esp_err_t err = adc_oneshot_new_unit(&init_cfg, &s_adc1_handle);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to create ADC1 unit: %s", esp_err_to_name(err));
            return HAL_ERROR;
        }
    }
    
    /* Configure channel */
    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten = map_atten(config->atten),
        .bitwidth = map_bitwidth(config->width),
    };
    
    esp_err_t err = adc_oneshot_config_channel(s_adc1_handle, 
                                                (adc_channel_t)config->channel, 
                                                &chan_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure ADC channel %d: %s", 
                 config->channel, esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    /* Track configuration */
    s_channel_configs[config->channel].initialized = true;
    s_channel_configs[config->channel].atten = chan_cfg.atten;
    s_channel_configs[config->channel].bitwidth = chan_cfg.bitwidth;
    
    ESP_LOGD(TAG, "ADC channel %d initialized, atten=%d, width=%d",
             config->channel, config->atten, config->width);
    return HAL_OK;
}

static hal_status_t esp32_adc_read_raw(hal_adc_channel_t channel, uint16_t *value)
{
    if (!s_adc1_handle || channel < 0 || channel >= MAX_ADC_CHANNELS || !value) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_channel_configs[channel].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    int raw_value;
    esp_err_t err = adc_oneshot_read(s_adc1_handle, (adc_channel_t)channel, &raw_value);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    *value = (uint16_t)raw_value;
    return HAL_OK;
}

static hal_status_t esp32_adc_read_voltage(hal_adc_channel_t channel, float *voltage_mv)
{
    if (!s_adc1_handle || channel < 0 || channel >= MAX_ADC_CHANNELS || !voltage_mv) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_channel_configs[channel].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Read raw value */
    int raw_value;
    esp_err_t err = adc_oneshot_read(s_adc1_handle, (adc_channel_t)channel, &raw_value);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Convert to voltage using calibration if available */
    if (s_cali_handles[channel]) {
        int voltage_int;
        err = adc_cali_raw_to_voltage(s_cali_handles[channel], raw_value, &voltage_int);
        if (err == ESP_OK) {
            *voltage_mv = (float)voltage_int;
            return HAL_OK;
        }
    }
    
    /* Fallback: simple linear conversion (less accurate) */
    /* 11dB attenuation: 0-3100mV range for ESP32-S3 */
    float max_voltage = 3100.0f;  /* Approximate for 11dB */
    int max_raw = (1 << s_channel_configs[channel].bitwidth) - 1;
    *voltage_mv = ((float)raw_value / max_raw) * max_voltage;
    
    return HAL_OK;
}

static hal_status_t esp32_adc_calibrate(hal_adc_channel_t channel)
{
    if (channel < 0 || channel >= MAX_ADC_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_channel_configs[channel].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Delete existing calibration if any */
    if (s_cali_handles[channel]) {
#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
        adc_cali_delete_scheme_curve_fitting(s_cali_handles[channel]);
#elif ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
        adc_cali_delete_scheme_line_fitting(s_cali_handles[channel]);
#endif
        s_cali_handles[channel] = NULL;
    }
    
    /* Create calibration handle */
#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT_1,
        .chan = (adc_channel_t)channel,
        .atten = s_channel_configs[channel].atten,
        .bitwidth = s_channel_configs[channel].bitwidth,
    };
    esp_err_t err = adc_cali_create_scheme_curve_fitting(&cali_cfg, &s_cali_handles[channel]);
#elif ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
    adc_cali_line_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT_1,
        .atten = s_channel_configs[channel].atten,
        .bitwidth = s_channel_configs[channel].bitwidth,
    };
    esp_err_t err = adc_cali_create_scheme_line_fitting(&cali_cfg, &s_cali_handles[channel]);
#else
    ESP_LOGW(TAG, "ADC calibration not supported on this chip");
    return HAL_ERROR_NOT_SUPPORTED;
#endif

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create ADC calibration for channel %d: %s",
                 channel, esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    ESP_LOGI(TAG, "ADC channel %d calibrated", channel);
    return HAL_OK;
}

static hal_status_t esp32_adc_start_continuous(hal_adc_channel_t channel, uint32_t sample_rate_hz)
{
    if (channel < 0 || channel >= MAX_ADC_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    /* For simplicity, this implementation uses a single-channel continuous mode */
    /* Multi-channel would require more complex configuration */
    
    if (s_continuous_handle) {
        ESP_LOGW(TAG, "Continuous mode already running");
        return HAL_ERROR_BUSY;
    }
    
    /* Configure continuous ADC */
    adc_continuous_handle_cfg_t adc_cfg = {
        .max_store_buf_size = 1024,
        .conv_frame_size = 256,
    };
    
    esp_err_t err = adc_continuous_new_handle(&adc_cfg, &s_continuous_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create continuous ADC handle: %s", esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    /* Configure channel pattern */
    adc_digi_pattern_config_t pattern = {
        .atten = s_channel_configs[channel].atten,
        .channel = (adc_channel_t)channel,
        .unit = ADC_UNIT_1,
        .bit_width = s_channel_configs[channel].bitwidth,
    };
    
    adc_continuous_config_t cont_cfg = {
        .pattern_num = 1,
        .adc_pattern = &pattern,
        .sample_freq_hz = sample_rate_hz,
        .conv_mode = ADC_CONV_SINGLE_UNIT_1,
        .format = ADC_DIGI_OUTPUT_FORMAT_TYPE2,
    };
    
    err = adc_continuous_config(s_continuous_handle, &cont_cfg);
    if (err != ESP_OK) {
        adc_continuous_deinit(s_continuous_handle);
        s_continuous_handle = NULL;
        return HAL_ERROR;
    }
    
    err = adc_continuous_start(s_continuous_handle);
    if (err != ESP_OK) {
        adc_continuous_deinit(s_continuous_handle);
        s_continuous_handle = NULL;
        return HAL_ERROR;
    }
    
    ESP_LOGI(TAG, "ADC continuous mode started for channel %d at %lu Hz",
             channel, (unsigned long)sample_rate_hz);
    return HAL_OK;
}

static hal_status_t esp32_adc_stop_continuous(hal_adc_channel_t channel)
{
    (void)channel;  /* Currently single-channel continuous mode */
    
    if (!s_continuous_handle) {
        return HAL_ERROR_NOT_READY;
    }
    
    adc_continuous_stop(s_continuous_handle);
    adc_continuous_deinit(s_continuous_handle);
    s_continuous_handle = NULL;
    
    ESP_LOGI(TAG, "ADC continuous mode stopped");
    return HAL_OK;
}

static hal_status_t esp32_adc_get_latest(hal_adc_channel_t channel, uint16_t *value)
{
    if (!s_continuous_handle || !value) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Read latest data from continuous mode buffer */
    uint8_t result[256];
    uint32_t ret_num;
    
    esp_err_t err = adc_continuous_read(s_continuous_handle, result, sizeof(result), 
                                         &ret_num, 0);
    if (err != ESP_OK || ret_num == 0) {
        return HAL_ERROR_TIMEOUT;
    }
    
    /* Parse the last sample (TYPE2 format) */
    adc_digi_output_data_t *data = (adc_digi_output_data_t *)&result[ret_num - sizeof(adc_digi_output_data_t)];
    if (data->type2.channel == channel) {
        *value = data->type2.data;
        return HAL_OK;
    }
    
    return HAL_ERROR_NOT_FOUND;
}

static hal_status_t esp32_adc_deinit(hal_adc_channel_t channel)
{
    if (channel < 0 || channel >= MAX_ADC_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    /* Delete calibration handle */
    if (s_cali_handles[channel]) {
#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
        adc_cali_delete_scheme_curve_fitting(s_cali_handles[channel]);
#elif ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
        adc_cali_delete_scheme_line_fitting(s_cali_handles[channel]);
#endif
        s_cali_handles[channel] = NULL;
    }
    
    s_channel_configs[channel].initialized = false;
    
    /* Check if all channels are deinitialized */
    bool all_deinit = true;
    for (int i = 0; i < MAX_ADC_CHANNELS; i++) {
        if (s_channel_configs[i].initialized) {
            all_deinit = false;
            break;
        }
    }
    
    /* Delete ADC unit handle if all channels deinitialized */
    if (all_deinit && s_adc1_handle) {
        adc_oneshot_del_unit(s_adc1_handle);
        s_adc1_handle = NULL;
    }
    
    ESP_LOGD(TAG, "ADC channel %d deinitialized", channel);
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_adc_ops_t hal_adc_esp32_ops = {
    .init = esp32_adc_init,
    .read_raw = esp32_adc_read_raw,
    .read_voltage = esp32_adc_read_voltage,
    .calibrate = esp32_adc_calibrate,
    .start_continuous = esp32_adc_start_continuous,
    .stop_continuous = esp32_adc_stop_continuous,
    .get_latest = esp32_adc_get_latest,
    .deinit = esp32_adc_deinit
};
