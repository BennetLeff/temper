/**
 * @file hal_init.c
 * @brief ESP32 HAL Initialization
 * 
 * Initializes all HAL subsystems and wires up ESP32 implementations
 * to the global HAL operation pointers.
 */

#include "../include/hal.h"
#include "../include/hal_gpio.h"
#include "../include/hal_adc.h"
#include "../include/hal_pwm.h"
#include "../include/hal_spi.h"
#include "../include/hal_timer.h"
#include "driver/gpio.h"
#include "esp_log.h"

static const char *TAG = "hal_esp32";

/* External declarations for ESP32 operation structs */
extern const hal_gpio_ops_t hal_gpio_esp32_ops;
extern const hal_adc_ops_t hal_adc_esp32_ops;
extern const hal_pwm_ops_t hal_pwm_esp32_ops;
extern const hal_spi_ops_t hal_spi_esp32_ops;
extern const hal_timer_ops_t hal_timer_esp32_ops;

/* Global HAL operation pointers (defined in each HAL header) */
const hal_gpio_ops_t *hal_gpio = NULL;
const hal_adc_ops_t *hal_adc = NULL;
const hal_pwm_ops_t *hal_pwm = NULL;
const hal_spi_ops_t *hal_spi = NULL;
const hal_timer_ops_t *hal_timer = NULL;

/**
 * @brief Initialize ESP32 HAL
 * 
 * Wires up all ESP32 HAL implementations and performs any
 * global initialization required by the peripherals.
 * 
 * @return HAL_OK on success
 */
hal_status_t hal_esp32_init(void)
{
    ESP_LOGI(TAG, "Initializing ESP32 HAL");
    
    /* Install GPIO ISR service globally (required before any GPIO interrupts) */
    esp_err_t err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "Failed to install GPIO ISR service: %s", esp_err_to_name(err));
        /* Continue anyway - individual GPIO init will fail if needed */
    }
    
    /* Wire up all HAL implementations */
    hal_gpio = &hal_gpio_esp32_ops;
    hal_adc = &hal_adc_esp32_ops;
    hal_pwm = &hal_pwm_esp32_ops;
    hal_spi = &hal_spi_esp32_ops;
    hal_timer = &hal_timer_esp32_ops;
    
    ESP_LOGI(TAG, "ESP32 HAL initialized successfully");
    ESP_LOGI(TAG, "  GPIO:  %p", (void*)hal_gpio);
    ESP_LOGI(TAG, "  ADC:   %p", (void*)hal_adc);
    ESP_LOGI(TAG, "  PWM:   %p", (void*)hal_pwm);
    ESP_LOGI(TAG, "  SPI:   %p", (void*)hal_spi);
    ESP_LOGI(TAG, "  Timer: %p", (void*)hal_timer);
    
    return HAL_OK;
}

/**
 * @brief Deinitialize ESP32 HAL
 * 
 * Cleans up all HAL resources. After calling this, HAL functions
 * will return HAL_ERROR_NOT_READY until hal_esp32_init() is called again.
 * 
 * @return HAL_OK on success
 */
hal_status_t hal_esp32_deinit(void)
{
    ESP_LOGI(TAG, "Deinitializing ESP32 HAL");
    
    /* Clear all HAL pointers */
    hal_gpio = NULL;
    hal_adc = NULL;
    hal_pwm = NULL;
    hal_spi = NULL;
    hal_timer = NULL;
    
    /* Uninstall GPIO ISR service */
    gpio_uninstall_isr_service();
    
    ESP_LOGI(TAG, "ESP32 HAL deinitialized");
    return HAL_OK;
}

/* ============================================================================
 * HAL Operation Setter Functions
 * 
 * These allow runtime switching of HAL implementations (e.g., for testing)
 * ============================================================================ */

void hal_gpio_set_ops(const hal_gpio_ops_t *ops)
{
    hal_gpio = ops;
}

void hal_adc_set_ops(const hal_adc_ops_t *ops)
{
    hal_adc = ops;
}

void hal_pwm_set_ops(const hal_pwm_ops_t *ops)
{
    hal_pwm = ops;
}

void hal_spi_set_ops(const hal_spi_ops_t *ops)
{
    hal_spi = ops;
}

void hal_timer_set_ops(const hal_timer_ops_t *ops)
{
    hal_timer = ops;
}
