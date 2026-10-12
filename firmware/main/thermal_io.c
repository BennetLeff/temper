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
 * - Blower (DECISIONS C28): thermal_blower_tick(), every MONITOR tick (100 ms): fan law -> FAN_OFF
 *   and the GPIO46 duty (duty 0 = full speed), FG tach -> rpm -> stall detector, and the tank
 *   power cap min(coil derate, stall derate) that thermal_power_cap_pct() hands the state
 *   handlers. is_fan_running() is false once the stall detector has stopped the tank (the blower
 *   failed and the sink or coil kept rising), which the state machine latches as FAULT_FAN_FAILURE.
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
    if (below_range) *below_range = st == NTC_BELOW_RANGE;
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

/* The rim has no hardware open detect: below range (cold, or open) is "no rim reading". */
bool read_rim_temperature(float *temp_c)
{
    return read_ntc(IDX_RIM, &THERMAL_NTC_RIM, false, temp_c, NULL);
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
/* Written by the monitor task, read by the control task: single bytes, so the accesses are
 * atomic. Until the first tick the cap is 0 (no tank power on an unknown thermal state). */
static volatile uint8_t s_power_cap_pct;
static volatile bool s_blower_failed;

void thermal_blower_tick(void)
{
    if (!s_blower_init) {
        blower_ctrl_init(&s_blower);
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
    bool fault = !exp_ok || in.hs_fault || in.coil_fault || in.latched_fault || sink_low || coil_low;

    uint16_t count = 0;
    bool tach_ok = ctrl_board_blower_tach_count(&count);
    blower_cmd_t cmd = blower_ctrl_step(&s_blower, sink_c, coil_c, fault, tach_ok, count,
                                        ms_since_boot(), BLOWER_TICK_S, BLOWER_TACH_PULSES_PER_REV);
    if (!ctrl_board_blower_apply(cmd.on, blower_ledc_counts(cmd.duty, CTRL_BLOWER_LEDC_RES_BITS)))
        ESP_LOGW(TAG, "blower drive not applied (LEDC / FAN_OFF): blower at its full-speed default");
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
