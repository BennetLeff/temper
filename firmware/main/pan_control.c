/**
 * @file pan_control.c
 * @brief Runtime adapter for the sensor-r3 C1 pan-temperature loop (see header).
 */

#include "pan_control.h"

#include <math.h>
#include <stddef.h>

#include "current_sense_check.h"
#include "hs_ntc.h"
#include "pan_cold_soak.h"
#include "pan_soak_store.h"
#include "pan_leak_check.h"
#include "pan_rim_limit.h"
#include "pan_supervisor.h"
#include "pan_temp_loop.h"
#include "rim_ntc.h"
#include "rtd_service.h"
#include "state_machine.h"

extern uint32_t get_time_ms(void);
extern void power_set_level(uint8_t level);
extern float read_dc_bus_current(void);
/* The heatsink NTC driver's reading (main/board_peripherals.c on the target,
 * the test stubs on the host); true when it is VALID. */
extern bool read_heatsink_ntc(hs_ntc_reading_t *out);

/* (c) of D-ISENSE: the input-current (AMC1301) vs bus-current cross-check.
 * Off until the input-current sense is on the board (nameplate-r1 D3). */
#ifndef TEMPER_INPUT_CURRENT_SENSE
#define TEMPER_INPUT_CURRENT_SENSE 0
#endif
#if TEMPER_INPUT_CURRENT_SENSE
extern float read_input_current(void);
#endif

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
static csc_t s_csc;                 /* bus-current sense plausibility (D-ISENSE) */
static plc_t s_plc;                 /* element-parallel Pt100 leakage (D-LEAK) */
static prl_t s_prl;                 /* setpoint-relative rim limit (D-RIMLIM) */
static pcs_t s_pcs;                 /* cold-soak history (D-SOAK) */
static pcs_t s_pcs_begin;           /* ... frozen at pan_control_begin() */
static bool s_soak_pending;         /* evaluate in the session's first period */
static uint32_t s_soak_begin_ms;
static float s_soak_pt_c;
static bool s_soak_hs_valid;
static float s_soak_hs_c;
static bool s_soak_rail_measured;   /* the heatsink reading used a measured rail (D-RAIL) */
static pcs_result_t s_soak_res;
static bool s_soak_latched;
static bool s_soak_have_note;
static pss_t s_pss;                 /* coil-off token in NVS (D-SOAKNV) */

/* The board's NVS binding (main/soak_store_nvs.c; host tests: a mock). */
extern const pss_hal_t *pan_soak_store_hal(void);

/* Read the coil-off token and credit it to a freshly initialised history. */
static void soak_store_boot(uint32_t now_ms)
{
    const uint32_t credit = pss_boot(&s_pss, pan_soak_store_hal());
    pcs_credit_off(&s_pcs, now_ms, credit);
}
static uint32_t s_soak_last_note_ms;

