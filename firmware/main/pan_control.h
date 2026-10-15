/**
 * @file pan_control.h
 * @brief Runtime adapter for the sensor-r3 C1 pan-temperature loop.
 *
 * Built only with TEMPER_PAN_CONTROL_C1 (main/CMakeLists.txt; the legacy host
 * suites build without it and keep the legacy bang-bang/PID control). It owns
 * the loop (components/control/pan_temp_loop.c) and the runaway supervisor
 * (components/control/pan_supervisor.c) and connects them to the runtime:
 *
 *   input   rtd_service_latest_sample() (MAX31865 conversions, 50 Hz),
 *           read_rim_ntc_temperature() (rim NTC, peripherals), the commanded
 *           power of the last period as PG_POWER_ESTIMATED, the target
 *           temperature and intensity level from the state machine;
 *   period  the state machine updates every 10 ms; the loop runs every
 *           PAN_CONTROL_PERIOD_MS (100 ms) and its command is held between;
 *   output  power_set_level() in percent of PAN_CONTROL_P_MAX_W, limited by
 *           the intensity level (the loop's own power limit, so its
 *           anti-windup and plant-gain gate see the limit);
 *   events  guard verdicts -> state_machine_report_rtd_device_fault();
 *           D1 contact lost -> state_machine_report_pan_contact_lost();
 *           supervisor stage 2a/2b latches -> PAN_CONTROL_RUNAWAY (the
 *           caller latches FAULT_THERMAL_RUNAWAY).
 *
 * The supervisor's R1 (sustained-rise) half is fed every 10 ms tick from
 * check_runaway_boundary() through pan_control_rate_sample().
 *
 * See output/temper-sensor-r3/firmware/DECISIONS.md D-MODE, D-RUN.
 */

#ifndef PAN_CONTROL_H
#define PAN_CONTROL_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PAN_CONTROL_PERIOD_MS 100u
#define PAN_CONTROL_P_MAX_W 1800.0f

typedef enum {
    PAN_CONTROL_HOLD = 0,       /**< between control periods: command held   */
    PAN_CONTROL_RAN = 1,        /**< a control period ran                    */
    PAN_CONTROL_SENSOR_FAULT = 2, /**< guard fault reported to the state machine */
    PAN_CONTROL_RUNAWAY = 3,    /**< supervisor latch: caller latches FAULT_THERMAL_RUNAWAY */
} pan_control_status_t;

/** PREHEAT entry: restart the loop from the latest reading, zero the command. */
void pan_control_begin(void);

/**
 * PREHEAT/HEATING update (every state-machine update). Runs one control
 * period when PAN_CONTROL_PERIOD_MS has elapsed since the last one.
 */
pan_control_status_t pan_control_step(float setpoint_c, uint8_t intensity_level);

/** Leaving PREHEAT/HEATING: command 0. */
void pan_control_stop(void);

/** True between pan_control_begin() and pan_control_stop(). */
bool pan_control_is_running(void);

/** Pan-temperature estimate of the last control period (degC). */
float pan_control_t_hat(void);

/** True once the MAX31865 has delivered a conversion. */
bool pan_control_have_reading(void);
/** Latest Pt100 reading (degC), NAN before the first conversion. */
float pan_control_reading_c(void);
/** Latest Pt100 resistance (ohm), NAN before the first conversion. */
float pan_control_resistance_ohm(void);

/** R1: feed one 10 ms reading; true when the sustained-rise latch trips. */
bool pan_control_rate_sample(float reading_c, uint32_t now_ms);
/** R1: forget the rise history (state_machine_reset_temp_baseline). */
void pan_control_rate_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* PAN_CONTROL_H */
