/**
 * @file power_gate.h
 * @brief RUN_EN, the firmware's gate enable, raised only with the PWM idle
 *
 * zapote/controller: PERMIT = interlock latch OK AND RUN_EN (DECISIONS C23).
 * RUN_EN is GPIO14 with a 4.7 k pull-down, so it is low at reset and while
 * the pin is an input. RUN_EN low also presets / clears the capacitive-mode
 * detector's flip-flops (C39); its rising edge re-arms them. The board's
 * firmware rule (C39, open item 18): raise RUN_EN only while the PWM is idle,
 * i.e. every gate command is held low, so the detector re-arms with no edge
 * in flight.
 *
 * This module is the only writer of PIN_RUN_EN (firmware/tools/
 * check_board_pin_map.py enforces that). power_gate_enable() refuses, and
 * leaves RUN_EN low, unless every gate PWM channel is idle:
 *   - no PWM driver (hal_pwm NULL) or the channel not initialised: nothing
 *     drives the gate pins (board_power_init() holds them low as GPIOs);
 *   - otherwise get_state() must report running == false and
 *     outputs_off == true (after init or emergency_stop(), not after a bare
 *     stop(), which leaves the outputs at their last level).
 * Lowering RUN_EN is never refused.
 *
 * The gate PWM channels checked are POWER_GATE_PWM_CHANNELS. A full-bridge
 * driver that adds a channel, or drives the gate pins outside hal_pwm, must
 * extend that list or this check is blind to it (power-stage requirement,
 * output/temper-sensor-r3/firmware/DECISIONS.md D-BRINGUP).
 */

#ifndef POWER_GATE_H
#define POWER_GATE_H

#include <stdbool.h>
#include <stdint.h>

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Configure PIN_RUN_EN as an output and drive it low. */
hal_status_t power_gate_init(void);

/** True when every gate PWM channel is idle (see above). */
bool power_gate_pwm_idle(void);

/**
 * Raise RUN_EN.
 * @return HAL_OK (RUN_EN high), HAL_ERROR_BUSY (refused: PWM not idle; RUN_EN
 *         stays/goes low), HAL_ERROR_NOT_READY (not initialised or no GPIO
 *         driver), or the GPIO write's error (RUN_EN driven low).
 */
hal_status_t power_gate_enable(void);

/** Drive RUN_EN low. Never refused. */
void power_gate_disable(void);

/** RUN_EN as last driven by this module. */
bool power_gate_is_enabled(void);

/** Number of refused power_gate_enable() calls since init. */
uint32_t power_gate_refusals(void);

#ifdef __cplusplus
}
#endif

#endif /* POWER_GATE_H */
