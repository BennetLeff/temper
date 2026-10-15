/**
 * @file hal_adc.h
 * @brief ADC Hardware Abstraction Layer
 * 
 * Provides platform-independent ADC operations for:
 * - Single-shot readings
 * - Voltage conversion with calibration
 * - Continuous mode for high-speed sampling
 * 
 * Used by:
 * - Current sensing (CT secondary voltage)
 * - Voltage sensing (bus voltage via divider)
 * - Analog inputs
 */

#ifndef HAL_ADC_H
#define HAL_ADC_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief ADC channel configuration
 */
typedef struct {
    hal_adc_channel_t channel;  /**< ADC channel number */
    hal_adc_atten_t atten;      /**< Input attenuation */
    hal_adc_width_t width;      /**< Resolution in bits */
} hal_adc_config_t;

/**
 * @brief ADC operations interface
 */
typedef struct {
    /**
     * @brief Initialize ADC channel
     * 
     * @param config Channel configuration
     * @return HAL_OK on success
     */
    hal_status_t (*init)(const hal_adc_config_t *config);
    
    /**
     * @brief Read raw ADC value
     * 
     * @param channel ADC channel
     * @param value Pointer to store raw value
     * @return HAL_OK on success
     */
    hal_status_t (*read_raw)(hal_adc_channel_t channel, uint16_t *value);
    
    /**
     * @brief Read calibrated voltage
     * 
     * @param channel ADC channel
     * @param voltage_mv Pointer to store voltage in millivolts
     * @return HAL_OK on success
     */
    hal_status_t (*read_voltage)(hal_adc_channel_t channel, float *voltage_mv);
    
    /**
     * @brief Calibrate ADC channel
     * 
     * Should be called once after init for accurate voltage readings.
     * 
     * @param channel ADC channel
     * @return HAL_OK on success
     */
    hal_status_t (*calibrate)(hal_adc_channel_t channel);
    
    /**
     * @brief Start continuous sampling mode
     * 
     * @param channel ADC channel
     * @param sample_rate_hz Desired sample rate
     * @return HAL_OK on success
     */
    hal_status_t (*start_continuous)(hal_adc_channel_t channel, uint32_t sample_rate_hz);
    
    /**
     * @brief Stop continuous sampling
     * 
     * @param channel ADC channel
     * @return HAL_OK on success
     */
    hal_status_t (*stop_continuous)(hal_adc_channel_t channel);
    
    /**
     * @brief Get latest value from continuous mode
     * 
     * @param channel ADC channel
     * @param value Pointer to store value
     * @return HAL_OK on success
     */
    hal_status_t (*get_latest)(hal_adc_channel_t channel, uint16_t *value);
    
    /**
     * @brief Deinitialize ADC channel
     * 
     * @param channel ADC channel
     * @return HAL_OK on success
     */
    hal_status_t (*deinit)(hal_adc_channel_t channel);
} hal_adc_ops_t;

/**
 * @brief Global ADC operations pointer
 */
extern const hal_adc_ops_t *hal_adc;

/**
 * @brief Set ADC operations implementation
 */
void hal_adc_set_ops(const hal_adc_ops_t *ops);

/* ============================================================================
 * Convenience Macros
 * ============================================================================ */

/**
 * @brief Read ADC voltage (convenience wrapper)
 */
#define HAL_ADC_READ_VOLTAGE(channel, voltage_ptr) \
    (hal_adc ? hal_adc->read_voltage((channel), (voltage_ptr)) : HAL_ERROR_NOT_READY)

/**
 * @brief Read raw ADC value (convenience wrapper)
 */
#define HAL_ADC_READ_RAW(channel, value_ptr) \
    (hal_adc ? hal_adc->read_raw((channel), (value_ptr)) : HAL_ERROR_NOT_READY)

#ifdef __cplusplus
}
#endif

#endif /* HAL_ADC_H */
