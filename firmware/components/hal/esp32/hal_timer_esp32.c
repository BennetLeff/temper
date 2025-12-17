/**
 * @file esp32_timer.c
 * @brief ESP32 Timer HAL Implementation
 * 
 * Uses ESP-IDF esp_timer for high-resolution timestamps and gptimer
 * for hardware timer callbacks. Supports input capture for ZCD timing.
 */

#include "../include/hal_timer.h"
#include "esp_timer.h"
#include "driver/gptimer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rom/ets_sys.h"
#include <string.h>

static const char *TAG = "hal_timer";

/* Maximum number of hardware timers */
#define MAX_TIMERS  4

/* Timer instance state */
typedef struct {
    bool initialized;
    gptimer_handle_t handle;
    hal_timer_callback_t callback;
    void *callback_arg;
    uint32_t period_us;
} timer_instance_t;

static timer_instance_t s_timers[MAX_TIMERS];

/* Capture callback storage */
typedef struct {
    hal_capture_callback_t callback;
    void *arg;
    hal_timer_t timer;
} capture_context_t;

static capture_context_t s_capture_contexts[MAX_TIMERS];

/* ============================================================================
 * Internal Callback Handler
 * ============================================================================ */

/**
 * @brief GPTimer alarm callback (runs in ISR context)
 */
static bool IRAM_ATTR timer_alarm_callback(gptimer_handle_t timer, 
                                            const gptimer_alarm_event_data_t *edata,
                                            void *user_ctx)
{
    timer_instance_t *inst = (timer_instance_t *)user_ctx;
    if (inst && inst->callback) {
        /* Find timer index */
        for (int i = 0; i < MAX_TIMERS; i++) {
            if (&s_timers[i] == inst) {
                inst->callback((hal_timer_t)i, inst->callback_arg);
                break;
            }
        }
    }
    return false;  /* No high-priority task woken */
}

/* ============================================================================
 * HAL Implementation Functions
 * ============================================================================ */

static hal_status_t esp32_timer_init(hal_timer_t timer, const hal_timer_config_t *config)
{
    if (timer < 0 || timer >= MAX_TIMERS || !config) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    timer_instance_t *inst = &s_timers[timer];
    if (inst->initialized) {
        ESP_LOGW(TAG, "Timer %d already initialized", timer);
        return HAL_ERROR_BUSY;
    }
    
    /* Create GPTimer */
    gptimer_config_t timer_cfg = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,  /* 1 MHz = 1 µs resolution */
    };
    
    esp_err_t err = gptimer_new_timer(&timer_cfg, &inst->handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create timer %d: %s", timer, esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    /* Configure alarm if periodic */
    if (config->period_us > 0) {
        gptimer_alarm_config_t alarm_cfg = {
            .alarm_count = config->period_us,
            .reload_count = 0,
            .flags.auto_reload_on_alarm = config->auto_reload,
        };
        
        err = gptimer_set_alarm_action(inst->handle, &alarm_cfg);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to set alarm for timer %d: %s", timer, esp_err_to_name(err));
            gptimer_del_timer(inst->handle);
            return HAL_ERROR;
        }
        
        /* Register callback if provided */
        if (config->callback) {
            gptimer_event_callbacks_t cbs = {
                .on_alarm = timer_alarm_callback,
            };
            
            err = gptimer_register_event_callbacks(inst->handle, &cbs, inst);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to register callback for timer %d: %s", 
                         timer, esp_err_to_name(err));
                gptimer_del_timer(inst->handle);
                return HAL_ERROR;
            }
        }
    }
    
    /* Store configuration */
    inst->callback = config->callback;
    inst->callback_arg = config->callback_arg;
    inst->period_us = config->period_us;
    inst->initialized = true;
    
    /* Enable timer */
    err = gptimer_enable(inst->handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable timer %d: %s", timer, esp_err_to_name(err));
        gptimer_del_timer(inst->handle);
        inst->initialized = false;
        return HAL_ERROR;
    }
    
    ESP_LOGI(TAG, "Timer %d initialized, period=%lu us", timer, (unsigned long)config->period_us);
    return HAL_OK;
}

