/**
 * @file thermal_io.c
 * @brief Target glue for the thermal inputs and the J10 blower (ESP-IDF only).
 *
 * Every decision is in components/control/thermal_mgmt.c (host-tested); this file only moves
 * values between the ADC frames, the expander, the LEDC / PCNT drivers and those functions.
 *
 * - NTC readings (HS, COIL, RIM): the native-21 binding's continuous ADC1 pattern keeps per-frame
 *   means (n21_hw_thermal_mv). Without CONFIG_TEMPER_POWER_HW_BINDING there is no reading: the
 *   heatsink and coil read NaN (the state machine's over-temperature interlock trips on NaN and
 *   the fan law runs full speed) and the rim reads invalid (no rim cap; the pan RTD still caps).
 *   A reading is used only after the C29 input RC has settled (ntc_input_settled(); the MCU runs
 *   from v3v3, so time since boot is a lower bound on time since the rail came up).
 * - Sensor plausibility (coordinator 2026-10-12): the state handlers latch rim / coil sensor faults
 *   (thermal_plaus_t) and hand them here; a coil-sensor fault clamps the native-21 tank ceiling to
 *   COIL_SENSOR_FAULT_TANK_MAX_A (22 A) and runs the blower at full speed.
 * - Blower (DECISIONS C28): thermal_blower_tick(), every MONITOR tick (100 ms): fan law -> FAN_OFF
 *   and the GPIO46 duty (duty 0 = full speed), FG tach -> rpm -> stall detector, and the tank
 *   power cap min(coil derate, stall derate) that thermal_power_cap_pct() hands the state
 *   handlers. is_fan_running() is false once the stall detector has stopped the tank (the blower
 *   failed and the sink or coil kept rising), which the state machine latches as FAULT_FAN_FAILURE.
 * - Blower supply inlet allowance (stage 16, power/blower_aux.h): between the fan law and the
 *   hardware, blower_aux_step() schedules PS3's inlet allowance from the commanded drive and hands
 *   it to the native-21 binding (n21_set_aux_allowance()) BEFORE the blower write; a speed-up is
 *   held until its allowance is in force, a fault or unknown state goes at once at the worst case.
 *   The stall detector runs on the state actually applied (blower_ctrl_finish()).
 */
#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "sdkconfig.h"
#include "config.h"
#include "controller_board.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "../components/control/thermal_mgmt.h"
#include "blower_aux.h"
#if CONFIG_TEMPER_POWER_HW_BINDING
#include "n21_hw.h"
#endif

static const char *TAG = "thermal_io";

/* Two control ticks: the ADC task refreshes the thermal means every frame (< 1 ms). */
#define THERMAL_MAX_AGE_US 20000u
#define BLOWER_TICK_S      0.1f

static uint32_t ms_since_boot(void) { return (uint32_t)(esp_timer_get_time() / 1000); }

/* NTC_OK and (for HS / COIL) NTC_BELOW_RANGE give a temperature; the latter is the ADC range
 * floor (~15 C), an upper bound for a healthy sensor, so the over-temperature interlocks stay
 * correct in a cold kitchen. An open HS / COIL NTC reads the same; the thermal-sense OPEN_REF
 * comparator latches it in hardware, and the blower tick runs full speed on it. */
static bool read_ntc(unsigned idx, const ntc_channel_t *ch, bool below_range_ok, float *temp_c,
                     bool *below_range)
{
    *temp_c = NAN;
    if (below_range) *below_range = false;
#if CONFIG_TEMPER_POWER_HW_BINDING
    if (!ntc_input_settled(ch, ms_since_boot())) return false;
    float mv[N21_THERMAL_COUNT];
    if (!n21_hw_thermal_mv(mv, THERMAL_MAX_AGE_US)) return false;
    float t = NAN;
    ntc_status_t st = ntc_channel_temp_c(ch, mv[idx], &t);
    if (below_range) *below_range = st == NTC_BELOW_RANGE || st == NTC_OPEN; /* cold or open */
    if (st == NTC_OK || (below_range_ok && st == NTC_BELOW_RANGE)) {
        *temp_c = t;
        return true;
    }
    return false;
#else
    (void)idx;
    (void)ch;
    (void)below_range_ok;
    return false;
#endif
}

#if CONFIG_TEMPER_POWER_HW_BINDING
#define IDX_HS   N21_THERMAL_HS
#define IDX_COIL N21_THERMAL_COIL
#define IDX_RIM  N21_THERMAL_RIM
#else
#define IDX_HS   0u
#define IDX_COIL 0u
#define IDX_RIM  0u
#endif

/* The rim has no hardware open detect: below range (cold, or open) is "no rim reading", and the
 * state handlers' plausibility check (thermal_plaus_t) latches a rim-sensor fault when it lasts
 * while the pan RTD reads hot. */
bool read_rim_temperature_status(float *temp_c, bool *cold_or_open)
{
    return read_ntc(IDX_RIM, &THERMAL_NTC_RIM, false, temp_c, cold_or_open);
}

bool read_rim_temperature(float *temp_c)
{
    return read_rim_temperature_status(temp_c, NULL);
}

