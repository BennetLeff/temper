/**
 * @file test_c1_runtime.c
 * @brief TEMPER_PAN_CONTROL_C1 runtime: the state machine driving the C1 loop
 *        through main/pan_control.c, with the C1 runaway checks (D-RUN).
 *
 * rtd_service_latest_sample() and rim_ntc_board_hal() are stubbed here so
 * each test sets the MAX31865 conversion and the rim temperature directly;
 * the rtd_service C1 conversion path itself is covered by
 * test_c1_rtd_service.c, the rim driver by test_c1_rim_ntc.c.
 */

#include <math.h>
#include <string.h>

#include "unity/unity.h"
#include "../main/state_machine.h"
#include "../main/pan_control.h"
#include "../main/state_handlers.h"
#include "../components/sensors/include/rim_ntc.h"
#include "../components/sensors/include/rtd_service.h"

extern void mock_sm_reset(void);
extern void mock_sm_advance_time(uint32_t ms);
extern void mock_sm_set_pan_status(int status);
extern uint32_t mock_sm_get_power_level(void);
extern void mock_sm_set_heatsink_temperature(float temp_c);
extern void mock_sm_set_thermal_cap(uint8_t pct);
extern void mock_sm_set_pan_refused(bool refused);
extern void mock_sm_press_button(button_id_t button);
extern void mock_sm_release_button(button_id_t button);
extern void mock_sm_set_heatsink_ntc_state(int state);

#define MOCK_PAN_PRESENT 1

static rtd_sample_t s_smp;
static bool s_have;
static float s_rim = 40.0f;

bool rtd_service_latest_sample(rtd_sample_t *out)
{
    if (!s_have || out == NULL) {
        return false;
    }
    *out = s_smp;
    return true;
}

/* Rim NTC board HAL: the node voltage of the 104GT-2 at s_rim under the
 * 1.00 k pull-up and a 3300 mV rail, clipped as the ADC clips and rounded to
 * whole mV (the ESP-IDF calibration returns integer mV). s_rim_node_mv forces
 * a node voltage (short, open), s_rim_adc_fail fails every read. */
static float s_rim_node_mv = NAN;
static bool s_rim_adc_fail;

static bool rim_read_node(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    if (s_rim_adc_fail) {
        return false;
    }
    float v = s_rim_node_mv;
    if (!isfinite(v)) {
        const float r = rim_ntc_c_to_r(s_rim);
        v = 3300.0f * r / (r + 1000.0f);
    }
    const float clip = atten == RIM_ATTEN_0 ? 950.0f : (atten == RIM_ATTEN_2 ? 1700.0f : 3100.0f);
    *mv = roundf(v < clip ? v : clip);
    return true;
}

static bool rim_read_rail(void *ctx, float *mv)
{
    (void)ctx;
    *mv = 3300.0f;
    return true;
}

static const rim_ntc_hal_t s_rim_hal = {.read_node_mv = rim_read_node, .read_v3v3_mv = rim_read_rail, .ctx = NULL};
const rim_ntc_hal_t *rim_ntc_board_hal(void) { return &s_rim_hal; }

/* The converter service is not linked here; it is running whenever a
 * conversion has been set (test_c1_rtd_service.c covers it stopping). */
static bool s_service_stopped;
bool rtd_service_is_ready(void) { return s_have && !s_service_stopped; }
/* Register 07h is not modelled here: clean unless a test flags it. */
bool rtd_service_fault_status_clean(void) { return s_smp.fault_status == 0u; }

static void set_reading(float t_c)
{
    /* Callendar-Van Dusen T >= 0 for the resistance; the code is not used. */
    s_smp.t_c = t_c;
    s_smp.r_ohm = 100.0f * (1.0f + 3.9083e-3f * t_c - 5.775e-7f * t_c * t_c);
    s_smp.code = (uint16_t)lroundf(s_smp.r_ohm / 430.0f * 32768.0f);
    s_smp.spi_ok = true;
    s_smp.fault_status = 0u;
    s_smp.seq++;
    s_have = true;
}

/* The stage: the native-21 binding's measured power. The supervisor and the current-sense check see
 * it as a current at PAN_CONTROL_I_REF_V (100 V), so s_i_force x 100 V is the power a test forces. By
 * default an obeying stage on a 120 V line, as main's tests (P_cmd / 120 V). */
