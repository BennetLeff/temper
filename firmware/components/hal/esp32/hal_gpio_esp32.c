/**
 * @file esp32_gpio.c
 * @brief ESP32 GPIO HAL Implementation
 * 
 * Wraps ESP-IDF GPIO driver to implement the HAL GPIO interface.
 * Provides digital I/O with interrupt support for the Temper PCB.
 */

#include "../include/hal_gpio.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "hal_gpio";

/* Maximum GPIO number on ESP32-S3 */
#define ESP32S3_GPIO_MAX    48

/* Track ISR service installation state */
static bool s_isr_service_installed = false;

/* Store ISR context for callback wrapper */
typedef struct {
    hal_gpio_isr_t callback;
    void *arg;
} gpio_isr_context_t;

static gpio_isr_context_t s_isr_contexts[ESP32S3_GPIO_MAX + 1];

/* ============================================================================
 * Internal ISR Handler
 * ============================================================================ */

/**
 * @brief GPIO ISR handler wrapper
 * 
 * Called by ESP-IDF ISR, forwards to HAL callback with correct signature.
 */
static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    uint32_t pin = (uint32_t)(uintptr_t)arg;
    if (pin <= ESP32S3_GPIO_MAX && s_isr_contexts[pin].callback) {
        s_isr_contexts[pin].callback((hal_pin_t)pin, s_isr_contexts[pin].arg);
    }
}

/* ============================================================================
 * HAL Implementation Functions
 * ============================================================================ */

static hal_status_t esp32_gpio_init(hal_pin_t pin, hal_gpio_mode_t mode)
{
    if (pin < 0 || pin > ESP32S3_GPIO_MAX) {
        ESP_LOGE(TAG, "Invalid pin number: %d", (int)pin);
        return HAL_ERROR_INVALID_ARG;
    }
    
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << pin),
        .intr_type = GPIO_INTR_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
    };
    
    switch (mode) {
        case HAL_GPIO_MODE_INPUT:
            io_conf.mode = GPIO_MODE_INPUT;
            break;
        case HAL_GPIO_MODE_OUTPUT:
            io_conf.mode = GPIO_MODE_OUTPUT;
            break;
        case HAL_GPIO_MODE_INPUT_PULLUP:
            io_conf.mode = GPIO_MODE_INPUT;
            io_conf.pull_up_en = GPIO_PULLUP_ENABLE;
            break;
        case HAL_GPIO_MODE_INPUT_PULLDOWN:
            io_conf.mode = GPIO_MODE_INPUT;
            io_conf.pull_down_en = GPIO_PULLDOWN_ENABLE;
            break;
        case HAL_GPIO_MODE_OUTPUT_OD:
            io_conf.mode = GPIO_MODE_OUTPUT_OD;
            break;
        default:
            ESP_LOGE(TAG, "Invalid GPIO mode: %d", mode);
            return HAL_ERROR_INVALID_ARG;
    }
    
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "gpio_config failed for pin %d: %s", (int)pin, esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    ESP_LOGD(TAG, "GPIO %d initialized, mode=%d", (int)pin, mode);
    return HAL_OK;
}

static hal_status_t esp32_gpio_set_level(hal_pin_t pin, hal_gpio_level_t level)
{
    if (pin < 0 || pin > ESP32S3_GPIO_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    esp_err_t err = gpio_set_level((gpio_num_t)pin, level == HAL_GPIO_HIGH ? 1 : 0);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    return HAL_OK;
}

static hal_gpio_level_t esp32_gpio_get_level(hal_pin_t pin)
{
    if (pin < 0 || pin > ESP32S3_GPIO_MAX) {
        return HAL_GPIO_LOW;
    }
    
    return gpio_get_level((gpio_num_t)pin) ? HAL_GPIO_HIGH : HAL_GPIO_LOW;
}

static hal_status_t esp32_gpio_set_interrupt(hal_pin_t pin, hal_gpio_intr_t intr_type,
                                             hal_gpio_isr_t isr, void *arg)
{
    if (pin < 0 || pin > ESP32S3_GPIO_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    /* Install ISR service if not already done */
    if (!s_isr_service_installed) {
        esp_err_t err = gpio_install_isr_service(0);
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "Failed to install GPIO ISR service: %s", esp_err_to_name(err));
            return HAL_ERROR;
        }
        s_isr_service_installed = true;
    }
    
    /* Map HAL interrupt type to ESP-IDF */
    gpio_int_type_t esp_intr_type;
    switch (intr_type) {
        case HAL_GPIO_INTR_DISABLE:
            esp_intr_type = GPIO_INTR_DISABLE;
            break;
        case HAL_GPIO_INTR_RISING:
            esp_intr_type = GPIO_INTR_POSEDGE;
            break;
        case HAL_GPIO_INTR_FALLING:
            esp_intr_type = GPIO_INTR_NEGEDGE;
            break;
        case HAL_GPIO_INTR_BOTH:
            esp_intr_type = GPIO_INTR_ANYEDGE;
            break;
        default:
            return HAL_ERROR_INVALID_ARG;
    }
    
    /* Store callback context */
    s_isr_contexts[pin].callback = isr;
    s_isr_contexts[pin].arg = arg;
    
    /* Configure interrupt */
    esp_err_t err = gpio_set_intr_type((gpio_num_t)pin, esp_intr_type);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Add ISR handler */
    err = gpio_isr_handler_add((gpio_num_t)pin, gpio_isr_handler, (void *)(uintptr_t)pin);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Enable interrupt */
    err = gpio_intr_enable((gpio_num_t)pin);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    ESP_LOGD(TAG, "GPIO %d interrupt configured, type=%d", (int)pin, intr_type);
    return HAL_OK;
}

static hal_status_t esp32_gpio_disable_interrupt(hal_pin_t pin)
{
    if (pin < 0 || pin > ESP32S3_GPIO_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    esp_err_t err = gpio_intr_disable((gpio_num_t)pin);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    err = gpio_isr_handler_remove((gpio_num_t)pin);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Clear callback context */
    s_isr_contexts[pin].callback = NULL;
    s_isr_contexts[pin].arg = NULL;
    
    return HAL_OK;
}

static hal_status_t esp32_gpio_deinit(hal_pin_t pin)
{
    if (pin < 0 || pin > ESP32S3_GPIO_MAX) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    /* Disable any interrupt */
    gpio_intr_disable((gpio_num_t)pin);
    gpio_isr_handler_remove((gpio_num_t)pin);
    
    /* Reset pin to default state */
    esp_err_t err = gpio_reset_pin((gpio_num_t)pin);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Clear callback context */
    s_isr_contexts[pin].callback = NULL;
    s_isr_contexts[pin].arg = NULL;
    
    ESP_LOGD(TAG, "GPIO %d deinitialized", (int)pin);
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_gpio_ops_t hal_gpio_esp32_ops = {
    .init = esp32_gpio_init,
    .set_level = esp32_gpio_set_level,
    .get_level = esp32_gpio_get_level,
    .set_interrupt = esp32_gpio_set_interrupt,
    .disable_interrupt = esp32_gpio_disable_interrupt,
    .deinit = esp32_gpio_deinit
};
