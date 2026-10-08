/** ESP32-S3 PWM proposal: independently forced, complementary edge paths.
 * ESP-IDF v5.3 MCPWM Dead Time and mcpwm_gen.c:318-395.
 * Both raw generators have identical actions; A owns RED, B owns FED and
 * inversion. This is equivalent to the documented complementary waveform,
 * but permits A=0/B=1 forcing to put BOTH final outputs low.
 * Programmed ticks are a successful-API receipt, NOT register/pin readback.
 */
#include "../include/hal_pwm.h"
#include "driver/mcpwm_prelude.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include <math.h>
#include <string.h>

#define MAX_PWM_CHANNELS 2
static const char *TAG = "hal_pwm";
typedef struct {
    bool initialized;
    bool has_config;
    bool timer_enabled;
    bool timer_started;
    mcpwm_timer_handle_t timer;
    mcpwm_oper_handle_t oper;
    mcpwm_cmpr_handle_t cmpr;
    mcpwm_gen_handle_t gen_high, gen_low;
    hal_pwm_config_t config;
    hal_pwm_state_t state;
} pwm_channel_t;
static pwm_channel_t channels[MAX_PWM_CHANNELS];

static bool valid_channel(hal_pwm_channel_t channel) {
    return channel >= 0 && channel < MAX_PWM_CHANNELS;
}
static uint32_t ticks(uint16_t ns) { return (uint32_t)ns * 2 / 25; }
static bool valid_timing(uint32_t hz, float duty, bool complementary, uint16_t ns) {
    if (!hz || hz > HAL_PWM_TIMER_RESOLUTION_HZ || !isfinite(duty) || duty < 0 || duty > 100) return false;
    uint32_t period = HAL_PWM_TIMER_RESOLUTION_HZ / hz;
    if (period > 65535 || period < 2) return false;
    if (!complementary) return ns == 0;
    if (ns < HAL_PWM_MIN_DEAD_TIME_NS || ns > HAL_PWM_MAX_DEAD_TIME_NS) return false;
    uint32_t compare = (uint32_t)(period * (duty / 100.0f));
    return ticks(ns) < compare && ticks(ns) < period - compare;
}
static esp_err_t low_pin(hal_pin_t pin) {
    esp_err_t result = ESP_OK;
    if (pin == HAL_PIN_INVALID) return result;
    /* Disconnect peripheral routing; an external pull-down is required during
     * the input interval. An API failure remains an error, not a physical-off guarantee. */
    if (gpio_set_level(pin, 0) != ESP_OK) result = ESP_FAIL;
    if (gpio_reset_pin(pin) != ESP_OK) result = ESP_FAIL;
    if (gpio_set_level(pin, 0) != ESP_OK) result = ESP_FAIL;
    if (gpio_pullup_dis(pin) != ESP_OK) result = ESP_FAIL;
    if (gpio_pulldown_en(pin) != ESP_OK) result = ESP_FAIL;
    if (gpio_set_direction(pin, GPIO_MODE_OUTPUT) != ESP_OK) result = ESP_FAIL;
    if (gpio_hold_dis(pin) != ESP_OK) result = ESP_FAIL;
    return result;
}
static hal_status_t ground_outputs(pwm_channel_t *ch) {
    esp_err_t a = low_pin(ch->config.pin_high);
    esp_err_t b = low_pin(ch->config.complementary ? ch->config.pin_low : HAL_PIN_INVALID);
    if (a != ESP_OK || b != ESP_OK) {
        ESP_LOGE(TAG, "GPIO shutdown failed; hardware interlock required");
        return HAL_ERROR;
    }
    return HAL_OK;
}
static hal_status_t release_resources(pwm_channel_t *ch) {
    hal_status_t result = HAL_OK;
#define DELETE(handle, fn) do { if (ch->handle) { if (fn(ch->handle) == ESP_OK) ch->handle = NULL; else result = HAL_ERROR; } } while (0)
    if (ch->timer_started) {
        if (mcpwm_timer_start_stop(ch->timer, MCPWM_TIMER_STOP_FULL) == ESP_OK) ch->timer_started = false;
        else result = HAL_ERROR;
    }
    if (ch->timer_enabled && !ch->timer_started) {
        if (mcpwm_timer_disable(ch->timer) == ESP_OK) ch->timer_enabled = false;
        else result = HAL_ERROR;
    }
    DELETE(gen_low, mcpwm_del_generator);
    DELETE(gen_high, mcpwm_del_generator);
    if (!ch->gen_low && !ch->gen_high) DELETE(cmpr, mcpwm_del_comparator);
    if (!ch->gen_low && !ch->gen_high && !ch->cmpr) DELETE(oper, mcpwm_del_operator);
    if (!ch->oper && !ch->timer_enabled) DELETE(timer, mcpwm_del_timer);
#undef DELETE
    /* Generator deletion resets its GPIO to disabled output with pull-up.
     * Restore both pins LAST, even after a failed/partial resource release. */
    if (ground_outputs(ch) != HAL_OK) {
        result = HAL_ERROR;
        (void)ground_outputs(ch); /* Restore after a transient final GPIO failure. */
    }
    return result;
}
static hal_status_t invalidate(pwm_channel_t *ch) {
    ch->initialized = false;
    ch->state.configured = false;
    ch->state.running = false;
    /* Disconnect first; release_resources reasserts GPIO state after deletion. */
    ground_outputs(ch);
    if (release_resources(ch) != HAL_OK) ESP_LOGE(TAG, "PWM cleanup failed; deinit required");
    else ch->has_config = false; /* Fully released: a fresh init may retry. */
    return HAL_ERROR;
}