static float s_i_force = NAN;
static float s_stage_w;
static bool s_stage_valid = true;

bool read_stage_power(pan_stage_power_t *out)
{
    out->p_inv_w = s_stage_w;
    out->valid = s_stage_valid;
    return s_stage_valid;
}

static void set_bus_current(void)
{
    const float i = isfinite(s_i_force) ? s_i_force
                                        : (float)mock_sm_get_power_level() / 100.0f * 1800.0f / 120.0f;
    s_stage_w = i * 100.0f; /* W per A, literal: the check's scale is under test */
}

/* 10 ms state-machine ticks; a fresh conversion every other tick. */
static void run_ms(uint32_t ms, float (*reading)(uint32_t), uint32_t *clock)
{
    for (uint32_t t = 0; t < ms; t += 10u) {
        mock_sm_advance_time(10u);
        set_bus_current();
        *clock += 10u;
        if (reading != NULL && (*clock % 20u) == 0u) {
            set_reading(reading(*clock));
        }
        state_machine_update();
    }
}

static uint32_t s_clock;
static float s_hold_t;
static float hold(uint32_t t_ms) { (void)t_ms; return s_hold_t; }

static void start(system_state_t st, float target, uint8_t intensity, float t0)
{
    mock_sm_reset();
    memset(&s_smp, 0, sizeof(s_smp));
    s_have = false;
    s_clock = 0u;
    s_rim = 40.0f;
    s_rim_node_mv = NAN;
    s_rim_adc_fail = false;
    s_i_force = NAN;
    s_stage_valid = true;
    s_stage_w = 0.0f;
    mock_sm_advance_time(1000u);
    state_machine_init();
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    state_machine_set_target_temp(target);
    state_machine_set_intensity(intensity);
    set_reading(t0);
    state_machine_reset_temp_baseline();
    state_machine_force_state(st);
}

/* main.c runs the RTD service to its first reading before the control task, so a tick without one is
 * a probe fault here (sensor-r3's main waits): never RUNAWAY. */
