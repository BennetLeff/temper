/**
 * @file hal_gpio.h
 * @brief GPIO Hardware Abstraction Layer
 * 
 * Provides platform-independent GPIO operations for:
 * - Digital input/output
 * - Interrupt configuration
 * - Pull-up/pull-down resistors
 */

#ifndef HAL_GPIO_H
#define HAL_GPIO_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief GPIO operations interface
 * 
 * Function pointer struct for runtime binding.
 * Allows swapping implementations (ESP32, mock, etc.)
 */
typedef struct {
    /**
     * @brief Initialize GPIO pin
     * 
     * @param pin Pin number
     * @param mode Pin mode (input/output/etc.)
     * @return HAL_OK on success
     */
    hal_status_t (*init)(hal_pin_t pin, hal_gpio_mode_t mode);
    
    /**
     * @brief Set GPIO output level
     * 
     * @param pin Pin number
     * @param level Logic level (HIGH/LOW)
     * @return HAL_OK on success
     */
    hal_status_t (*set_level)(hal_pin_t pin, hal_gpio_level_t level);
    
    /**
     * @brief Get GPIO input level
     * 
     * @param pin Pin number
     * @return Current logic level
     */
    hal_gpio_level_t (*get_level)(hal_pin_t pin);
    
    /**
     * @brief Configure interrupt on GPIO
     * 
     * @param pin Pin number
     * @param intr_type Interrupt edge trigger type
     * @param isr Interrupt service routine
     * @param arg User argument for ISR
     * @return HAL_OK on success
     */
    hal_status_t (*set_interrupt)(hal_pin_t pin, hal_gpio_intr_t intr_type,
                                  hal_gpio_isr_t isr, void *arg);
    
    /**
     * @brief Disable interrupt on GPIO
     * 
     * @param pin Pin number
     * @return HAL_OK on success
     */
    hal_status_t (*disable_interrupt)(hal_pin_t pin);
    
    /**
     * @brief Deinitialize GPIO pin
     * 
     * @param pin Pin number
     * @return HAL_OK on success
     */
    hal_status_t (*deinit)(hal_pin_t pin);
} hal_gpio_ops_t;

/**
 * @brief Global GPIO operations pointer
 * 
 * Set this to point to the appropriate implementation:
 * - &hal_gpio_esp32_ops for ESP32
 * - &hal_gpio_mock_ops for testing
 */
extern const hal_gpio_ops_t *hal_gpio;

/**
 * @brief Set GPIO operations implementation
 * 
 * @param ops Pointer to operations struct
 */
void hal_gpio_set_ops(const hal_gpio_ops_t *ops);

/* ============================================================================
 * Convenience Macros
 * ============================================================================ */

/**
 * @brief Initialize GPIO pin (convenience wrapper)
 */
#define HAL_GPIO_INIT(pin, mode) \
    (hal_gpio ? hal_gpio->init((pin), (mode)) : HAL_ERROR_NOT_READY)

/**
 * @brief Set GPIO level (convenience wrapper)
 */
#define HAL_GPIO_SET(pin, level) \
    (hal_gpio ? hal_gpio->set_level((pin), (level)) : HAL_ERROR_NOT_READY)

/**
 * @brief Get GPIO level (convenience wrapper)
 */
#define HAL_GPIO_GET(pin) \
    (hal_gpio ? hal_gpio->get_level(pin) : HAL_GPIO_LOW)

#ifdef __cplusplus
}
#endif

#endif /* HAL_GPIO_H */