static esp_err_t program_delay(pwm_channel_t *ch, uint16_t ns) {
    mcpwm_dead_time_config_t rise = {.posedge_delay_ticks = ticks(ns)};
    mcpwm_dead_time_config_t fall = {.negedge_delay_ticks = ticks(ns), .flags.invert_output = true};
    esp_err_t err = mcpwm_generator_set_dead_time(ch->gen_high, ch->gen_high, &rise);
    if (err != ESP_OK) return err;
    err = mcpwm_generator_set_dead_time(ch->gen_low, ch->gen_low, &fall);
    if (err != ESP_OK) return err;
    ch->state.dead_time_ticks = ticks(ns);
    ch->state.dead_time_ns = ticks(ns) * 25 / 2; /* legacy field truncates a half ns */
    ch->state.timer_resolution_hz = HAL_PWM_TIMER_RESOLUTION_HZ;
    ch->config.dead_time_ns = ns;
    return ESP_OK;
}
static esp_err_t force_off(pwm_channel_t *ch) {
    esp_err_t result = ESP_OK;
    if (ch->gen_high && mcpwm_generator_set_force_level(ch->gen_high, 0, true) != ESP_OK) result = ESP_FAIL;
    if (ch->gen_low && mcpwm_generator_set_force_level(ch->gen_low, 1, true) != ESP_OK) result = ESP_FAIL;
    return result;
}
static hal_status_t esp32_pwm_init(hal_pwm_channel_t channel, const hal_pwm_config_t *config) {
    /* Native19 gate drive belongs to the synchronized four-output service. */
    if (channel == HAL_PWM_CHANNEL_GATE) return HAL_ERROR_NOT_READY;
    if (!valid_channel(channel) || !config) return HAL_ERROR_INVALID_ARG;
    pwm_channel_t *ch = &channels[channel];
    if (ch->has_config || ch->initialized || ch->timer || ch->oper) return HAL_ERROR_BUSY;
    if (!GPIO_IS_VALID_OUTPUT_GPIO(config->pin_high) ||
        (config->complementary && (!GPIO_IS_VALID_OUTPUT_GPIO(config->pin_low) || config->pin_low == config->pin_high)) ||
        !valid_timing(config->frequency_hz, config->duty_percent, config->complementary, config->dead_time_ns)) return HAL_ERROR_INVALID_ARG;
    memset(ch, 0, sizeof(*ch));
    ch->config = *config;
    ch->has_config = true;
#define TRY(call) do { if ((call) != ESP_OK) goto fail; } while (0)
    /* Hold both pads low while routing, forcing and inversion are configured. */
    TRY(low_pin(config->pin_high));
    TRY(gpio_hold_en(config->pin_high));
    if (config->complementary) {
        TRY(low_pin(config->pin_low));
        TRY(gpio_hold_en(config->pin_low));
    }
    uint32_t period = HAL_PWM_TIMER_RESOLUTION_HZ / config->frequency_hz;
    mcpwm_timer_config_t timer = {.group_id=channel, .clk_src=MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz=HAL_PWM_TIMER_RESOLUTION_HZ, .count_mode=MCPWM_TIMER_COUNT_MODE_UP, .period_ticks=period};
    mcpwm_operator_config_t oper = {.group_id=channel};
    mcpwm_comparator_config_t cmpr = {.flags.update_cmp_on_tez=true};
    TRY(mcpwm_new_timer(&timer, &ch->timer));
    TRY(mcpwm_new_operator(&oper, &ch->oper));
    TRY(mcpwm_operator_connect_timer(ch->oper, ch->timer));
    TRY(mcpwm_new_comparator(ch->oper, &cmpr, &ch->cmpr));
    TRY(mcpwm_comparator_set_compare_value(ch->cmpr, (uint32_t)(period * config->duty_percent / 100.0f)));
    mcpwm_generator_config_t high = {.gen_gpio_num=config->pin_high};
    TRY(mcpwm_new_generator(ch->oper, &high, &ch->gen_high));
    TRY(mcpwm_generator_set_force_level(ch->gen_high, 0, true));
    TRY(mcpwm_generator_set_action_on_timer_event(ch->gen_high,
        MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,MCPWM_TIMER_EVENT_EMPTY,MCPWM_GEN_ACTION_HIGH)));
    TRY(mcpwm_generator_set_action_on_compare_event(ch->gen_high,
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,ch->cmpr,MCPWM_GEN_ACTION_LOW)));
    if (config->complementary) {
        mcpwm_generator_config_t low = {.gen_gpio_num=config->pin_low};
        TRY(mcpwm_new_generator(ch->oper, &low, &ch->gen_low));
        TRY(mcpwm_generator_set_force_level(ch->gen_low, 1, true));
        /* Identical raw actions; invert only AFTER FED. */
        TRY(mcpwm_generator_set_action_on_timer_event(ch->gen_low,
            MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,MCPWM_TIMER_EVENT_EMPTY,MCPWM_GEN_ACTION_HIGH)));
        TRY(mcpwm_generator_set_action_on_compare_event(ch->gen_low,
            MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,ch->cmpr,MCPWM_GEN_ACTION_LOW)));
        TRY(program_delay(ch, config->dead_time_ns));
    }
    TRY(gpio_hold_dis(config->pin_high));
    if (config->complementary) TRY(gpio_hold_dis(config->pin_low));
    ch->state.frequency_hz = HAL_PWM_TIMER_RESOLUTION_HZ / period;
    ch->state.duty_percent = config->duty_percent;
    ch->state.complementary = config->complementary;
    ch->state.configured = true;
    ch->initialized = true;
    return HAL_OK;
