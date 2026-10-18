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
 *           the rim NTC (components/sensors/rim_ntc.c through
 *           rim_ntc_board_hal(), one driver period per control period;
 *           DECISIONS.md D-RIM), the commanded
 *           power of the last period as PG_POWER_ESTIMATED, the target
 *           temperature and intensity level from the state machine;
 *   period  the state machine updates every 10 ms; the loop runs every
 *           PAN_CONTROL_PERIOD_MS (100 ms) and its command is held between;
 *   output  power_set_level() in percent of PAN_CONTROL_P_MAX_W, limited by
 *           the intensity level (the loop's own power limit, so its
 *           anti-windup and plant-gain gate see the limit);
 *   events  guard verdicts and latched rim faults ->
 *           state_machine_report_rtd_device_fault();
 *           D1 contact lost -> state_machine_report_pan_contact_lost();
 *           supervisor stage 2a/2b latches -> PAN_CONTROL_RUNAWAY (the
 *           caller latches FAULT_THERMAL_RUNAWAY);
 *           current-sense plausibility (D-ISENSE) -> FAULT_CURRENT_SENSE and
 *           element-parallel Pt100 leakage (D-LEAK, D-RIMLIM, and the
 *           cold-soak check D-SOAK) -> FAULT_PROBE_LEAKAGE,
 *           both through state_machine_report_latched_fault() (hardware
 *           cut; only the cold-soak latch can be reset, once the Pt100
 *           agrees with the heatsink again).
 *
 * Cold soak (DECISIONS.md D-SOAK): pan_control_soak_note() keeps, from every
 * state-machine tick, when the coil was last active and the per-minute Pt100
 * and heatsink history (components/control/pan_cold_soak.c);
 * pan_control_begin() freezes it, and the first control period of the
 * session evaluates it with the rim NTC's first reading, before any power.
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

#include "hs_ntc.h"
#include "pan_cold_soak.h"
#include "pan_soak_store.h"
#include "rim_ntc.h"
#include "rtd_convert.h"

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
/** False once the MAX31865 service has stopped (no DRDY, frozen code, SPI or
 *  fault-cycle failure): only a power cycle restarts it (DECISIONS D-RESET). */
bool pan_control_sensor_ready(void);

/**
 * Sensor-failure class of the latest conversion (rtd_convert_classify_failure:
 * a code at or beyond R(850 degC) or R(-200 degC), or register 07h input
 * bits). RTD_SENSOR_OK before the first conversion. check_runaway_boundary()
 * routes a failed conversion to the recoverable probe fault instead of the
 * RUNAWAY latch (DECISIONS.md D-OPEN).
 */
rtd_sensor_fail_t pan_control_reading_failure(void);

/** Reset policy: register 07h reads clean on the latest conversion (asks the
 *  service for a clear otherwise; rtd_service_fault_status_clean). */
bool pan_control_sensor_fault_clean(void);

/**
 * Supervisor R2 latch since the last pan_control_begin(): 0 none, 1 stage 2a
 * (the power stage is not obeying), 2 stage 2b (still rising with no command).
 * Read-only diagnostics; the SIL suite uses it to attribute a
 * FAULT_THERMAL_RUNAWAY to the rule that raised it.
 */
int pan_control_supervisor_latch(void);

/**
 * Current-sense plausibility latch since the last pan_control_begin()
 * (components/control/current_sense_check.h csc_latch_t): 0 none, 1 (a) the
 * command drew no current, 2 (b) the start-up pulse showed no current, 3 (c)
 * input and bus current disagree. Read-only diagnostics for the SIL.
 */
int pan_control_current_sense_latch(void);

/**
 * Rim NTC temperature (degC) of the last control period: the filtered
 * reading when the driver classifies it VALID, otherwise NAN (saturated
 * cold, no data, or a fault). The loop's own rim input is in D-RIM.
 */
float read_rim_ntc_temperature(void);
/** Last rim driver reading; returns true when it is VALID. */
bool pan_control_rim_reading(rim_ntc_reading_t *out);
/** Pt100-vs-rim cross-check suspects (D-XCHK) since pan_control_begin(). */
uint32_t pan_control_xcheck_suspects(void);
/**
 * Element-parallel Pt100 leakage latch since pan_control_begin(): the chained
 * cross-check cycles (components/control/pan_leak_check.h, DECISIONS.md
 * D-LEAK). Read-only diagnostics for the SIL.
 */
bool pan_control_leak_latched(void);
/**
 * The setpoint-relative rim limit (components/control/pan_rim_limit.h,
 * DECISIONS.md D-RIMLIM) since pan_control_begin(). It reports the same
 * FAULT_PROBE_LEAKAGE. Read-only diagnostics for the SIL.
 */
bool pan_control_rim_limit_latched(void);

/**
 * Cold-soak history (D-SOAK): call every state-machine tick, in every state.
 * Samples at most once a second; the coil counts as active while the loop
 * runs or the last period commanded power.
 */
void pan_control_soak_note(uint32_t now_ms);
/** Power-up / state_machine_init(): the coil counts as just active (no soak). */
void pan_control_soak_restart(void);
/** The cold-soak result of the last heating session's first period
 *  (verdict PCS_NONE before one ran). Read-only diagnostics. */
/** The coil-off token store's state (D-SOAKNV diagnostics and tests). */
const pss_t *pan_control_soak_store(void);

pcs_result_t pan_control_cold_soak_result(void);
/** The cold-soak check latched FAULT_PROBE_LEAKAGE this session. */
bool pan_control_cold_soak_latched(void);
/**
 * fault_cleared() for FAULT_PROBE_LEAKAGE: true only when the cold-soak
 * check raised it (not D-LEAK or D-RIMLIM) and the Pt100 now reads within
 * the threshold of a VALID heatsink (a cold item removed or thawed). A
 * persisting leak keeps it latched.
 */
bool pan_control_cold_soak_clearable(void);

/** R1: feed one 10 ms reading; true when the sustained-rise latch trips. */
bool pan_control_rate_sample(float reading_c, uint32_t now_ms);
/** R1: forget the rise history (state_machine_reset_temp_baseline). */
void pan_control_rate_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* PAN_CONTROL_H */
