/**
 * @file hal_types.h
 * @brief Common HAL types and definitions
 * 
 * Provides platform-independent types for the Hardware Abstraction Layer.
 * All HAL modules include this header for consistent typing.
 */

#ifndef HAL_TYPES_H
#define HAL_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Status Codes
 * ============================================================================ */

/**
 * @brief HAL function return status
 */
typedef enum {
    HAL_OK = 0,             /**< Operation successful */
    HAL_ERROR,              /**< Generic error */
    HAL_ERROR_INVALID_ARG,  /**< Invalid argument */
    HAL_ERROR_NOT_FOUND,    /**< Resource not found */
    HAL_ERROR_NO_MEM,       /**< Out of memory */
    HAL_ERROR_TIMEOUT,      /**< Operation timed out */
    HAL_ERROR_NOT_READY,    /**< Resource not ready */
    HAL_ERROR_BUSY,         /**< Resource busy */
    HAL_ERROR_NOT_SUPPORTED /**< Feature not supported */
} hal_status_t;

/* ============================================================================
 * GPIO Types
 * ============================================================================ */

/**
 * @brief GPIO pin identifier
 * 
 * Platform-specific mapping:
 * - ESP32: GPIO number (0-48)
 * - Mock: Virtual pin number
 */
typedef int32_t hal_pin_t;

/**
 * @brief Invalid pin marker
 */
#define HAL_PIN_INVALID (-1)

/**
 * @brief GPIO pin modes
 */
typedef enum {
    HAL_GPIO_MODE_INPUT,           /**< Digital input */
    HAL_GPIO_MODE_OUTPUT,          /**< Digital output */
    HAL_GPIO_MODE_INPUT_PULLUP,    /**< Input with internal pull-up */
    HAL_GPIO_MODE_INPUT_PULLDOWN,  /**< Input with internal pull-down */
    HAL_GPIO_MODE_OUTPUT_OD        /**< Open-drain output */
} hal_gpio_mode_t;

/**
 * @brief GPIO logic level
 */
typedef enum {
    HAL_GPIO_LOW = 0,
    HAL_GPIO_HIGH = 1
} hal_gpio_level_t;

/**
 * @brief GPIO interrupt edge trigger
 */
typedef enum {
    HAL_GPIO_INTR_DISABLE,      /**< Interrupt disabled */
    HAL_GPIO_INTR_RISING,       /**< Rising edge trigger */
    HAL_GPIO_INTR_FALLING,      /**< Falling edge trigger */
    HAL_GPIO_INTR_BOTH          /**< Both edges trigger */
} hal_gpio_intr_t;

/**
 * @brief GPIO interrupt callback
 * 
 * @param pin Pin that triggered interrupt
 * @param arg User-provided argument
 */
typedef void (*hal_gpio_isr_t)(hal_pin_t pin, void *arg);

/* ============================================================================
 * ADC Types
 * ============================================================================ */

/**
 * @brief ADC channel identifier
 * 
 * Platform-specific mapping:
 * - ESP32: ADC1_CHANNEL_x or ADC2_CHANNEL_x
 * - Mock: Virtual channel number
 */
typedef int32_t hal_adc_channel_t;

/**
 * @brief ADC attenuation (input range)
 */
typedef enum {
    HAL_ADC_ATTEN_0dB,      /**< 0-1.1V (ESP32) */
    HAL_ADC_ATTEN_2_5dB,    /**< 0-1.5V */
    HAL_ADC_ATTEN_6dB,      /**< 0-2.2V */
    HAL_ADC_ATTEN_11dB      /**< 0-3.3V (full range) */
} hal_adc_atten_t;

/**
 * @brief ADC resolution
 */
typedef enum {
    HAL_ADC_WIDTH_9BIT = 9,
    HAL_ADC_WIDTH_10BIT = 10,
    HAL_ADC_WIDTH_11BIT = 11,
    HAL_ADC_WIDTH_12BIT = 12,
    HAL_ADC_WIDTH_13BIT = 13   /**< ESP32-S3 supports 13-bit */
} hal_adc_width_t;

/* ============================================================================
 * PWM Types
 * ============================================================================ */

/**
 * @brief PWM channel identifier
 */
typedef int32_t hal_pwm_channel_t;

/**
 * @brief PWM configuration
 */
typedef struct {
    uint32_t frequency_hz;      /**< PWM frequency in Hz */
    float duty_percent;         /**< Initial duty cycle (0-100%) */
    uint16_t dead_time_ns;      /**< Dead-time in nanoseconds (for complementary) */
    hal_pin_t pin_high;         /**< High-side output pin */
    hal_pin_t pin_low;          /**< Low-side output pin (HAL_PIN_INVALID if not used) */
    bool complementary;         /**< Enable complementary output */
} hal_pwm_config_t;

/* ============================================================================
 * SPI Types
 * ============================================================================ */

/**
 * @brief SPI bus identifier
 */
typedef int32_t hal_spi_bus_t;

/**
 * @brief SPI device handle
 */
typedef void* hal_spi_device_t;

/**
 * @brief SPI configuration
 */
typedef struct {
    uint32_t clock_hz;          /**< SPI clock frequency */
    uint8_t mode;               /**< SPI mode (0-3) */
    hal_pin_t pin_mosi;         /**< MOSI pin */
    hal_pin_t pin_miso;         /**< MISO pin */
    hal_pin_t pin_sclk;         /**< Clock pin */
    hal_pin_t pin_cs;           /**< Chip select pin */
    bool cs_active_high;        /**< CS polarity */
} hal_spi_config_t;

/**
 * @brief SPI transaction descriptor
 */
typedef struct {
    const uint8_t *tx_buffer;   /**< Data to transmit (NULL for read-only) */
    uint8_t *rx_buffer;         /**< Buffer for received data (NULL for write-only) */
    size_t length;              /**< Transaction length in bytes */
} hal_spi_transaction_t;

/* ============================================================================
 * Timer Types
 * ============================================================================ */

/**
 * @brief Timer identifier
 */
typedef int32_t hal_timer_t;

/**
 * @brief Timer callback function
 * 
 * @param timer Timer that triggered callback
 * @param arg User-provided argument
 */
typedef void (*hal_timer_callback_t)(hal_timer_t timer, void *arg);

/**
 * @brief Timer configuration
 */
typedef struct {
    uint32_t period_us;         /**< Timer period in microseconds */
    bool auto_reload;           /**< Auto-reload on expiry */
    hal_timer_callback_t callback;  /**< Callback function */
    void *callback_arg;         /**< Callback argument */
} hal_timer_config_t;

/* ============================================================================
 * Time Types
 * ============================================================================ */

/**
 * @brief Timestamp in microseconds
 */
typedef uint64_t hal_time_us_t;

/**
 * @brief Timestamp in milliseconds
 */
typedef uint32_t hal_time_ms_t;

#ifdef __cplusplus
}
#endif

#endif /* HAL_TYPES_H */
