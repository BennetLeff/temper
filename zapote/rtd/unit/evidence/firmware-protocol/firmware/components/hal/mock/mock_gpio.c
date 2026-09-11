/**
 * @file mock_gpio.c
 * @brief Mock GPIO implementation for testing
 * 
 * Provides simulated GPIO with:
 * - State tracking for verification
 * - Programmable input levels
 * - Interrupt simulation
 * - Call recording for test assertions
 */

#include "../include/hal_gpio.h"
#include <string.h>
#include <stdbool.h>
#include <stddef.h>

/* Maximum number of GPIO pins to track */
#define MOCK_GPIO_MAX_PINS 64

/* Per-pin state */
typedef struct {
    bool initialized;
    hal_gpio_mode_t mode;
    hal_gpio_level_t output_level;      /* What we set */
    hal_gpio_level_t input_level;       /* What get_level returns */
    hal_gpio_intr_t intr_type;
    hal_gpio_isr_t isr;
    void *isr_arg;
} mock_gpio_pin_t;

/* Global mock state */
static mock_gpio_pin_t s_pins[MOCK_GPIO_MAX_PINS];
static uint32_t s_call_count_init = 0;
static uint32_t s_call_count_set_level = 0;
static uint32_t s_call_count_get_level = 0;

/* ============================================================================
 * Mock Control Functions (for test setup)
 * ============================================================================ */

/**
 * @brief Reset all mock GPIO state
 */
void mock_gpio_reset(void)
{
    memset(s_pins, 0, sizeof(s_pins));
    s_call_count_init = 0;
    s_call_count_set_level = 0;
    s_call_count_get_level = 0;
}

/**
 * @brief Set what get_level will return for a pin
 */
void mock_gpio_set_input_level(hal_pin_t pin, hal_gpio_level_t level)
{
    if (pin >= 0 && pin < MOCK_GPIO_MAX_PINS) {
        s_pins[pin].input_level = level;
    }
}

/**
 * @brief Get the output level that was set on a pin
 */
hal_gpio_level_t mock_gpio_get_output_level(hal_pin_t pin)
{
    if (pin >= 0 && pin < MOCK_GPIO_MAX_PINS) {
        return s_pins[pin].output_level;
    }
    return HAL_GPIO_LOW;
}

/**
 * @brief Check if pin is initialized
 */
bool mock_gpio_is_initialized(hal_pin_t pin)
{
    if (pin >= 0 && pin < MOCK_GPIO_MAX_PINS) {
        return s_pins[pin].initialized;
    }
    return false;
}

/**
 * @brief Get pin mode
 */
hal_gpio_mode_t mock_gpio_get_mode(hal_pin_t pin)
{
    if (pin >= 0 && pin < MOCK_GPIO_MAX_PINS) {
        return s_pins[pin].mode;
    }
    return HAL_GPIO_MODE_INPUT;
}

/**
 * @brief Simulate an interrupt on a pin
 */
void mock_gpio_trigger_interrupt(hal_pin_t pin)
{
    if (pin >= 0 && pin < MOCK_GPIO_MAX_PINS) {
        if (s_pins[pin].isr != NULL) {
            s_pins[pin].isr(pin, s_pins[pin].isr_arg);
        }
    }
}

/**
 * @brief Get call counts for verification
 */
uint32_t mock_gpio_get_init_count(void) { return s_call_count_init; }
uint32_t mock_gpio_get_set_level_count(void) { return s_call_count_set_level; }
uint32_t mock_gpio_get_get_level_count(void) { return s_call_count_get_level; }

/* ============================================================================
 * HAL Implementation Functions
 * ============================================================================ */

static hal_status_t mock_gpio_init(hal_pin_t pin, hal_gpio_mode_t mode)
{
    s_call_count_init++;
    
    if (pin < 0 || pin >= MOCK_GPIO_MAX_PINS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_pins[pin].initialized = true;
    s_pins[pin].mode = mode;
    s_pins[pin].output_level = HAL_GPIO_LOW;
    s_pins[pin].input_level = HAL_GPIO_LOW;
    
    return HAL_OK;
}

static hal_status_t mock_gpio_set_level(hal_pin_t pin, hal_gpio_level_t level)
{
    s_call_count_set_level++;
    
    if (pin < 0 || pin >= MOCK_GPIO_MAX_PINS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_pins[pin].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    s_pins[pin].output_level = level;
    return HAL_OK;
}

static hal_gpio_level_t mock_gpio_get_level(hal_pin_t pin)
{
    s_call_count_get_level++;
    
    if (pin < 0 || pin >= MOCK_GPIO_MAX_PINS) {
        return HAL_GPIO_LOW;
    }
    
    /* For output pins, return what was set; for input pins, return injected value */
    if (s_pins[pin].mode == HAL_GPIO_MODE_OUTPUT || 
        s_pins[pin].mode == HAL_GPIO_MODE_OUTPUT_OD) {
        return s_pins[pin].output_level;
    }
    return s_pins[pin].input_level;
}

static hal_status_t mock_gpio_set_interrupt(hal_pin_t pin, hal_gpio_intr_t intr_type,
                                            hal_gpio_isr_t isr, void *arg)
{
    if (pin < 0 || pin >= MOCK_GPIO_MAX_PINS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_pins[pin].intr_type = intr_type;
    s_pins[pin].isr = isr;
    s_pins[pin].isr_arg = arg;
    
    return HAL_OK;
}

static hal_status_t mock_gpio_disable_interrupt(hal_pin_t pin)
{
    if (pin < 0 || pin >= MOCK_GPIO_MAX_PINS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_pins[pin].intr_type = HAL_GPIO_INTR_DISABLE;
    s_pins[pin].isr = NULL;
    s_pins[pin].isr_arg = NULL;
    
    return HAL_OK;
}

static hal_status_t mock_gpio_deinit(hal_pin_t pin)
{
    if (pin < 0 || pin >= MOCK_GPIO_MAX_PINS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    memset(&s_pins[pin], 0, sizeof(mock_gpio_pin_t));
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_gpio_ops_t hal_gpio_mock_ops = {
    .init = mock_gpio_init,
    .set_level = mock_gpio_set_level,
    .get_level = mock_gpio_get_level,
    .set_interrupt = mock_gpio_set_interrupt,
    .disable_interrupt = mock_gpio_disable_interrupt,
    .deinit = mock_gpio_deinit
};
