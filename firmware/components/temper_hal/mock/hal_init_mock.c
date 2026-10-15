/**
 * @file hal_init_mock.c
 * @brief Mock HAL initialization
 * 
 * Sets up all HAL interfaces with mock implementations for testing.
 */

#include "../include/hal.h"
#include <string.h>
#include <stdbool.h>
#include <stddef.h>

/* External mock operations declarations */
extern const hal_gpio_ops_t hal_gpio_mock_ops;
extern const hal_adc_ops_t hal_adc_mock_ops;
extern const hal_pwm_ops_t hal_pwm_mock_ops;
extern const hal_spi_ops_t hal_spi_mock_ops;
extern const hal_timer_ops_t hal_timer_mock_ops;

/* Global HAL operation pointers */
const hal_gpio_ops_t *hal_gpio = NULL;
const hal_adc_ops_t *hal_adc = NULL;
const hal_pwm_ops_t *hal_pwm = NULL;
const hal_spi_ops_t *hal_spi = NULL;
const hal_timer_ops_t *hal_timer = NULL;

static bool s_hal_initialized = false;

/* Setter functions */
void hal_gpio_set_ops(const hal_gpio_ops_t *ops) { hal_gpio = ops; }
void hal_adc_set_ops(const hal_adc_ops_t *ops) { hal_adc = ops; }
void hal_pwm_set_ops(const hal_pwm_ops_t *ops) { hal_pwm = ops; }
void hal_spi_set_ops(const hal_spi_ops_t *ops) { hal_spi = ops; }
void hal_timer_set_ops(const hal_timer_ops_t *ops) { hal_timer = ops; }

hal_status_t hal_init(void)
{
    /* For mock builds, hal_init() also uses mock implementations */
    return hal_init_mock();
}

hal_status_t hal_init_mock(void)
{
    if (s_hal_initialized) {
        return HAL_OK;
    }
    
    hal_gpio = &hal_gpio_mock_ops;
    hal_adc = &hal_adc_mock_ops;
    hal_pwm = &hal_pwm_mock_ops;
    hal_spi = &hal_spi_mock_ops;
    hal_timer = &hal_timer_mock_ops;
    
    s_hal_initialized = true;
    return HAL_OK;
}

hal_status_t hal_deinit(void)
{
    hal_gpio = NULL;
    hal_adc = NULL;
    hal_pwm = NULL;
    hal_spi = NULL;
    hal_timer = NULL;
    
    s_hal_initialized = false;
    return HAL_OK;
}

bool hal_is_initialized(void)
{
    return s_hal_initialized;
}
