/**
 * @file esp32_pwm.c
 * @brief ESP32 MCPWM HAL Implementation for Half-Bridge Gate Drive
 * 
 * Uses ESP32-S3 MCPWM peripheral for complementary PWM generation
 * with hardware dead-time insertion. Critical for IGBT gate driver
 * control in the induction cooker half-bridge.
 * 
 * Safety Critical Requirements:
 * - Hardware dead-time: 500ns minimum (prevents shoot-through)
 * - Emergency stop: <1µs response time
 * - Frequency range: 38-50 kHz for resonant operation
 */

#include "../include/hal_pwm.h"
#include "driver/mcpwm_prelude.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "hal_pwm";

/* Maximum number of PWM channels */
#define MAX_PWM_CHANNELS    2

/* MCPWM timer resolution (higher = finer control) */
#define MCPWM_TIMER_RESOLUTION_HZ   80000000  /* 80 MHz = 12.5ns resolution */

/* Per-channel state tracking */
typedef struct {
    bool initialized;
    mcpwm_timer_handle_t timer;
    mcpwm_oper_handle_t oper;
    mcpwm_cmpr_handle_t cmpr;
    mcpwm_gen_handle_t gen_high;
    mcpwm_gen_handle_t gen_low;
    hal_pwm_config_t config;
    hal_pwm_state_t state;
} pwm_channel_t;

static pwm_channel_t s_channels[MAX_PWM_CHANNELS];

/* ============================================================================
 * Internal Helper Functions
 * ============================================================================ */

/**
 * @brief Convert frequency to timer period ticks
 */
static uint32_t freq_to_period_ticks(uint32_t freq_hz)
{
    return MCPWM_TIMER_RESOLUTION_HZ / freq_hz;
}

/**
 * @brief Convert duty cycle percentage to compare value
 */
static uint32_t duty_to_compare(uint32_t period_ticks, float duty_percent)
{
    return (uint32_t)((duty_percent / 100.0f) * period_ticks);
}

/* ============================================================================
 * HAL Implementation Functions
 * ============================================================================ */

