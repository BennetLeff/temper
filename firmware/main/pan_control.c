/**
 * @file pan_control.c
 * @brief Runtime adapter for the sensor-r3 C1 pan-temperature loop (see header).
 */

#include "pan_control.h"

#include <math.h>
#include <stddef.h>

#include "pan_supervisor.h"
#include "pan_temp_loop.h"
#include "rim_ntc.h"
#include "rtd_service.h"
#include "state_machine.h"

extern uint32_t get_time_ms(void);
extern void power_set_level(uint8_t level);
extern float read_dc_bus_current(void);

static ptl_params_t s_params;
static ptl_t s_loop;
static psup_t s_sup;
static bool s_inited;
static bool s_running;
static uint32_t s_last_ms;
static uint32_t s_last_seq;
static float s_p_applied_w;
static float s_t_hat = NAN;
static rim_ntc_t s_rim;
static rim_ntc_reading_t s_rim_rd;
static uint32_t s_xcheck_suspects;

static void ensure_init(void)
{
    if (s_inited) {
        return;
    }
    psup_params_t sp;
    psup_default_params(&sp);
    (void)psup_init(&s_sup, &sp);
    ptl_default_params(&s_params);
    rim_ntc_params_t rp;
    rim_ntc_default_params(&rp);
    (void)rim_ntc_init(&s_rim, &rp);
    s_rim_rd = s_rim.last;
    s_inited = true;
}

/*
 * The loop's rim input (KF leak sink, D1 free-decay asymptote and the
 * cross-check; DECISIONS.md D-RIM):
 *   VALID      the filtered rim temperature;
 *   SATURATED  the rim is below the saturation bound (about 92 degC): use the
 *              smaller of the bound and the Pt100 reading. The bound is an
 *              upper limit, and the glass under a heated pan is not hotter
 *              than the pan, so this is the closer of the two known limits.
 *              Because it never exceeds the reading, the cross-check
 *              (reading < rim - 25 K) cannot fire on a saturated rim: no
 *              information, no suspect;
 *   otherwise  the Pt100 reading (no rim information; a rim FAULT also cuts
 *              the power this period).
 * The value must be finite: a NAN sink would corrupt the KF.
 */
static float loop_rim_input(const rim_ntc_reading_t *rd, float reading_c)
{
    if (rd->state == RIM_NTC_VALID && isfinite(rd->t_c)) {
        return rd->t_c;
    }
    float fallback = reading_c;
    if (!isfinite(fallback)) {
        fallback = isfinite(s_t_hat) ? s_t_hat : s_params.pg.t_amb_c;
    }
    if (rd->state == RIM_NTC_SATURATED && isfinite(rd->t_c) && rd->t_c < fallback) {
        return rd->t_c;
    }
    return fallback;
}

float read_rim_ntc_temperature(void)
{
    return (s_rim_rd.state == RIM_NTC_VALID) ? s_rim_rd.t_c : NAN;
}

bool pan_control_rim_reading(rim_ntc_reading_t *out)
{
    ensure_init();
    if (out != NULL) {
        *out = s_rim_rd;
    }
    return s_rim_rd.state == RIM_NTC_VALID;
}

uint32_t pan_control_xcheck_suspects(void)
{
    return s_xcheck_suspects;
}

static bool latest(rtd_sample_t *smp)
{
    return rtd_service_latest_sample(smp);
}

bool pan_control_have_reading(void)
{
    rtd_sample_t smp;
    return latest(&smp);
}

float pan_control_reading_c(void)
{
    rtd_sample_t smp;
    return latest(&smp) ? smp.t_c : NAN;
}

float pan_control_resistance_ohm(void)
{
    rtd_sample_t smp;
    return latest(&smp) ? smp.r_ohm : NAN;
}

bool pan_control_sensor_ready(void)
{
    return rtd_service_is_ready();
}

float pan_control_t_hat(void)
{
    return s_t_hat;
}

int pan_control_supervisor_latch(void)
{
    return s_inited ? (int)s_sup.latched : 0;
}

bool pan_control_rate_sample(float reading_c, uint32_t now_ms)
{
    ensure_init();
    return psup_rate_sample(&s_sup, reading_c, now_ms);
}

void pan_control_rate_reset(void)
{
    ensure_init();
    psup_rate_reset(&s_sup);
}