static float read_sink(bool *below_range)
{
    float t;
    (void)read_ntc(IDX_HS, &THERMAL_NTC_SINK, true, &t, below_range);
    return t;
}

static float read_coil(bool *below_range)
{
    float t;
    (void)read_ntc(IDX_COIL, &THERMAL_NTC_COIL, true, &t, below_range);
    return t;
}

float read_heatsink_temperature(void) { return read_sink(NULL); }
float read_coil_temperature(void) { return read_coil(NULL); }

/* ---------------------------------------------------------------- blower */
static blower_ctrl_t s_blower;
static bool s_blower_init;
static blower_aux_cfg_t s_aux_cfg;
static blower_aux_t s_aux;
static bool s_blower_write_ok; /* last LEDC / FAN_OFF write took effect; false until the first */
/* Written by the monitor task, read by the control task: single bytes, so the accesses are
 * atomic. Until the first tick the cap is 0 (no tank power on an unknown thermal state). */
static volatile uint8_t s_power_cap_pct;
static volatile bool s_blower_failed;
/* Latched by the state handlers' plausibility check (control task). */
static volatile bool s_rim_sensor_fault, s_coil_sensor_fault;

void thermal_set_sensor_faults(bool rim_fault, bool coil_fault)
{
    s_rim_sensor_fault = rim_fault;
    s_coil_sensor_fault = coil_fault;
}

void thermal_blower_tick(void)
{
    if (!s_blower_init) {
        blower_ctrl_init(&s_blower);
        s_aux_cfg = blower_aux_native21();
        blower_aux_init(&s_aux, &s_aux_cfg);
        s_blower_write_ok = false;
        s_blower_init = true;
    }
    bool sink_low = false, coil_low = false;
    float sink_c = read_sink(&sink_low), coil_c = read_coil(&coil_low);
    /* Any hardware thermal trip, the interlock latch, a stale expander snapshot, or a sink / coil
     * node above the ADC's range (colder than ~15 C, or an open NTC: indistinguishable): full
     * speed. In a cold kitchen that is a short burst of noise until the sink warms past ~15 C. */
    ctrl_exp_cache_t c;
    bool exp_ok = ctrl_board_expander(&c) && ctrl_exp_fresh(&c, (uint64_t)esp_timer_get_time(),
                                                            CTRL_EXP_MAX_AGE_US);
    ctrl_exp_inputs_t in = ctrl_exp_decode(c.raw);
    bool coil_sensor_fault = s_coil_sensor_fault;
    bool fault = !exp_ok || in.hs_fault || in.coil_fault || in.latched_fault || sink_low || coil_low ||
                 coil_sensor_fault;
#if CONFIG_TEMPER_POWER_HW_BINDING
    /* Coil-sensor fault: the tank RMS ceiling is clamped to <= 22 A (n21 frequency loop). */
    n21_binding_t *b = n21_hw_binding();
    if (b && b->thermal_limited != coil_sensor_fault &&
        !n21_set_thermal_tank_limit(b, coil_sensor_fault, COIL_SENSOR_FAULT_TANK_MAX_A))
        ESP_LOGE(TAG, "coil-sensor tank clamp not applied");
#endif

    uint16_t count = 0;
    bool tach_ok = ctrl_board_blower_tach_count(&count);
    uint32_t now_ms = ms_since_boot();
    blower_cmd_t cmd = blower_ctrl_decide(&s_blower, sink_c, coil_c, fault, BLOWER_TICK_S);
    /* Inlet allowance first, then the blower (blower_aux.h). The fan law's fault path (any fault
     * or an invalid sink / coil reading) is urgent: full speed at once. */
    blower_aux_in_t ai = {.on = cmd.on, .duty = cmd.duty,
                          .urgent = fault || !isfinite(sink_c) || !isfinite(coil_c),
                          .known = s_blower_write_ok && !s_blower.stall.stalled,
                          .tach_rpm = s_blower.tach.rpm};
    blower_aux_out_t ao = blower_aux_step(&s_aux, &s_aux_cfg, &ai, now_ms);
#if CONFIG_TEMPER_POWER_HW_BINDING
    if (b && !n21_set_aux_allowance(b, ao.allowance_a))
        ESP_LOGE(TAG, "aux allowance not applied: binding stays at the worst case");
#endif
    s_blower_write_ok = ctrl_board_blower_apply(ao.on, blower_ledc_counts(ao.duty, CTRL_BLOWER_LEDC_RES_BITS));
    if (!s_blower_write_ok)
        ESP_LOGW(TAG, "blower drive not applied (LEDC / FAN_OFF): blower at its full-speed default");
    blower_ctrl_finish(&s_blower, &cmd, ao.on, sink_c, coil_c, tach_ok, count, now_ms,
                       BLOWER_TACH_PULSES_PER_REV);
    s_power_cap_pct = cmd.power_cap_pct;
    s_blower_failed = cmd.blower_failed;
}

uint8_t thermal_power_cap_pct(void)
{
    return s_power_cap_pct;
}

bool is_fan_running(void)
{
    return !s_blower_failed;
}
