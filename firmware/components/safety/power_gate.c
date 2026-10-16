/**
 * @file power_gate.c
 * @brief RUN_EN raised only with the gate PWM idle (zapote C23 / C39)
 *
 * See power_gate.h.
 */

#include "power_gate.h"

#include <stddef.h>

#include "hal_gpio.h"
#include "hal_pwm.h"
#include "temper_pins.h"

/* Gate PWM channels whose idleness RUN_EN depends on. */
static const hal_pwm_channel_t POWER_GATE_PWM_CHANNELS[] = {HAL_PWM_CHANNEL_GATE};

static bool s_inited;
static bool s_enabled;
static uint32_t s_refusals;

static void drive_low(void)
{
    if (hal_gpio != NULL) {
        (void)hal_gpio->set_level(PIN_RUN_EN, HAL_GPIO_LOW);
    }
    s_enabled = false;
}

hal_status_t power_gate_init(void)
{
    s_inited = false;
    s_enabled = false;
    s_refusals = 0u;
    if (hal_gpio == NULL) {
        return HAL_ERROR_NOT_READY;
    }
    /* Level first, so the pad comes up driving low (the 4.7 k pull-down
     * already holds it low while it is an input). */
    (void)hal_gpio->set_level(PIN_RUN_EN, HAL_GPIO_LOW);
    hal_status_t st = hal_gpio->init(PIN_RUN_EN, HAL_GPIO_MODE_OUTPUT);
    if (st != HAL_OK) {
        return st;
    }
    st = hal_gpio->set_level(PIN_RUN_EN, HAL_GPIO_LOW);
    if (st != HAL_OK) {
        return st;
    }
    s_inited = true;
    return HAL_OK;
}

bool power_gate_pwm_idle(void)
{
    if (hal_pwm == NULL) {
        return true;   /* no PWM driver: nothing drives the gate pins */
    }
    for (size_t i = 0; i < sizeof(POWER_GATE_PWM_CHANNELS) / sizeof(POWER_GATE_PWM_CHANNELS[0]);
         i++) {
        hal_pwm_state_t st;
        const hal_status_t rc = hal_pwm->get_state(POWER_GATE_PWM_CHANNELS[i], &st);
        if (rc == HAL_ERROR_NOT_READY) {
            continue;  /* channel not initialised: no generator on the pins */
        }
        if (rc != HAL_OK || st.running || !st.outputs_off) {
            return false;
        }
    }
    return true;
}

hal_status_t power_gate_enable(void)
{
    if (!s_inited || hal_gpio == NULL) {
        return HAL_ERROR_NOT_READY;
    }
    if (s_enabled) {
        return HAL_OK;   /* already high: no new rising edge */
    }
    if (!power_gate_pwm_idle()) {
        s_refusals++;
        drive_low();
        return HAL_ERROR_BUSY;
    }
    const hal_status_t st = hal_gpio->set_level(PIN_RUN_EN, HAL_GPIO_HIGH);
    if (st != HAL_OK) {
        drive_low();
        return st;
    }
    s_enabled = true;
    return HAL_OK;
}

void power_gate_disable(void)
{
    drive_low();
}

bool power_gate_is_enabled(void)
{
    return s_enabled;
}

uint32_t power_gate_refusals(void)
{
    return s_refusals;
}