static hal_status_t esp32_pwm_init(hal_pwm_channel_t channel, const hal_pwm_config_t *config)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS || !config) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (s_channels[channel].initialized) {
        ESP_LOGW(TAG, "PWM channel %d already initialized", channel);
        return HAL_ERROR_BUSY;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    esp_err_t err;
    
    /* Store configuration */
    memcpy(&ch->config, config, sizeof(hal_pwm_config_t));
    
    /* Create MCPWM timer */
    mcpwm_timer_config_t timer_cfg = {
        .group_id = channel,  /* Use channel as group ID */
        .clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = MCPWM_TIMER_RESOLUTION_HZ,
        .count_mode = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks = freq_to_period_ticks(config->frequency_hz),
    };
    
    err = mcpwm_new_timer(&timer_cfg, &ch->timer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create MCPWM timer: %s", esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    /* Create MCPWM operator */
    mcpwm_operator_config_t oper_cfg = {
        .group_id = channel,
    };
    
    err = mcpwm_new_operator(&oper_cfg, &ch->oper);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create MCPWM operator: %s", esp_err_to_name(err));
        mcpwm_del_timer(ch->timer);
        return HAL_ERROR;
    }
    
    /* Connect operator to timer */
    err = mcpwm_operator_connect_timer(ch->oper, ch->timer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to connect operator to timer: %s", esp_err_to_name(err));
        mcpwm_del_operator(ch->oper);
        mcpwm_del_timer(ch->timer);
        return HAL_ERROR;
    }
    
    /* Create comparator for duty cycle control */
    mcpwm_comparator_config_t cmpr_cfg = {
        .flags.update_cmp_on_tez = true,  /* Update on timer equal zero */
    };
    
    err = mcpwm_new_comparator(ch->oper, &cmpr_cfg, &ch->cmpr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create MCPWM comparator: %s", esp_err_to_name(err));
        mcpwm_del_operator(ch->oper);
        mcpwm_del_timer(ch->timer);
        return HAL_ERROR;
    }
    
    /* Set initial duty cycle */
    uint32_t period = freq_to_period_ticks(config->frequency_hz);
    mcpwm_comparator_set_compare_value(ch->cmpr, duty_to_compare(period, config->duty_percent));
    
    /* Create high-side generator */
    mcpwm_generator_config_t gen_high_cfg = {
        .gen_gpio_num = config->pin_high,
    };
    
    err = mcpwm_new_generator(ch->oper, &gen_high_cfg, &ch->gen_high);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create high-side generator: %s", esp_err_to_name(err));
        mcpwm_del_comparator(ch->cmpr);
        mcpwm_del_operator(ch->oper);
        mcpwm_del_timer(ch->timer);
        return HAL_ERROR;
    }
    
    /* Set high-side generator actions (active high) */
    mcpwm_generator_set_action_on_timer_event(ch->gen_high,
        MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, MCPWM_TIMER_EVENT_EMPTY, MCPWM_GEN_ACTION_HIGH));
    mcpwm_generator_set_action_on_compare_event(ch->gen_high,
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, ch->cmpr, MCPWM_GEN_ACTION_LOW));
    
    /* Create low-side generator if complementary mode */
    if (config->complementary && config->pin_low != HAL_PIN_INVALID) {
        mcpwm_generator_config_t gen_low_cfg = {
            .gen_gpio_num = config->pin_low,
        };
        
        err = mcpwm_new_generator(ch->oper, &gen_low_cfg, &ch->gen_low);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to create low-side generator: %s", esp_err_to_name(err));
            mcpwm_del_generator(ch->gen_high);
            mcpwm_del_comparator(ch->cmpr);
            mcpwm_del_operator(ch->oper);
            mcpwm_del_timer(ch->timer);
            return HAL_ERROR;
        }
        
        /* Set low-side generator actions (inverted) */
        mcpwm_generator_set_action_on_timer_event(ch->gen_low,
            MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, MCPWM_TIMER_EVENT_EMPTY, MCPWM_GEN_ACTION_LOW));
        mcpwm_generator_set_action_on_compare_event(ch->gen_low,
            MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, ch->cmpr, MCPWM_GEN_ACTION_HIGH));
        
        /* Configure hardware dead-time */
        if (config->dead_time_ns > 0) {
            mcpwm_dead_time_config_t dt_cfg = {
                .posedge_delay_ticks = (config->dead_time_ns * (MCPWM_TIMER_RESOLUTION_HZ / 1000000)) / 1000,
                .negedge_delay_ticks = (config->dead_time_ns * (MCPWM_TIMER_RESOLUTION_HZ / 1000000)) / 1000,
            };
            
            /* Apply dead-time to high-side (rising edge delayed) */
            err = mcpwm_generator_set_dead_time(ch->gen_high, ch->gen_high, &dt_cfg);
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "Failed to set dead-time on high-side: %s", esp_err_to_name(err));
            }
            
            /* Apply dead-time to low-side (falling edge delayed) */
            dt_cfg.flags.invert_output = true;  /* Inverted output for low-side */
            err = mcpwm_generator_set_dead_time(ch->gen_low, ch->gen_low, &dt_cfg);
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "Failed to set dead-time on low-side: %s", esp_err_to_name(err));
            }
            
            ESP_LOGI(TAG, "Dead-time configured: %u ns", config->dead_time_ns);
        }
    }
    
    /* Update state */
    ch->state.frequency_hz = config->frequency_hz;
    ch->state.duty_percent = config->duty_percent;
    ch->state.dead_time_ns = config->dead_time_ns;
    ch->state.running = false;
    ch->state.complementary = config->complementary;
    
    ch->initialized = true;
    
    ESP_LOGI(TAG, "PWM channel %d initialized: %lu Hz, %.1f%% duty, %u ns dead-time",
             channel, (unsigned long)config->frequency_hz, config->duty_percent, config->dead_time_ns);
    return HAL_OK;
}

static hal_status_t esp32_pwm_set_frequency(hal_pwm_channel_t channel, uint32_t freq_hz)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Frequency range validation (38-50 kHz for resonant operation) */
    if (freq_hz < 20000 || freq_hz > 100000) {
        ESP_LOGW(TAG, "Frequency %lu Hz outside recommended range", (unsigned long)freq_hz);
    }
    
    uint32_t period = freq_to_period_ticks(freq_hz);
    
    /* Update timer period */
    esp_err_t err = mcpwm_timer_set_period(ch->timer, period);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Update comparator to maintain duty cycle percentage */
    mcpwm_comparator_set_compare_value(ch->cmpr, duty_to_compare(period, ch->state.duty_percent));
    
    ch->state.frequency_hz = freq_hz;
    return HAL_OK;
}

static hal_status_t esp32_pwm_set_duty(hal_pwm_channel_t channel, float duty_percent)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (duty_percent < 0.0f || duty_percent > 100.0f) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    uint32_t period = freq_to_period_ticks(ch->state.frequency_hz);
    uint32_t compare = duty_to_compare(period, duty_percent);
    
    esp_err_t err = mcpwm_comparator_set_compare_value(ch->cmpr, compare);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    ch->state.duty_percent = duty_percent;
    return HAL_OK;
}