static void ensure_init(void)
{
    if (s_inited) {
        return;
    }
    psup_params_t sp;
    psup_default_params(&sp);
    (void)psup_init(&s_sup, &sp);
    csc_params_t cp;
    csc_default_params(&cp);
    (void)csc_init(&s_csc, &cp);
    plc_params_t lp;
    plc_default_params(&lp);
    (void)plc_init(&s_plc, &lp);
    prl_params_t rl;
    prl_default_params(&rl);
    (void)prl_init(&s_prl, &rl);
    pcs_params_t sp2;
    pcs_default_params(&sp2);
    (void)pcs_init(&s_pcs, &sp2, get_time_ms());
    soak_store_boot(get_time_ms());
    s_soak_res.verdict = PCS_NONE;
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

rtd_sensor_fail_t pan_control_reading_failure(void)
{
    rtd_sample_t smp;
    return latest(&smp) ? rtd_convert_classify_failure(smp.code, smp.fault_status) : RTD_SENSOR_OK;
}

bool pan_control_sensor_fault_clean(void)
{
    return rtd_service_fault_status_clean();
}

float pan_control_t_hat(void)
{
    return s_t_hat;
}

int pan_control_supervisor_latch(void)
{
    return s_inited ? (int)s_sup.latched : 0;
}

int pan_control_current_sense_latch(void)
{
    return s_inited ? (int)s_csc.latched : 0;
}

bool pan_control_leak_latched(void)
{
    return s_inited && s_plc.latched;
}

bool pan_control_rim_limit_latched(void)
{
    return s_inited && s_prl.latched;
}

/* The Pt100 reading for the cold soak: a conversion that is not a sensor
 * failure (D-OPEN), else NAN. */
static float soak_reading(void)
{
    rtd_sample_t smp;
    if (!latest(&smp) || !isfinite(smp.t_c) ||
        rtd_convert_classify_failure(smp.code, smp.fault_status) != RTD_SENSOR_OK) {
        return NAN;
    }
    return smp.t_c;
}

void pan_control_soak_note(uint32_t now_ms)
{
    ensure_init();
    const bool coil_active = s_running || s_p_applied_w > 0.0f;
    if (!coil_active && s_soak_have_note && (uint32_t)(now_ms - s_soak_last_note_ms) < 1000u) {
        return;
    }
    s_soak_have_note = true;
    s_soak_last_note_ms = now_ms;
    hs_ntc_reading_t hs;
    const bool hs_valid = read_heatsink_ntc(&hs);
    pcs_note_rail(&s_pcs, now_ms, coil_active, soak_reading(), hs_valid, hs.t_c, !hs.rail_nominal);
    pss_note(&s_pss, pan_soak_store_hal(), coil_active, pcs_off_s(&s_pcs, now_ms));
}

void pan_control_soak_restart(void)
{
    ensure_init();
    /* state_machine_init() enters INIT without leaving PREHEAT/HEATING
     * through transition_to(), so the loop is marked stopped here: no
     * session survives a (re)initialisation, and the soak history must not
     * see one as coil activity. */
    s_running = false;
    s_p_applied_w = 0.0f;
    const pcs_params_t p = s_pcs.p;
    (void)pcs_init(&s_pcs, &p, get_time_ms());
    soak_store_boot(get_time_ms());
    s_soak_have_note = false;
}

const pss_t *pan_control_soak_store(void)
{
    return &s_pss;
}

pcs_result_t pan_control_cold_soak_result(void)
{
    return s_soak_res;
}

bool pan_control_cold_soak_latched(void)
{
    return s_soak_latched;
}

bool pan_control_cold_soak_clearable(void)
{
    if (!s_inited || !s_soak_latched || s_plc.latched || s_prl.latched) {
        return false;
    }
    hs_ntc_reading_t hs;
    const bool hs_valid = read_heatsink_ntc(&hs);
    return pcs_agrees_rail(&s_pcs, soak_reading(), hs_valid, hs.t_c, !hs.rail_nominal);
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
    /* D-ISENSE: fresh plausibility state, and the start-up current pulse
     * before the loop heats (a pan is present: PAN_DET confirmed it). */
    {
        const csc_params_t cp = s_csc.p;
        s_running = csc_init(&s_csc, &cp) && s_running;
        csc_pulse_begin(&s_csc);
        const plc_params_t lp = s_plc.p;
        s_running = plc_init(&s_plc, &lp) && s_running;
        /* D-RIMLIM: the reference restarts with the session; a glass still
         * hot from the last one is falling, which the rule ignores. */
        const prl_params_t rl = s_prl.p;
        s_running = prl_init(&s_prl, &rl) && s_running;
    }
    /* Fresh rim detection per heating session, as ptl_init clears the guard;
     * a persisting rim fault latches again within short_persist periods. */
    const rim_ntc_params_t rp = s_rim.p;
    s_running = rim_ntc_init(&s_rim, &rp) && s_running;
    s_rim_rd = s_rim.last;
    s_xcheck_suspects = 0u;
    /* D-SOAKNV: no coil-off token may outlive this session's first power.
     * A failed revoke is counted and the store disabled; heating goes on
     * (pan_soak_store.h: a stale token can only cause a false, clearable
     * cold-soak latch after a later power cycle). */
    (void)pss_revoke(&s_pss, pan_soak_store_hal());
    /* D-SOAK: freeze the coil-off history before this session marks the coil
     * active; the first control period evaluates it with the rim's reading. */
    s_pcs_begin = s_pcs;
    s_soak_begin_ms = get_time_ms();
    s_soak_pt_c = soak_reading();
    {
        hs_ntc_reading_t hs;
        s_soak_hs_valid = read_heatsink_ntc(&hs);
        s_soak_hs_c = hs.t_c;
        s_soak_rail_measured = !hs.rail_nominal;
    }
    s_soak_pending = true;
    s_soak_latched = false;
    s_soak_res.verdict = PCS_NONE;
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
    /* The bus current of the period that just ended, under s_p_applied_w. */
    const float i_bus = read_dc_bus_current();
    /* Rim NTC: one driver period; the open rule uses the last estimate. */
    rim_ntc_step(&s_rim, rim_ntc_board_hal(), s_t_hat, &s_rim_rd);
    const bool rim_fault = s_rim_rd.state == RIM_NTC_FAULT;
    /* D-SOAK: the session's first period, before any power is commanded. */
    if (s_soak_pending) {
        s_soak_pending = false;
        s_soak_res = pcs_evaluate_rail(&s_pcs_begin, s_soak_begin_ms, s_soak_pt_c, s_soak_hs_valid,
                                       s_soak_hs_c, s_rim_rd.state == RIM_NTC_SATURATED, s_soak_rail_measured);
        if (s_soak_res.verdict == PCS_LEAK) {
            s_soak_latched = true;
            s_p_applied_w = 0.0f;
            power_set_level(0);
            state_machine_report_latched_fault(FAULT_PROBE_LEAKAGE);
            return PAN_CONTROL_SENSOR_FAULT;
        }
    }
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
    /* D-LEAK: repeated cross-check suspects on intact contact. */
    bool leak_fault = plc_step(&s_plc, out.xcheck_suspect, (int)out.cc_event, in.t_pt100_c,
                               s_rim_rd.state == RIM_NTC_VALID ? s_rim_rd.t_c : NAN);
    /* D-RIMLIM: a rim hotter than any pan at the loop's temperature can make it. */
    leak_fault = prl_step(&s_prl, setpoint_c, out.t_hat_c, s_rim_rd.state == RIM_NTC_VALID, s_rim_rd.t_c) ||
                 leak_fault;

    float p_cmd = out.p_cmd_w;
    /* D-ISENSE (b): the start-up pulse replaces the loop's command until it
     * has shown current; the limits below still apply to it. */
    if (csc_pulse_active(&s_csc)) {
        float pulse_w = 0.0f;
        const csc_pulse_state_t ps = csc_pulse_step(&s_csc, s_p_applied_w, i_bus, p_max, &pulse_w);
        if (ps == CSC_PULSE_PENDING || ps == CSC_PULSE_RUNNING) {
            p_cmd = pulse_w;
        }
    }
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

    /* D-ISENSE (a), and (c) when the input-current sense is fitted. */
    bool isense_fault = csc_run_step(&s_csc, s_p_applied_w, i_bus);
#if TEMPER_INPUT_CURRENT_SENSE
    isense_fault = csc_xcheck_step(&s_csc, read_input_current(), i_bus) || isense_fault;
#endif

    if (out.fault != PSG_OK || so.latch != PSUP_OK || rim_fault || isense_fault || leak_fault) {
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
    if (isense_fault) {
        state_machine_report_latched_fault(FAULT_CURRENT_SENSE);
        return PAN_CONTROL_SENSOR_FAULT;
    }
    if (leak_fault) {
        state_machine_report_latched_fault(FAULT_PROBE_LEAKAGE);
        return PAN_CONTROL_SENSOR_FAULT;
    }
    if (out.cc_event == CC_EVT_LOST) {
        state_machine_report_pan_contact_lost();
    }
    return PAN_CONTROL_RAN;
}