static void test_no_conversion_is_a_probe_fault_not_runaway(void)
{
    mock_sm_reset();
    memset(&s_smp, 0, sizeof(s_smp));
    s_have = false;
    state_machine_init();
    state_machine_force_state(STATE_IDLE);
    run_ms(1000u, NULL, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/* ---- native-21 stage ------------------------------------------------------ */
/* The lowest continuous power is what the pan draws at 60 kHz: 73-175 W at 120 V, x 1.21 at 132 V
 * (COMMISSIONING H12), plus the 10 % estimator error: 233 W at a 1 % command must not latch. */
static void test_stage_floor_power_is_not_disobedience(void)
{
    start(STATE_HEATING, 200.0f, 10u, 199.0f);
    s_hold_t = 199.0f;
    run_ms(2000u, hold, &s_clock);
    for (int k = 0; k < 3000; k++) {
        s_i_force = mock_sm_get_power_level() > 0u ? fmaxf(2.33f, (float)mock_sm_get_power_level() * 0.15f) : 0.0f;
        s_hold_t = 199.0f + 0.5f * sinf((float)k * 0.02f);
        run_ms(10u, hold, &s_clock);
    }
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

static bool heat_until_power(uint8_t min_pct);

/* Stale or missing stage power while power is commanded is a dead sense: fail closed. */
static void test_invalid_stage_power_while_heating_latches_current_sense(void)
{
    start(STATE_HEATING, 200.0f, 10u, 100.0f);
    s_hold_t = 100.0f;
    TEST_ASSERT_TRUE(heat_until_power(20u));
    s_stage_valid = false;
    run_ms(1000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_CURRENT_SENSE, state_machine_get_fault());
}

/* The binding holds the request refused (no pan, or lifted): power 0, COOLDOWN, the user starts
 * again (UL 858 47.8), and not a current-sense fault although the stage draws nothing. */
static void refused_in(system_state_t st)
{
    start(st, 200.0f, 10u, 100.0f);
    s_hold_t = 100.0f;
    TEST_ASSERT_TRUE(heat_until_power(20u));
    s_i_force = 0.0f;
    mock_sm_set_pan_refused(true);
    run_ms(200u, hold, &s_clock);
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
    mock_sm_set_pan_refused(false);         /* the pan is back: it must not resume on its own */
    for (int k = 0; k < 1000; k++) {
        run_ms(10u, hold, &s_clock);
        TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
    }
    TEST_ASSERT_TRUE(state_machine_get_state() == STATE_COOLDOWN || state_machine_get_state() == STATE_IDLE);
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}
static void test_pan_refusal_while_heating_stops_without_a_fault(void) { refused_in(STATE_HEATING); }
static void test_pan_refusal_in_preheat_stops_without_a_fault(void) { refused_in(STATE_PREHEAT); }

/* Every command still passes the 250 C cap and the coil / blower derate. */
static void test_thermal_cap_limits_the_loop(void)
{
    start(STATE_HEATING, 200.0f, 10u, 60.0f);
    mock_sm_set_thermal_cap(15u);
    s_hold_t = 60.0f;
    uint32_t max = 0u;
    for (int k = 0; k < 300; k++) {
        run_ms(10u, hold, &s_clock);
        if (mock_sm_get_power_level() > max) max = mock_sm_get_power_level();
    }
    TEST_ASSERT_EQUAL_UINT32(15u, max);
    mock_sm_set_thermal_cap(0u);
    run_ms(200u, hold, &s_clock);
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
    run_ms(2000u, hold, &s_clock);          /* and 0 W by derate is not a dead sense */
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

/* A stopped MAX31865 service refuses the reset of any fault, also one that has cleared. */
static void test_reset_refused_while_the_rtd_service_is_stopped(void)
{
    for (int stopped = 1; stopped >= 0; stopped--) {
        start(STATE_HEATING, 200.0f, 10u, 100.0f);
        mock_sm_set_heatsink_temperature(90.0f);
        state_machine_report_latched_fault(FAULT_OVER_TEMP);
        mock_sm_set_heatsink_temperature(25.0f);
        s_hold_t = 100.0f;
        s_service_stopped = stopped != 0;
        mock_sm_press_button(BUTTON_BACK);
        run_ms(50u, hold, &s_clock);
        mock_sm_release_button(BUTTON_BACK);
        TEST_ASSERT_EQUAL_INT(stopped ? FAULT_OVER_TEMP : FAULT_NONE, state_machine_get_fault());
        s_service_stopped = false;
    }
}

/* With power commanded off, "no power" is 50 W. */
static system_state_t off_with_stage_at(float i_force)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 215.0f;
    run_ms(1000u, hold, &s_clock);
    s_i_force = i_force;
    run_ms(2000u, hold, &s_clock);
    return state_machine_get_state();
}
static void test_residual_power_limit_while_off_is_50_w(void)
{
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, off_with_stage_at(0.45f));
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, off_with_stage_at(0.55f));
    TEST_ASSERT_EQUAL_INT(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
}

/* R1: a sustained 20 K/s latches RUNAWAY within about 6 s, far below 300 degC. */
static float ramp_20k_s(uint32_t t_ms) { return 25.0f + 0.02f * (float)t_ms; }
static void test_sustained_rise_latches_runaway(void)
{
    start(STATE_IDLE, 200.0f, 10u, 25.0f);
    run_ms(9000u, ramp_20k_s, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_RUNAWAY_FAULT, state_machine_get_state());
    TEST_ASSERT_TRUE(ramp_20k_s(s_clock) < 300.0f);
}

/* The loop runs at the cap (its own power limit), so a released derate does not release a wound-up
 * integrator. */
static void test_thermal_cap_does_not_wind_up_the_loop(void)
{
    start(STATE_HEATING, 200.0f, 10u, 193.5f);
    mock_sm_set_thermal_cap(5u);
    s_hold_t = 193.5f;                      /* a derate holds the pan about 5 K low */
    run_ms(120000u, hold, &s_clock);
    mock_sm_set_thermal_cap(100u);
    s_hold_t = 198.5f;                      /* it reaches the setpoint as the derate lifts */
    run_ms(5000u, hold, &s_clock);
    TEST_ASSERT_TRUE(mock_sm_get_power_level() <= 5u); /* 19 % without the cap in the loop */
}

static uint32_t s_place_ms;
static float placed_hot_pan(uint32_t t_ms)
{
    if (t_ms < s_place_ms) {
        return 25.0f;
    }
    return 240.0f - 215.0f * expf(-(float)(t_ms - s_place_ms) / 1350.0f);
}

static void test_hot_pan_placed_in_idle_does_not_latch_runaway(void)
{
    start(STATE_IDLE, 200.0f, 10u, 25.0f);
    s_place_ms = s_clock + 1000u;
    run_ms(20000u, placed_hot_pan, &s_clock);
    TEST_ASSERT_TRUE(state_machine_get_state() != STATE_RUNAWAY_FAULT);
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

static void test_absolute_300_still_latches_runaway(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 305.0f;
    run_ms(30u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_RUNAWAY_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_RUNAWAY_BOUNDARY, state_machine_get_fault());
}

static void test_preheat_heats_and_hands_over_on_the_estimate(void)
{
    start(STATE_PREHEAT, 200.0f, 10u, 25.0f);
    s_hold_t = 25.0f;
    run_ms(500u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);
    s_hold_t = 195.0f;
    run_ms(5000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_TRUE(pan_control_t_hat() >= 190.0f);
}

static void test_intensity_limits_the_loop_power(void)
{
    start(STATE_PREHEAT, 200.0f, 3u, 25.0f);
    s_hold_t = 25.0f;
    for (int i = 0; i < 20; i++) {
        run_ms(100u, hold, &s_clock);
        TEST_ASSERT_TRUE(mock_sm_get_power_level() <= 30u);
    }
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);
}

static void test_reading_over_target_plus_10_holds_power_off_without_latching(void)
{
    /* h_c drop: T_c up to target + 13 K (legacy latched FAULT_THERMAL_RUNAWAY) */
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 213.0f;
    run_ms(30000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
}

static void test_lowered_target_does_not_latch(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 200.0f;
    run_ms(2000u, hold, &s_clock);
    state_machine_set_target_temp(170.0f);
    for (int i = 0; i < 300; i++) {
        s_hold_t -= 0.1f;   /* cooling with the power off */
        run_ms(100u, hold, &s_clock);
    }
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

static void test_power_stage_drawing_current_with_power_off_latches_thermal_runaway(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 215.0f;
    run_ms(1000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    s_i_force = 10.0f;
    run_ms(1500u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
}

static void test_still_rising_with_power_off_latches_thermal_runaway(void)
{
    /* stuck-on stage and a current sense reading 0: 2b after 20 s */
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 211.0f;
    s_i_force = 0.0f;
    uint32_t elapsed = 0u;
    while (state_machine_get_state() == STATE_HEATING && elapsed < 60000u) {
        s_hold_t += 0.03f;    /* 3 K/s */
        run_ms(10u, hold, &s_clock);
        elapsed += 10u;
    }
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
    TEST_ASSERT_TRUE(elapsed >= 20000u && elapsed <= 21000u);
}

static void test_rtd_resistance_interlock_uses_the_c1_window(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 200.0f;
    run_ms(200u, hold, &s_clock);
    /* 80 ohm: inside the legacy 10..300 ohm window, below the C1 84.27 ohm */
    s_smp.r_ohm = 80.0f;
    s_smp.t_c = -50.0f;
    s_smp.seq++;
    mock_sm_advance_time(10u);
    state_machine_update();
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_SHORT, state_machine_get_fault());
}

static void test_leaving_heating_stops_the_loop(void)
{
    start(STATE_HEATING, 200.0f, 10u, 150.0f);
    s_hold_t = 150.0f;
    run_ms(500u, hold, &s_clock);
    TEST_ASSERT_TRUE(pan_control_is_running());
    state_machine_force_state(STATE_COOLDOWN);
    TEST_ASSERT_FALSE(pan_control_is_running());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
}


/* ---- rim NTC in the loop (DECISIONS.md D-XCHK, D-RIM) ------------------ */

static float s_ramp_t0;
static uint32_t s_ramp_ms0;
static float s_ramp_k_per_s;
static float ramp(uint32_t t_ms)
{
    return s_ramp_t0 + s_ramp_k_per_s * (float)(t_ms - s_ramp_ms0) / 1000.0f;
}

/* A Pt100 that reads low and does not follow the heating (stuck, or
 * element-parallel leakage at a hold), with the rim NTC valid and hot. */
static void test_rim_cross_check_fires_on_a_low_flat_pt100(void)
{
    start(STATE_HEATING, 200.0f, 10u, 180.0f);
    s_rim = 215.0f;               /* reading 180 < 215 - 25 */
    s_hold_t = 180.0f;
    run_ms(29000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_UINT32(0u, pan_control_xcheck_suspects());
    run_ms(2500u, hold, &s_clock);
    TEST_ASSERT_EQUAL_UINT32(1u, pan_control_xcheck_suspects());
    rim_ntc_reading_t rd;
    TEST_ASSERT_TRUE(pan_control_rim_reading(&rd));
    TEST_ASSERT_FLOAT_WITHIN(0.3f, 215.0f, read_rim_ntc_temperature());
    /* A suspect asks D1 for a probe; it is not a fault. */
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

/* Cold-food quench: the reading sits 40 K below the hot rim but rises as the
 * loop reheats the load, so the count keeps restarting. */
static void test_rim_cross_check_ignores_a_cold_food_quench(void)
{
    start(STATE_HEATING, 200.0f, 10u, 150.0f);
    s_rim = 190.0f;
    s_ramp_t0 = 150.0f;
    s_ramp_ms0 = s_clock;
    s_ramp_k_per_s = 0.25f;       /* 7.5 K per 30 s: rising, as a reheating load does */
    run_ms(50000u, ramp, &s_clock);
    /* still below rim - 25 K after 50 s, with the power on for 40 s of it */
    TEST_ASSERT_TRUE(ramp(s_clock) < 190.0f - 25.0f);
    TEST_ASSERT_EQUAL_UINT32(0u, pan_control_xcheck_suspects());
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);   /* no probe either */
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

/* A saturated (cold) rim carries no information: no cross-check, even with a
 * flat reading below the saturation bound minus 25 K. */
static void test_saturated_rim_never_cross_checks(void)
{
    start(STATE_HEATING, 200.0f, 10u, 60.0f);
    s_rim = 80.0f;                /* below the ~92 degC saturation bound */
    s_hold_t = 60.0f;
    run_ms(35000u, hold, &s_clock);
    rim_ntc_reading_t rd;
    TEST_ASSERT_FALSE(pan_control_rim_reading(&rd));
    TEST_ASSERT_EQUAL_INT(RIM_NTC_SATURATED, rd.state);
    TEST_ASSERT_TRUE(isnan(read_rim_ntc_temperature()));
    TEST_ASSERT_EQUAL_UINT32(0u, pan_control_xcheck_suspects());
    TEST_ASSERT_TRUE(isfinite(pan_control_t_hat()));
}

static void test_rim_short_latches_probe_short_and_cuts_power(void)
{
    start(STATE_HEATING, 200.0f, 10u, 190.0f);
    s_rim = 170.0f;
    s_hold_t = 190.0f;
    run_ms(2000u, hold, &s_clock);
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);
    s_rim_node_mv = 120.0f;       /* < 0.25 V */
    run_ms(200u, hold, &s_clock); /* two periods: still a candidate */
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    run_ms(200u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
}

static void test_rim_open_latches_probe_open_after_600s_hot(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_rim_node_mv = 3300.0f;      /* open bead: full scale */
    s_hold_t = 200.0f;
    run_ms(598000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    run_ms(3000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

static void test_rim_adc_failure_latches_probe_open(void)
{
    start(STATE_HEATING, 200.0f, 10u, 190.0f);
    s_rim = 170.0f;
    s_hold_t = 190.0f;
    run_ms(1000u, hold, &s_clock);
    s_rim_adc_fail = true;
    run_ms(900u, hold, &s_clock);  /* nine periods: held */
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    run_ms(200u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/* ---- D-ISENSE through the state machine and pan_control ---------------------- */

/* Heat a pan held at 150 degC toward 200 degC until the loop commands at
 * least min_pct (the start-up pulse runs first); false if it never does. */
static bool heat_until_power(uint8_t min_pct)
{
    for (int i = 0; i < 600; i++) {
        run_ms(100u, hold, &s_clock);
        if (mock_sm_get_power_level() >= min_pct && i > 15) {
            return true;
        }
    }
    return false;
}

static void test_bus_sense_dead_while_heating_latches_current_sense(void)
{
    start(STATE_HEATING, 200.0f, 10u, 150.0f);
    s_hold_t = 150.0f;
    TEST_ASSERT_TRUE(heat_until_power(20u));   /* pulse passed, loop at >= 360 W */
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    s_i_force = 0.0f;
    uint32_t elapsed = 0u;
    while (state_machine_get_state() == STATE_HEATING && elapsed < 5000u) {
        run_ms(10u, hold, &s_clock);
        elapsed += 10u;
    }
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_CURRENT_SENSE, state_machine_get_fault());
    TEST_ASSERT_EQUAL_INT(1, pan_control_current_sense_latch());
    TEST_ASSERT_TRUE(elapsed <= 700u);
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
}

static void test_dead_sense_fails_the_start_up_pulse(void)
{
    start(STATE_PREHEAT, 200.0f, 10u, 25.0f);
    s_i_force = 0.0f;
    s_hold_t = 25.0f;
    run_ms(2000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_CURRENT_SENSE, state_machine_get_fault());
    TEST_ASSERT_EQUAL_INT(2, pan_control_current_sense_latch());
}

static void test_low_power_hold_with_no_current_does_not_latch(void)
{
    /* Intensity 1 (180 W) never reaches the 300 W floor of check (a): a stage
     * bursting below its floor reads 0 A between bursts. The pulse (180 W)
     * still sees current. */
    start(STATE_HEATING, 200.0f, 1u, 150.0f);
    s_hold_t = 150.0f;
    run_ms(3000u, hold, &s_clock);
    s_i_force = 0.0f;
    run_ms(20000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}



/* ---- cold-soak check (DECISIONS.md D-SOAK) --------------------------------
 * The unit idles with the heatsink NTC VALID at 35 degC (the stub's reading),
 * the rim saturated (40 degC glass), then PREHEAT starts. */

static uint32_t s_soak_max_power;

static void soak_idle(float pt_c, float hs_c, uint32_t idle_ms)
{
    start(STATE_IDLE, 200.0f, 10u, pt_c);
    mock_sm_set_heatsink_temperature(hs_c);
    s_hold_t = pt_c;
    run_ms(idle_ms, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_IDLE, state_machine_get_state());
}

static void soak_preheat(uint32_t ms)
{
    s_soak_max_power = 0u;
    state_machine_force_state(STATE_PREHEAT);
    for (uint32_t t = 0; t < ms; t += 10u) {
        run_ms(10u, hold, &s_clock);
        if (mock_sm_get_power_level() > s_soak_max_power) {
            s_soak_max_power = mock_sm_get_power_level();
        }
    }
}

static void test_cold_soak_leak_latches_before_any_power_and_holds(void)
{
    /* a leak reading 25 K low after 31 min idle (threshold 19.4 K) */
    soak_idle(10.0f, 35.0f, 31u * 60000u);
    soak_preheat(300u);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_LEAKAGE, state_machine_get_fault());
    TEST_ASSERT_TRUE(pan_control_cold_soak_latched());
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pan_control_cold_soak_result().verdict);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 25.0f, pan_control_cold_soak_result().gap_k);
    TEST_ASSERT_EQUAL_UINT32(0u, s_soak_max_power);           /* the coil never started */
    TEST_ASSERT_FALSE(fault_cleared());                       /* the leak persists */
    /* a cold item removed or thawed: the reading agrees again, reset allowed */
    s_hold_t = 33.0f;
    run_ms(100u, hold, &s_clock);
    TEST_ASSERT_TRUE(fault_cleared());
}

static void test_cold_soak_skips_before_30_min_and_heats(void)
{
    soak_idle(15.0f, 35.0f, 20u * 60000u);
    soak_preheat(1500u);
    TEST_ASSERT_EQUAL_INT(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_NOT_SOAKED, pan_control_cold_soak_result().verdict);
    TEST_ASSERT_TRUE(s_soak_max_power > 0u);
}

static void test_cold_soak_passes_when_the_readings_agree(void)
{
    soak_idle(33.0f, 35.0f, 31u * 60000u);
    soak_preheat(1500u);
    TEST_ASSERT_EQUAL_INT(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(PCS_PASS, pan_control_cold_soak_result().verdict);
    TEST_ASSERT_TRUE(s_soak_max_power > 0u);
}

static void test_cold_soak_skips_with_the_heatsink_saturated_or_the_rim_warm(void)
{
    start(STATE_IDLE, 200.0f, 10u, 15.0f);
    mock_sm_set_heatsink_ntc_state(HS_NTC_SATURATED);   /* above range, or an open sensor */
    s_hold_t = 15.0f;
    run_ms(31u * 60000u, hold, &s_clock);
    soak_preheat(300u);
    TEST_ASSERT_EQUAL_INT(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HS_INVALID, pan_control_cold_soak_result().verdict);
    soak_idle(15.0f, 35.0f, 31u * 60000u);
    s_rim = 150.0f;                                       /* glass still hot */
    soak_preheat(300u);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_RIM_WARM, pan_control_cold_soak_result().verdict);
    TEST_ASSERT_TRUE(state_machine_get_state() != STATE_FAULT);
}

static float s_cold_pan_at;
static float cold_pan(uint32_t t_ms)
{
    return (float)t_ms < s_cold_pan_at ? 34.0f : 5.0f;
}

static void test_cold_soak_skips_a_cold_pan_placed_in_the_window(void)
{
    start(STATE_IDLE, 200.0f, 10u, 34.0f);
    mock_sm_set_heatsink_temperature(35.0f);
    s_cold_pan_at = (float)(s_clock + 26u * 60000u);
    run_ms(31u * 60000u, cold_pan, &s_clock);
    s_hold_t = 5.0f;
    soak_preheat(300u);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_PT_DRIFT, pan_control_cold_soak_result().verdict);
    TEST_ASSERT_TRUE(state_machine_get_state() != STATE_FAULT);
}

static void test_a_rim_limit_leak_latch_is_not_cleared_by_agreement(void)
{
    /* D-RIMLIM: the rim far above the envelope of a 100 degC reading */
    start(STATE_HEATING, 100.0f, 10u, 100.0f);
    s_hold_t = 100.0f;
    s_rim = 160.0f;
    run_ms(60000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_LEAKAGE, state_machine_get_fault());
    TEST_ASSERT_TRUE(pan_control_rim_limit_latched());
    TEST_ASSERT_FALSE(pan_control_cold_soak_latched());
    mock_sm_set_heatsink_temperature(35.0f);
    s_hold_t = 34.0f;
    s_rim = 40.0f;
    run_ms(100u, hold, &s_clock);
    TEST_ASSERT_FALSE(fault_cleared());
}

/* ---- coil-off token across a power cycle (DECISIONS.md D-SOAKNV) ---------- */
extern void mock_soak_nvs_put(uint32_t v);
extern bool mock_soak_nvs_get(uint32_t *v);
extern void mock_soak_nvs_fail(bool load, bool save, bool clear);
extern uint32_t mock_soak_nvs_saves(void);

/* A power cycle: a fresh boot whose flash holds `token` (0: none). */
static void boot_idle_with_token(uint32_t token, float pt_c, float hs_c)
{
    start(STATE_IDLE, 200.0f, 10u, pt_c);   /* mock_sm_reset: an erased flash */
    if (token != 0u) {
        mock_soak_nvs_put(token);
    }
    state_machine_init();                   /* the boot reads the flash */
    state_machine_force_state(STATE_IDLE);
    mock_sm_set_heatsink_temperature(hs_c);
    s_hold_t = pt_c;
}

static void test_cold_soak_token_survives_a_power_cycle_and_is_revoked_before_power(void)
{
    /* 16 min idle after power-up: the token is written once, at 15 min */
    soak_idle(10.0f, 35.0f, 16u * 60000u);
    uint32_t tok = 0u;
    TEST_ASSERT_TRUE(mock_soak_nvs_get(&tok));
    TEST_ASSERT_EQUAL_UINT32(PSS_TOKEN_OFF_S, tok);
    TEST_ASSERT_EQUAL_UINT32(1u, mock_soak_nvs_saves());
    /* power cycle; 16 min of uptime: off >= 900 + 960 s, history complete */
    boot_idle_with_token(tok, 10.0f, 35.0f);
    TEST_ASSERT_EQUAL_UINT32(PSS_TOKEN_OFF_S, pan_control_soak_store()->boot_credit_s);
    run_ms(16u * 60000u, hold, &s_clock);
    soak_preheat(300u);
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_LEAKAGE, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(0u, s_soak_max_power);
    TEST_ASSERT_TRUE(pan_control_cold_soak_result().off_s >= 1800.0f);
    /* the PREHEAT entry revoked the token before any power */
    TEST_ASSERT_FALSE(mock_soak_nvs_get(&tok));
    /* the same unit without the token: not soaked at 16 min of uptime */
    boot_idle_with_token(0u, 10.0f, 35.0f);
    run_ms(16u * 60000u, hold, &s_clock);
    soak_preheat(300u);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_NOT_SOAKED, pan_control_cold_soak_result().verdict);
    TEST_ASSERT_TRUE(s_soak_max_power > 0u);
    TEST_ASSERT_FALSE(mock_soak_nvs_get(&tok));   /* the 15 min write was revoked by this cook */
}

static void test_cold_soak_store_failure_does_not_block_heating(void)
{
    boot_idle_with_token(PSS_TOKEN_OFF_S, 33.0f, 35.0f);
    mock_soak_nvs_fail(false, false, true);   /* the erase fails */
    run_ms(16u * 60000u, hold, &s_clock);
    soak_preheat(1500u);
    TEST_ASSERT_EQUAL_INT(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_TRUE(s_soak_max_power > 0u);
    TEST_ASSERT_TRUE(pan_control_soak_store()->disabled);
    TEST_ASSERT_TRUE(pan_control_soak_store()->failures >= 1u);
    mock_soak_nvs_fail(false, false, false);
}

void run_c1_runtime_tests(void)
{
    RUN_TEST(test_no_conversion_is_a_probe_fault_not_runaway);
    RUN_TEST(test_stage_floor_power_is_not_disobedience);
    RUN_TEST(test_invalid_stage_power_while_heating_latches_current_sense);
    RUN_TEST(test_pan_refusal_while_heating_stops_without_a_fault);
    RUN_TEST(test_pan_refusal_in_preheat_stops_without_a_fault);
    RUN_TEST(test_thermal_cap_limits_the_loop);
    RUN_TEST(test_thermal_cap_does_not_wind_up_the_loop);
    RUN_TEST(test_residual_power_limit_while_off_is_50_w);
    RUN_TEST(test_reset_refused_while_the_rtd_service_is_stopped);
    RUN_TEST(test_sustained_rise_latches_runaway);
    RUN_TEST(test_hot_pan_placed_in_idle_does_not_latch_runaway);
    RUN_TEST(test_absolute_300_still_latches_runaway);
    RUN_TEST(test_preheat_heats_and_hands_over_on_the_estimate);
    RUN_TEST(test_intensity_limits_the_loop_power);
    RUN_TEST(test_reading_over_target_plus_10_holds_power_off_without_latching);
    RUN_TEST(test_lowered_target_does_not_latch);
    RUN_TEST(test_power_stage_drawing_current_with_power_off_latches_thermal_runaway);
    RUN_TEST(test_still_rising_with_power_off_latches_thermal_runaway);
    RUN_TEST(test_rtd_resistance_interlock_uses_the_c1_window);
    RUN_TEST(test_bus_sense_dead_while_heating_latches_current_sense);
    RUN_TEST(test_dead_sense_fails_the_start_up_pulse);
    RUN_TEST(test_low_power_hold_with_no_current_does_not_latch);
    RUN_TEST(test_leaving_heating_stops_the_loop);
    RUN_TEST(test_rim_cross_check_fires_on_a_low_flat_pt100);
    RUN_TEST(test_rim_cross_check_ignores_a_cold_food_quench);
    RUN_TEST(test_saturated_rim_never_cross_checks);
    RUN_TEST(test_rim_short_latches_probe_short_and_cuts_power);
    RUN_TEST(test_rim_open_latches_probe_open_after_600s_hot);
    RUN_TEST(test_rim_adc_failure_latches_probe_open);
    RUN_TEST(test_cold_soak_leak_latches_before_any_power_and_holds);
    RUN_TEST(test_cold_soak_skips_before_30_min_and_heats);
    RUN_TEST(test_cold_soak_passes_when_the_readings_agree);
    RUN_TEST(test_cold_soak_skips_with_the_heatsink_saturated_or_the_rim_warm);
    RUN_TEST(test_cold_soak_skips_a_cold_pan_placed_in_the_window);
    RUN_TEST(test_cold_soak_token_survives_a_power_cycle_and_is_revoked_before_power);
    RUN_TEST(test_cold_soak_store_failure_does_not_block_heating);
    RUN_TEST(test_a_rim_limit_leak_latch_is_not_cleared_by_agreement);
}