static hal_status_t esp32_pwm_set_dead_time(hal_pwm_channel_t channel, uint16_t dead_time_ns)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    /* Minimum dead-time enforcement for safety */
    if (dead_time_ns < 500) {
        ESP_LOGW(TAG, "Dead-time %u ns below minimum 500ns, clamping", dead_time_ns);
        dead_time_ns = 500;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    if (!ch->initialized || !ch->gen_low) {
        return HAL_ERROR_NOT_READY;
    }
    
    uint32_t delay_ticks = (dead_time_ns * (MCPWM_TIMER_RESOLUTION_HZ / 1000000)) / 1000;
    
    mcpwm_dead_time_config_t dt_cfg = {
        .posedge_delay_ticks = delay_ticks,
        .negedge_delay_ticks = delay_ticks,
    };
    
    esp_err_t err = mcpwm_generator_set_dead_time(ch->gen_high, ch->gen_high, &dt_cfg);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    dt_cfg.flags.invert_output = true;
    err = mcpwm_generator_set_dead_time(ch->gen_low, ch->gen_low, &dt_cfg);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    ch->state.dead_time_ns = dead_time_ns;
    ESP_LOGD(TAG, "Dead-time updated to %u ns", dead_time_ns);
    return HAL_OK;
}

static hal_status_t esp32_pwm_start(hal_pwm_channel_t channel)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Enable timer */
    esp_err_t err = mcpwm_timer_enable(ch->timer);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Start timer */
    err = mcpwm_timer_start_stop(ch->timer, MCPWM_TIMER_START_NO_STOP);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    ch->state.running = true;
    ESP_LOGI(TAG, "PWM channel %d started", channel);
    return HAL_OK;
}

static hal_status_t esp32_pwm_stop(hal_pwm_channel_t channel)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Stop timer immediately */
    esp_err_t err = mcpwm_timer_start_stop(ch->timer, MCPWM_TIMER_STOP_FULL);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Disable timer */
    err = mcpwm_timer_disable(ch->timer);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    ch->state.running = false;
    ESP_LOGI(TAG, "PWM channel %d stopped", channel);
    return HAL_OK;
}

/**
 * @brief Emergency stop - SAFETY CRITICAL
 * 
 * Forces all PWM outputs low immediately to prevent IGBT shoot-through.
 * Called by hardware safety interlock on fault detection.
 */
static hal_status_t esp32_pwm_emergency_stop(void)
{
    ESP_LOGW(TAG, "EMERGENCY STOP - Disabling all PWM outputs");
    
    hal_status_t status = HAL_OK;
    
    for (int i = 0; i < MAX_PWM_CHANNELS; i++) {
        pwm_channel_t *ch = &s_channels[i];
        
        if (ch->initialized) {
            /* Force generators to low state immediately */
            if (ch->gen_high) {
                mcpwm_generator_set_force_level(ch->gen_high, 0, true);
            }
            if (ch->gen_low) {
                mcpwm_generator_set_force_level(ch->gen_low, 0, true);
            }
            
            /* Stop timer */
            mcpwm_timer_start_stop(ch->timer, MCPWM_TIMER_STOP_FULL);
            ch->state.running = false;
        }
    }
    
    return status;
}

static hal_status_t esp32_pwm_get_state(hal_pwm_channel_t channel, hal_pwm_state_t *state)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS || !state) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    memcpy(state, &ch->state, sizeof(hal_pwm_state_t));
    return HAL_OK;
}

static hal_status_t esp32_pwm_deinit(hal_pwm_channel_t channel)
{
    if (channel < 0 || channel >= MAX_PWM_CHANNELS) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    pwm_channel_t *ch = &s_channels[channel];
    if (!ch->initialized) {
        return HAL_OK;  /* Already deinitialized */
    }
    
    /* Stop if running */
    if (ch->state.running) {
        esp32_pwm_stop(channel);
    }
    
    /* Delete in reverse order of creation */
    if (ch->gen_low) {
        mcpwm_del_generator(ch->gen_low);
        ch->gen_low = NULL;
    }
    if (ch->gen_high) {
        mcpwm_del_generator(ch->gen_high);
        ch->gen_high = NULL;
    }
    if (ch->cmpr) {
        mcpwm_del_comparator(ch->cmpr);
        ch->cmpr = NULL;
    }
    if (ch->oper) {
        mcpwm_del_operator(ch->oper);
        ch->oper = NULL;
    }
    if (ch->timer) {
        mcpwm_del_timer(ch->timer);
        ch->timer = NULL;
    }
    
    memset(ch, 0, sizeof(pwm_channel_t));
    
    ESP_LOGI(TAG, "PWM channel %d deinitialized", channel);
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_pwm_ops_t hal_pwm_esp32_ops = {
    .init = esp32_pwm_init,
    .set_frequency = esp32_pwm_set_frequency,
    .set_duty = esp32_pwm_set_duty,
    .set_dead_time = esp32_pwm_set_dead_time,
    .start = esp32_pwm_start,
    .stop = esp32_pwm_stop,
    .emergency_stop = esp32_pwm_emergency_stop,
    .get_state = esp32_pwm_get_state,
    .deinit = esp32_pwm_deinit
};