static hal_status_t esp32_timer_start(hal_timer_t timer)
{
    if (timer < 0 || timer >= MAX_TIMERS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    timer_instance_t *inst = &s_timers[timer];
    if (!inst->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    esp_err_t err = gptimer_start(inst->handle);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    return HAL_OK;
}

static hal_status_t esp32_timer_stop(hal_timer_t timer)
{
    if (timer < 0 || timer >= MAX_TIMERS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    timer_instance_t *inst = &s_timers[timer];
    if (!inst->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    esp_err_t err = gptimer_stop(inst->handle);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    return HAL_OK;
}

static uint64_t esp32_timer_get_count(hal_timer_t timer)
{
    if (timer < 0 || timer >= MAX_TIMERS) {
        return 0;
    }
    
    timer_instance_t *inst = &s_timers[timer];
    if (!inst->initialized) {
        return 0;
    }
    
    uint64_t count;
    if (gptimer_get_raw_count(inst->handle, &count) != ESP_OK) {
        return 0;
    }
    
    return count;
}

static hal_status_t esp32_timer_set_period(hal_timer_t timer, uint32_t period_us)
{
    if (timer < 0 || timer >= MAX_TIMERS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    timer_instance_t *inst = &s_timers[timer];
    if (!inst->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    gptimer_alarm_config_t alarm_cfg = {
        .alarm_count = period_us,
        .reload_count = 0,
        .flags.auto_reload_on_alarm = true,
    };
    
    esp_err_t err = gptimer_set_alarm_action(inst->handle, &alarm_cfg);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    inst->period_us = period_us;
    return HAL_OK;
}

static hal_status_t esp32_timer_configure_capture(hal_timer_t timer, hal_pin_t pin,
                                                   hal_gpio_intr_t edge,
                                                   hal_capture_callback_t callback, void *arg)
{
    /* For simplicity, we use GPIO interrupt + esp_timer timestamp for capture.
     * A more accurate implementation would use MCPWM capture peripheral. */
    
    (void)timer;
    (void)pin;
    (void)edge;
    (void)callback;
    (void)arg;
    
    /* TODO: Implement using MCPWM capture or GPIO interrupt with timestamp */
    ESP_LOGW(TAG, "Input capture not yet implemented - use GPIO interrupt for now");
    return HAL_ERROR_NOT_SUPPORTED;
}

static hal_time_us_t esp32_timer_get_time_us(void)
{
    return (hal_time_us_t)esp_timer_get_time();
}

static hal_time_ms_t esp32_timer_get_time_ms(void)
{
    return (hal_time_ms_t)(esp_timer_get_time() / 1000);
}

static void esp32_timer_delay_us(uint32_t us)
{
    if (us < 10) {
        /* Very short delays use ROM delay function */
        ets_delay_us(us);
    } else {
        /* Longer delays use esp_rom_delay_us */
        ets_delay_us(us);
    }
}

static void esp32_timer_delay_ms(uint32_t ms)
{
    if (ms >= 10) {
        /* Use FreeRTOS delay for longer waits (yields to scheduler) */
        vTaskDelay(pdMS_TO_TICKS(ms));
    } else {
        /* Short delays busy-wait to avoid scheduler overhead */
        esp32_timer_delay_us(ms * 1000);
    }
}

static hal_status_t esp32_timer_deinit(hal_timer_t timer)
{
    if (timer < 0 || timer >= MAX_TIMERS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    timer_instance_t *inst = &s_timers[timer];
    if (!inst->initialized) {
        return HAL_OK;
    }
    
    /* Stop and disable timer */
    gptimer_stop(inst->handle);
    gptimer_disable(inst->handle);
    
    /* Delete timer */
    esp_err_t err = gptimer_del_timer(inst->handle);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    memset(inst, 0, sizeof(timer_instance_t));
    
    ESP_LOGI(TAG, "Timer %d deinitialized", timer);
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_timer_ops_t hal_timer_esp32_ops = {
    .init = esp32_timer_init,
    .start = esp32_timer_start,
    .stop = esp32_timer_stop,
    .get_count = esp32_timer_get_count,
    .set_period = esp32_timer_set_period,
    .configure_capture = esp32_timer_configure_capture,
    .get_time_us = esp32_timer_get_time_us,
    .get_time_ms = esp32_timer_get_time_ms,
    .delay_us = esp32_timer_delay_us,
    .delay_ms = esp32_timer_delay_ms,
    .deinit = esp32_timer_deinit
};