fail:
    return invalidate(ch);
#undef TRY
}
static hal_status_t esp32_pwm_set_frequency(hal_pwm_channel_t channel, uint32_t hz) {
    if (!valid_channel(channel)) return HAL_ERROR_INVALID_ARG;
    pwm_channel_t *ch=&channels[channel];
    if (!ch->initialized) return HAL_ERROR_NOT_READY;
    if (!valid_timing(hz,ch->state.duty_percent,ch->config.complementary,ch->config.dead_time_ns)) return HAL_ERROR_INVALID_ARG;
    /* Pair updates are not atomic in the SDK. Require a stopped output. */
    if (ch->state.running) return HAL_ERROR_BUSY;
    uint32_t period=HAL_PWM_TIMER_RESOLUTION_HZ/hz;
    if (mcpwm_timer_set_period(ch->timer,period)!=ESP_OK ||
        mcpwm_comparator_set_compare_value(ch->cmpr,(uint32_t)(period*ch->state.duty_percent/100.0f))!=ESP_OK) return invalidate(ch);
    ch->state.frequency_hz=HAL_PWM_TIMER_RESOLUTION_HZ/period;
    return HAL_OK;
}
static hal_status_t esp32_pwm_set_duty(hal_pwm_channel_t channel, float duty) {
    if (!valid_channel(channel)) return HAL_ERROR_INVALID_ARG;
    pwm_channel_t *ch=&channels[channel];
    if (!ch->initialized) return HAL_ERROR_NOT_READY;
    if (!valid_timing(ch->state.frequency_hz,duty,ch->config.complementary,ch->config.dead_time_ns)) return HAL_ERROR_INVALID_ARG;
    uint32_t period=HAL_PWM_TIMER_RESOLUTION_HZ/ch->state.frequency_hz;
    if (mcpwm_comparator_set_compare_value(ch->cmpr,(uint32_t)(period*duty/100.0f))!=ESP_OK) return invalidate(ch);
    ch->state.duty_percent=duty;
    return HAL_OK;
}
static hal_status_t esp32_pwm_set_dead_time(hal_pwm_channel_t channel, uint16_t ns) {
    if (!valid_channel(channel)) return HAL_ERROR_INVALID_ARG;
    pwm_channel_t *ch=&channels[channel];
    if (!ch->initialized || !ch->gen_low) return HAL_ERROR_NOT_READY;
    if (ch->state.running) return HAL_ERROR_BUSY;
    if (!valid_timing(ch->state.frequency_hz,ch->state.duty_percent,true,ns)) return HAL_ERROR_INVALID_ARG;
    if (program_delay(ch,ns)!=ESP_OK) return invalidate(ch);
    return HAL_OK;
}
static hal_status_t esp32_pwm_start(hal_pwm_channel_t channel) {
    if (!valid_channel(channel)) return HAL_ERROR_INVALID_ARG;
    pwm_channel_t *ch=&channels[channel];
    if (!ch->initialized || !ch->state.configured) return HAL_ERROR_NOT_READY;
    if (ch->state.running) return HAL_OK;
    if (!ch->timer_enabled) {
        if (mcpwm_timer_enable(ch->timer)!=ESP_OK) return invalidate(ch);
        ch->timer_enabled=true;
    }
    if (!ch->timer_started) {
        if (mcpwm_timer_start_stop(ch->timer,MCPWM_TIMER_START_NO_STOP)!=ESP_OK) return invalidate(ch);
        ch->timer_started=true;
    }
    if (ch->gen_low && mcpwm_generator_set_force_level(ch->gen_low,-1,true)!=ESP_OK) return invalidate(ch);
    if (mcpwm_generator_set_force_level(ch->gen_high,-1,true)!=ESP_OK) return invalidate(ch);
    ch->state.running=true;
    return HAL_OK;
}
static hal_status_t esp32_pwm_stop(hal_pwm_channel_t channel) {
    if (!valid_channel(channel)) return HAL_ERROR_INVALID_ARG;
    pwm_channel_t *ch=&channels[channel];
    if (!ch->initialized) return HAL_ERROR_NOT_READY;
    if (force_off(ch)!=ESP_OK) return invalidate(ch);
    /* Keep the timebase clocked; STOP_FULL is a future event, not immediate. */
    ch->state.running=false;
    return HAL_OK;
}
static hal_status_t esp32_pwm_emergency_stop(void) {
    hal_status_t result=HAL_OK;
    for (int i=0;i<MAX_PWM_CHANNELS;i++) {
        if (channels[i].initialized && esp32_pwm_stop(i)!=HAL_OK) result=HAL_ERROR;
    }
    return result;
}
static hal_status_t esp32_pwm_get_state(hal_pwm_channel_t channel, hal_pwm_state_t *state) {
    if (!valid_channel(channel) || !state) return HAL_ERROR_INVALID_ARG;
    memset(state,0,sizeof(*state));
    if (!channels[channel].initialized) return HAL_ERROR_NOT_READY;
    *state=channels[channel].state;
    return HAL_OK;
}
static hal_status_t esp32_pwm_deinit(hal_pwm_channel_t channel) {
    if (!valid_channel(channel)) return HAL_ERROR_INVALID_ARG;
    pwm_channel_t *ch=&channels[channel];
    if (!ch->has_config && !ch->timer && !ch->oper) return HAL_OK;
    hal_status_t result=ground_outputs(ch);
    ch->initialized=false; ch->state.configured=false; ch->state.running=false;
    if (release_resources(ch)!=HAL_OK) result=HAL_ERROR;
    if (result==HAL_OK) memset(ch,0,sizeof(*ch));
    return result;
}
const hal_pwm_ops_t hal_pwm_esp32_ops = {
    .init=esp32_pwm_init,.set_frequency=esp32_pwm_set_frequency,.set_duty=esp32_pwm_set_duty,
    .set_dead_time=esp32_pwm_set_dead_time,.start=esp32_pwm_start,.stop=esp32_pwm_stop,
    .emergency_stop=esp32_pwm_emergency_stop,.get_state=esp32_pwm_get_state,.deinit=esp32_pwm_deinit
};