void pan_control_begin(void)
{
    ensure_init();
    rtd_sample_t smp;
    const float t0 = (latest(&smp) && isfinite(smp.t_c)) ? smp.t_c : s_params.pg.t_amb_c;
    s_running = ptl_init(&s_loop, &s_params, t0);
    psup_r2_reset(&s_sup);
    /* Fresh rim detection per heating session, as ptl_init clears the guard;
     * a persisting rim fault latches again within short_persist periods. */
    const rim_ntc_params_t rp = s_rim.p;
    s_running = rim_ntc_init(&s_rim, &rp) && s_running;
    s_rim_rd = s_rim.last;
    s_xcheck_suspects = 0u;
    s_last_ms = get_time_ms();
    s_last_seq = latest(&smp) ? smp.seq : 0u;
    s_p_applied_w = 0.0f;
    s_t_hat = t0;
    power_set_level(0);
}

void pan_control_stop(void)
{
    s_running = false;
    s_p_applied_w = 0.0f;
    power_set_level(0);
}

bool pan_control_is_running(void)
{
    return s_running;
}

pan_control_status_t pan_control_step(float setpoint_c, uint8_t intensity_level)
{
    ensure_init();
    if (!s_running) {
        /* ptl_init rejected the parameters: never heat without the loop. */
        power_set_level(0);
        return PAN_CONTROL_SENSOR_FAULT;
    }
    const uint32_t now = get_time_ms();
    if ((uint32_t)(now - s_last_ms) < PAN_CONTROL_PERIOD_MS) {
        return PAN_CONTROL_HOLD;
    }
    s_last_ms = now;

    /* Intensity 1..10 limits the loop's power, as the legacy handlers did. */
    uint8_t level = intensity_level < 1u ? 1u : (intensity_level > 10u ? 10u : intensity_level);
    const float p_max = PAN_CONTROL_P_MAX_W * (float)level / 10.0f;
    ptl_set_power_limit(&s_loop, p_max);

    rtd_sample_t smp;
    const bool have = latest(&smp);
    /* Rim NTC: one driver period; the open rule uses the last estimate. */
    rim_ntc_step(&s_rim, rim_ntc_board_hal(), s_t_hat, &s_rim_rd);
    const bool rim_fault = s_rim_rd.state == RIM_NTC_FAULT;
    const ptl_input_t in = {
        .t_pt100_c = have ? smp.t_c : NAN,
        .t_rim_c = loop_rim_input(&s_rim_rd, have ? smp.t_c : NAN),
        .fresh = have && smp.seq != s_last_seq,
        .spi_ok = have && smp.spi_ok,
        .fault_status = have ? smp.fault_status : 0u,
        .setpoint_c = setpoint_c,
        .power_applied_w = s_p_applied_w,
        .power_source = PG_POWER_ESTIMATED,
    };
    if (have) {
        s_last_seq = smp.seq;
    }
    ptl_output_t out;
    ptl_step(&s_loop, &in, &out);
    s_t_hat = out.t_hat_c;
    if (out.xcheck_suspect) {
        s_xcheck_suspects++;
    }

    float p_cmd = out.p_cmd_w;
    const float i_bus = read_dc_bus_current();
    const psup_input_t si = {
        .t_hat_c = out.t_hat_c,
        .t_raw_c = in.t_pt100_c,
        .setpoint_c = setpoint_c,
        .p_cmd_w = p_cmd,
        .bus_current_a = i_bus,
        /* No validity signal exists for the bus-current sense yet; a sense
         * stuck at 0 is the double fault stage 2b covers. */
        .current_valid = isfinite(i_bus),
    };
    psup_output_t so;
    psup_step(&s_sup, &si, &so);
    if (so.force_zero) {
        p_cmd = 0.0f;
    }

    if (out.fault != PSG_OK || so.latch != PSUP_OK || rim_fault) {
        p_cmd = 0.0f;
    }
    long pct = lroundf(p_cmd / PAN_CONTROL_P_MAX_W * 100.0f);
    pct = pct < 0 ? 0 : (pct > 100 ? 100 : pct);
    power_set_level((uint8_t)pct);
    s_p_applied_w = (float)pct / 100.0f * PAN_CONTROL_P_MAX_W;

    if (so.latch != PSUP_OK) {
        return PAN_CONTROL_RUNAWAY;
    }
    if (out.fault != PSG_OK) {
        state_machine_report_rtd_device_fault(out.fault == PSG_FAULT_SHORT, out.fault == PSG_FAULT_OPEN, NULL);
        return PAN_CONTROL_SENSOR_FAULT;
    }
    if (rim_fault) {
        /* D-RIM: a rim fault latches through the same RTD sink. */
        rim_ntc_report(&s_rim_rd, state_machine_report_rtd_device_fault, NULL);
        return PAN_CONTROL_SENSOR_FAULT;
    }
    if (out.cc_event == CC_EVT_LOST) {
        state_machine_report_pan_contact_lost();
    }
    return PAN_CONTROL_RAN;
}
