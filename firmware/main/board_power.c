/**
 * @file board_power.c
 * @brief zapote/controller power-stage bring-up on the ESP-IDF target
 *
 * What is wired here, from the controller netlist (temper_pins.h):
 *
 * 1. The four native-21 gate commands (PWM_HA/LA/HB/LB, GPIO4/5/15/16) are
 *    driven low as GPIO outputs: commands idle, no edge for the C39
 *    capacitive-mode detector's flip-flops.
 * 2. RUN_EN (GPIO14) is an output, low, owned by power_gate.c (raised only
 *    with the gate PWM idle, C39).
 * 3. One MCPWM capture timer (group 0) with three channels:
 *      - PWM_HA rising, for the PLL's PWM edge (pwm_edge_cb). io_loop_back
 *        keeps the pad an output, still driven low, with its input path on;
 *      - CT_ZC rising (GPIO38, tank current going positive), for the PLL's
 *        zero-cross edge (zcd_edge_cb);
 *      - CT_ZC rising again, counted by pan detection's listen window.
 *    The PLL computes the lag from the two captures at the capture timer's
 *    own resolution.
 *
 * What is not (TODO(hardware)): the native-21 gate generator. Its waveform
 * (full bridge, leg phase, dead time split with the 2EDR8259X, the pan
 * detection pulse) is the power stage's, on codex/power-stage-integration,
 * and is not specified in this tree. So pll_set_timer() is never called (the
 * PLL tracks nothing and reports unlocked) and no pan-detect pulse ops are
 * installed (detect_pan_presence() reports PAN_ABSENT: no pan, no power).
 * When the power stage provides the generator it must (DECISIONS.md
 * D-BRINGUP): create it after this function, with
 * mcpwm_generator_config_t.flags.io_loop_back = 1 on PWM_HA (or the PLL's PWM
 * edge capture goes blind); call pll_set_timer(timer, resolution_hz); report
 * its state through hal_pwm (or extend power_gate.c's idle check); and start
 * every burst at pll_burst_start_frequency() or its own equivalent rule.
 */

#include "board_power.h"

#include <stdbool.h>

#include "driver/mcpwm_prelude.h"
#include "esp_log.h"

#include "hal.h"
#include "temper_pins.h"
#include "power_gate.h"
#include "pll_control.h"
#include "pan_detect.h"

static const char *TAG = "board_power";

#define BOARD_POWER_MCPWM_GROUP 0

static const hal_pin_t s_gate_pins[] = {PIN_PWM_HA, PIN_PWM_LA, PIN_PWM_HB, PIN_PWM_LB};

static void gate_commands_low(void)
{
    if (hal_gpio == NULL) {
        ESP_LOGE(TAG, "no GPIO driver: gate commands left at their reset state");
        return;
    }
    for (size_t i = 0; i < sizeof(s_gate_pins) / sizeof(s_gate_pins[0]); i++) {
        (void)hal_gpio->set_level(s_gate_pins[i], HAL_GPIO_LOW);
        if (hal_gpio->init(s_gate_pins[i], HAL_GPIO_MODE_OUTPUT) != HAL_OK ||
            hal_gpio->set_level(s_gate_pins[i], HAL_GPIO_LOW) != HAL_OK) {
            ESP_LOGE(TAG, "gate command GPIO%d not driven low", (int)s_gate_pins[i]);
        }
    }
}

static esp_err_t capture_init(void)
{
    mcpwm_cap_timer_handle_t timer = NULL;
    mcpwm_cap_channel_handle_t ch_pwm = NULL;
    mcpwm_cap_channel_handle_t ch_zcd = NULL;
    mcpwm_cap_channel_handle_t ch_pan = NULL;
    uint32_t res_hz = 0;

    const mcpwm_capture_timer_config_t tcfg = {
        .group_id = BOARD_POWER_MCPWM_GROUP,
        .clk_src = MCPWM_CAPTURE_CLK_SRC_DEFAULT,
    };
    esp_err_t err = mcpwm_new_capture_timer(&tcfg, &timer);

    mcpwm_capture_channel_config_t pwm_cfg = {
        .gpio_num = PIN_PWM_HA,
        .prescale = 1,
        .flags.pos_edge = 1,
        .flags.io_loop_back = 1,   /* keep the pad an output (still low) */
    };
    if (err == ESP_OK) {
        err = mcpwm_new_capture_channel(timer, &pwm_cfg, &ch_pwm);
    }
    const mcpwm_capture_channel_config_t zcd_cfg = {
        .gpio_num = PIN_CT_ZC,
        .prescale = 1,
        .flags.pos_edge = 1,
    };
    if (err == ESP_OK) {
        err = mcpwm_new_capture_channel(timer, &zcd_cfg, &ch_zcd);
    }
    if (err == ESP_OK) {
        err = mcpwm_new_capture_channel(timer, &zcd_cfg, &ch_pan);
    }
    if (err == ESP_OK) {
        err = mcpwm_capture_timer_get_resolution(timer, &res_hz);
    }
    if (err == ESP_OK) {
        err = pll_capture_attach(ch_pwm, ch_zcd, res_hz);
    }
    if (err == ESP_OK) {
        err = pan_detect_init(ch_pan, NULL);
    }
    if (err == ESP_OK) {
        err = mcpwm_capture_timer_enable(timer);
    }
    if (err == ESP_OK) {
        err = mcpwm_capture_timer_start(timer);
    }
    if (err != ESP_OK) {
        /* Channels and timer are left allocated (a half-registered capture
         * cannot be torn down cleanly once enabled); the PLL then sees no
         * edges and stays unlocked, and pan detection has no listener or no
         * pulse ops, so it reports no pan. */
        ESP_LOGE(TAG, "CT_ZC / PWM_HA capture not available: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "capture: PWM_HA GPIO%d, CT_ZC GPIO%d, %lu Hz ticks", PIN_PWM_HA, PIN_CT_ZC,
             (unsigned long)res_hz);
    return ESP_OK;
}

void board_power_init(void)
{
    gate_commands_low();

    if (power_gate_init() != HAL_OK) {
        /* RUN_EN keeps its 4.7 k pull-down: low, PERMIT low. power_enable()
         * then refuses (not initialised). */
        ESP_LOGE(TAG, "RUN_EN output not configured: power stays disabled");
    }

    pll_init(NULL);
    (void)capture_init();

    ESP_LOGE(TAG, "TODO(hardware): no native-21 gate generator in this image: PLL has no "
                  "timer and pan detection no pulse (no pan, coil off)");
}
