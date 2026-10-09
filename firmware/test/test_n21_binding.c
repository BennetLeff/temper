/* Native-21 binding: pure signal layer and the binding driven through power_service with a fake
 * HAL. Assertions are the oracle (built with -UNDEBUG). */
#include "n21_binding.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned tests;
#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))

/* ============================================================ fake HAL */
typedef struct {
    uint64_t now;
    bool pads_live, gate, has_gate, permit, bus_fault, rail_ok, sup_run_ok;
    bool status_fail, adc_fail, ext_fail, program_fail, outputs_fail, capture_skew;
    bool line_present, ct_zc_fail, acquiring;
    float vbus_peak, tank_rms_on, lag_deg, ct_mon_extra_a, vbus_force_mv, ref_v3v3;
    uint16_t ref_code_force;
    bridge_cycle_t programmed;
    unsigned resets, programs, outputs_on, outputs_off, gate_on_calls;
    uint64_t next_zero, ct_zc_age;
    int pending; /* 0: next edge rise, 1: next edge fall */
} fake_t;
static fake_t F;
static n21_binding_t B;

static uint64_t f_now(void *c) { (void)c; return F.now; }
static bool f_program(void *c, const bridge_cycle_t *k) { (void)c; F.programs++; F.programmed = *k; return !F.program_fail; }
static bool f_outputs(void *c, bool live)
{
    (void)c;
    if (live) { F.outputs_on++; if (F.outputs_fail) return false; F.pads_live = true; }
    else { F.outputs_off++; F.pads_live = false; } /* low even if reporting failure */
    return !F.outputs_fail;
}
static bool f_gate(void *c, bool on) { (void)c; if (on) F.gate_on_calls++; F.gate = on; return true; }
static bool f_capture(void *c, n21_pwm_capture_t *cap)
{
    (void)c;
    cap->t_us = F.now;
    for (unsigned n = 0; n < 4; n++) {
        cap->out[n] = (n21_edge_t){F.programmed.pulse[n].rise, F.programmed.pulse[n].width,
                                   F.programmed.period, F.pads_live};
        if (F.capture_skew && n == 1) cap->out[n].rise += 10; /* LA late: overlap shrinks */
    }
    return F.pads_live;
}
static bool f_status(void *c, n21_status_rb_t *s)
{
    (void)c;
    *s = (n21_status_rb_t){F.permit, F.bus_fault, F.rail_ok, F.sup_run_ok};
    return !F.status_fail;
}
static bool f_reset(void *c)
{
    (void)c;
    F.resets++;
    /* The latch grants PERMIT only with every source healthy. */
    if (!F.bus_fault && F.rail_ok && F.sup_run_ok) F.permit = true;
    return true;
}
static float bus_at(uint64_t t)
{
    return F.vbus_peak * fabsf(sinf(6.28318530718f * 60.0f * (float)t * 1e-6f));
}
static bool running(void) { return F.pads_live && F.gate; }
static bool f_adc1(void *c, float *vbus_mv, float *ct_mv)
{
    (void)c;
    *vbus_mv = F.vbus_force_mv != 0 ? F.vbus_force_mv
                                    : (N21_VBUS_BIAS_V + N21_VBUS_V_PER_V * bus_at(F.now)) * 1e3f;
    *ct_mv = 1650.0f + F.ct_mon_extra_a * 15.0f;
    return !F.adc_fail;
}
static bool f_ext(void *c, unsigned ch, uint16_t *code)
{
    (void)c;
    uint16_t ref = F.ref_code_force ? F.ref_code_force : (uint16_t)lroundf(2.5f * 4096.0f / F.ref_v3v3);
    if (ch == N21_MCP3202_CH_REF) *code = ref;
    else {
        float rms = running() ? F.tank_rms_on * fabsf(sinf(6.28318530718f * 60.0f * (float)F.now * 1e-6f)) : 0;
        float codes = rms * N21_RMS_V_PER_A * ref / 2.5f;
        *code = codes > 4095 ? 4095 : (uint16_t)lroundf(codes);
    }
    return !F.ext_fail;
}
static bool f_ct_zc(void *c, uint32_t *zc, uint64_t *t)
{
    (void)c;
    uint32_t p = F.programmed.period;
    int32_t ticks = (int32_t)lroundf(F.lag_deg / 360.0f * (float)p) + 8; /* + vsw delay 100 ns */
    *zc = (uint32_t)((ticks % (int32_t)p + (int32_t)p) % (int32_t)p);
    *t = F.now - F.ct_zc_age;
    return !F.ct_zc_fail;
}
static size_t f_edges(void *c, uint64_t *t, bool *lv, size_t max)
{
    (void)c;
    size_t n = 0;
    while (F.line_present && n < max) {
        uint64_t e = F.pending == 0 ? F.next_zero - 1000 : F.next_zero + 1000;
        if (e > F.now) break;
        t[n] = e;
        lv[n] = F.pending == 0;
        n++;
        if (F.pending == 1) F.next_zero += 8333;
        F.pending ^= 1;
    }
    if (!F.line_present) while (F.next_zero + 1000 <= F.now) F.next_zero += 8333;
    return n;
}
static const n21_hw_ops_t OPS = {f_now, NULL, NULL, f_program, f_outputs, f_capture, f_gate,
                                 f_status, f_reset, f_adc1, f_ext, f_ct_zc, f_edges, NULL};

static void fake_reset(bool with_gate)
{
    memset(&F, 0, sizeof F);
    F.now = 1000000;
    F.next_zero = 1003000;
    F.has_gate = with_gate;
    F.permit = true;
    F.rail_ok = F.sup_run_ok = true;
    F.line_present = true;
    F.acquiring = true;
    F.vbus_peak = 170.0f;
    F.tank_rms_on = 20.0f;  /* RMS envelope peak; well inside the 22 A ceiling on average */
    F.lag_deg = 30.0f;
    F.ref_v3v3 = 3.30f;
}
static n21_hw_ops_t ops(void)
{
    n21_hw_ops_t o = OPS;
    if (!F.has_gate) o.run_gate = NULL;
    return o;
}
static n21_config_t commissioned_cfg(void)
{
    n21_config_t c = n21_config_default();
    c.mode = N21_MODE_COMMISSIONED;
    c.calibrated = true;
    c.frequency_hz = 50000;
    return c;
}
/* Advance simulated time; acquisition every 625 us, control tick every 10 ms. Returns false if the
 * power service trips (observed as test_pwm_generation going false after having been true). */
static void run_ms(unsigned ms)
{
    for (unsigned k = 0; k < ms * 8; k++) {   /* 125 us steps */
        F.now += 125;
        if (F.acquiring && F.now % 625 == 0) n21_acquire_step(&B);
        if (F.now % 10000 == 0) power_service_tick();
    }
}
static bool bind_commissioned(n21_config_t c)
{
    power_service_bootstrap();
    power_binding_t pb;
    n21_hw_ops_t o = ops();
    if (n21_binding_init(&B, &c, &o, &pb) != N21_INIT_BIND) return false;
    return power_service_bind(&pb);
}
static bool inhibited(void) { return !F.pads_live && !F.gate; }

/* ============================================================ pure signal tests */
static void test_scaling(void)
{
    n21_analog_cal_t cal = {0};
    float v;
    /* controller_calcs d11_receiver adc_V_at_bus: 0 / 170 / 198 V */
    assert(n21_vbus_from_mv(&cal, 247.77f, &v) == N21_SIG_OK && NEAR(v, 0, 0.05));
    assert(n21_vbus_from_mv(&cal, 956.178f, &v) == N21_SIG_OK && NEAR(v, 170, 0.05));
    assert(n21_vbus_from_mv(&cal, 1072.857f, &v) == N21_SIG_OK && NEAR(v, 198, 0.05));
    assert(NEAR(1.0 / N21_VBUS_V_PER_V, 239.97, 0.05));   /* 240 V per ADC volt */
    assert(n21_vbus_from_mv(&cal, 99.0f, &v) == N21_SIG_INVALID);      /* D-11 < 100 mV */
    assert(n21_vbus_from_mv(&cal, 1210.0f, &v) == N21_SIG_OVERRANGE);  /* 231 V latch */
    assert(n21_vbus_from_mv(&cal, NAN, &v) == N21_SIG_INVALID);
    n21_analog_cal_t trim = {.vbus_offset_mv = -2.2f, .vbus_gain_trim = 1.01f};
    assert(n21_vbus_from_mv(&trim, 245.57f, &v) == N21_SIG_OK && NEAR(v, 0, 0.05));
    assert(n21_vbus_from_mv(&trim, 954.0f, &v) == N21_SIG_OK && NEAR(v, 171.7, 0.1));
    /* CT_MON: 1.65 V + 15 mV/A; 55 A -> 2.475 V (controller_calcs ct_mon range) */
    assert(n21_ct_mon_from_mv(&cal, 2475.0f, &v) == N21_SIG_OK && NEAR(v, 55, 0.01));
    assert(n21_ct_mon_from_mv(&cal, 825.0f, &v) == N21_SIG_OK && NEAR(v, -55, 0.01));
    assert(n21_ct_mon_from_mv(&cal, 10.0f, &v) == N21_SIG_INVALID);    /* J4 unplugged */
    assert(n21_ct_mon_from_mv(&cal, 2890.0f, &v) == N21_SIG_OVERRANGE);
    n21_analog_cal_t z = {.ct_mon_zero_mv = 1640.0f};
    assert(n21_ct_mon_from_mv(&z, 1640.0f, &v) == N21_SIG_OK && NEAR(v, 0, 1e-4));
    /* Tank RMS: 22 A -> 1.32 V (rms_channel adc_V_at_22A_rms), ratiometric against the LM4040 */
    float a, v3;
    for (float vdd = 3.25f; vdd <= 3.36f; vdd += 0.05f) {
        uint16_t ref = (uint16_t)lroundf(2.5f * 4096 / vdd), rms = (uint16_t)lroundf(1.32f * 4096 / vdd);
        assert(n21_tank_rms_from_codes(&cal, rms, ref, &a, &v3) == N21_SIG_OK);
        assert(NEAR(a, 22.0, 0.03) && NEAR(v3, vdd, 0.002));
    }
    assert(n21_tank_rms_from_codes(&cal, 1600, 2950, &a, NULL) == N21_SIG_INVALID); /* v3v3 > 3.465 */
    assert(n21_tank_rms_from_codes(&cal, 1600, 3270, &a, NULL) == N21_SIG_INVALID); /* v3v3 < 3.135 */
    assert(n21_tank_rms_from_codes(&cal, 1600, 0, &a, NULL) == N21_SIG_INVALID);
    assert(n21_tank_rms_from_codes(&cal, 4095, 3103, &a, NULL) == N21_SIG_OVERRANGE);
    n21_analog_cal_t g = {.rms_gain_trim = 0.98f};
    assert(n21_tank_rms_from_codes(&g, 1638, 3103, &a, NULL) == N21_SIG_OK && NEAR(a, 0.98 * 2.5 * 1638 / 3103 / 0.06, 1e-3));
    /* Line from the bus peak */
    assert(NEAR(n21_line_rms_from_bus_peak(169.7f, 0), 120.0, 0.02));
    assert(NEAR(n21_line_rms_from_bus_peak(168.0f, 1.7f), 120.0, 0.02));
    assert(isnan(n21_line_rms_from_bus_peak(170, -1)));
    tests++;
}

static void test_mcp3202(void)
{
    uint8_t tx[3], rx[3];
    uint16_t code;
    n21_mcp3202_frame(0, tx);
    assert(tx[0] == 0x01 && tx[1] == 0xA0 && tx[2] == 0x00);
    n21_mcp3202_frame(1, tx);
    assert(tx[0] == 0x01 && tx[1] == 0xE0);
    rx[0] = 0xFF; rx[1] = 0xE0 | 0x0A; rx[2] = 0xBC;     /* high-Z bits set, null bit 0 */
    assert(n21_mcp3202_decode(rx, &code) && code == 0xABC);
    rx[1] = 0xFF; rx[2] = 0xFF;                           /* nothing driving DOUT */
    assert(!n21_mcp3202_decode(rx, &code));
    tests++;
}

static void test_cos_phi(void)
{
    n21_phase_cfg_t c = {.period_ticks = 1600, .vsw_delay_ticks = 8, .ct_zc_delay_ticks = 4,
                         .ct_zc_inverted = false, .min_lag_rad = 5 * 0.0174532925f};
    float cp, phi;
    /* 30 degrees of lag = 133.3 ticks after the switch-node transition */
    assert(n21_cos_phi(&c, 133 + 12, &cp, &phi) && NEAR(cp, cosf(133.0f / 1600 * 6.2831853f), 1e-5));
    assert(NEAR(phi * 57.29578f, 29.925, 0.01));
    assert(n21_cos_phi(&c, 400 + 12, &cp, &phi) && NEAR(cp, 0, 1e-5));     /* 90 deg */
    assert(n21_cos_phi(&c, 600 + 12, &cp, &phi) && cp < 0);                /* regenerating */
    assert(!n21_cos_phi(&c, 12, &cp, &phi) && NEAR(phi, 0, 1e-6));         /* 0 lag < 5 deg min */
    assert(!n21_cos_phi(&c, 1600 - 50 + 12 - 1600 + 1600, &cp, &phi) && phi < 0); /* current leads */
    assert(!n21_cos_phi(&c, 1600, &cp, &phi));                              /* out of range */
    c.ct_zc_inverted = true;                       /* polarity reversed: edge half a period off */
    assert(n21_cos_phi(&c, (133 + 12 + 800) % 1600, &cp, &phi) && NEAR(phi * 57.29578f, 29.925, 0.01));
    c.ct_zc_inverted = false;
    c.vsw_delay_ticks = 1580;                      /* wrap through zero */
    assert(n21_cos_phi(&c, (133 + 1584) % 1600, &cp, &phi) && NEAR(phi * 57.29578f, 29.925, 0.01));
    tests++;
}

static void fill_half(n21_half_t *h, uint64_t zero, unsigned n, float vpk, float ipk, float cp)
{
    n21_half_begin(h, zero);
    for (unsigned j = 0; j < n; j++) {
        float x = fabsf(sinf(3.14159265f * (j + 0.5f) / n));
        input_sample_t s = {vpk * x, ipk * x, cp};
        n21_half_add(h, zero + (uint64_t)((j + 0.5) * 8333.0 / n), &s);
    }
}

static void test_half_cycle(void)
{
    input_limits_cfg_t lim = input_limits_native21();
    n21_half_t h;
    n21_half_result_t r;
    fill_half(&h, 1000, 13, 170, 30, 0.9f);
    assert(n21_half_close(&h, &lim, 1000 + 8333, 1500, 0, &r));
    /* Same as calling input_limits directly with the line taken from the sampled peak. */
    input_estimate_t e;
    assert(input_limits_half_cycle(&lim, h.s, 13, h.bus_peak_v * 0.70710678f, &e));
    assert(NEAR(r.est.inlet_bound_a, e.inlet_bound_a, 1e-5) && NEAR(r.line_rms_v, 120.2, 0.1));
    assert(r.end_us == 9333 && !h.open);
    /* Peak sampling under-reads the line: conservative (higher current). */
    assert(r.line_rms_v <= 170 * 0.7072f);
    assert(!n21_half_close(&h, &lim, 9333, 1500, 0, &r));              /* already closed */
    fill_half(&h, 1000, 7, 170, 30, 0.9f);
    assert(!n21_half_close(&h, &lim, 9333, 1500, 0, &r));              /* < 8 samples */
    fill_half(&h, 1000, 13, 170, 30, 0.9f);
    assert(!n21_half_close(&h, &lim, 1000 + 9000, 1500, 0, &r));       /* half too long */
    fill_half(&h, 1000, 13, 170, 30, 0.9f);
    assert(!n21_half_close(&h, &lim, 1000 + 8333, 500, 0, &r));        /* gaps > 500 us */
    /* A gap in the middle (acquisition stalled) */
    n21_half_begin(&h, 1000);
    for (unsigned j = 0; j < 13; j++) {
        if (j == 6 || j == 7 || j == 8) continue;
        input_sample_t s = {160, 10, 0.9f};
        n21_half_add(&h, 1000 + 300 + j * 620, &s);
    }
    assert(!n21_half_close(&h, &lim, 1000 + 8333, 1500, 0, &r));
    /* Out-of-order or overflow breaks the half */
    fill_half(&h, 1000, 13, 170, 30, 0.9f);
    input_sample_t s = {160, 10, 0.9f};
    n21_half_add(&h, 1500, &s);
    assert(h.broken && !n21_half_close(&h, &lim, 9333, 1500, 0, &r));
    n21_half_begin(&h, 0);
    for (unsigned j = 0; j <= N21_HALF_MAX_SAMPLES; j++) n21_half_add(&h, j * 100, &s);
    assert(h.broken);
    /* A bad sample value fails input_limits */
    fill_half(&h, 1000, 13, 170, 30, 0.9f);
    h.s[3].cos_phi = 2;
    assert(!n21_half_close(&h, &lim, 9333, 1500, 0, &r));
    /* Low line from the peak: < 100 V refused */
    fill_half(&h, 1000, 13, 135, 10, 0.9f);
    assert(!n21_half_close(&h, &lim, 9333, 1500, 0, &r));

    /* Line aggregation: worst case of the halves since the last report */
    n21_line_agg_t ag = {0};
    float lv, ia, bw;
    assert(!n21_line_report(&ag, 1800, 300, &lv, &ia, &bw));            /* nothing yet */
    n21_half_result_t r1 = {.end_us = 10, .line_rms_v = 121, .est = {.inlet_bound_a = 9, .tank_ceiling_w = 2000, .tank_rms_a = 15}};
    n21_half_result_t r2 = {.end_us = 20, .line_rms_v = 118, .est = {.inlet_bound_a = 11, .tank_ceiling_w = 1500, .tank_rms_a = 18}};
    n21_line_agg_add(&ag, &r1);
    n21_line_agg_add(&ag, &r2);
    assert(n21_line_report(&ag, 1800, 300, &lv, &ia, &bw));
    assert(lv == 118 && ia == 11 && bw == 1500 && ag.last_end_us == 20 && ag.halves == 2);
    assert(n21_line_report(&ag, 1200, 300, &lv, &ia, &bw) && bw == 1200);  /* pan model lower */
    n21_line_agg_t idle = {0};
    n21_half_result_t r3 = {.end_us = 5, .line_rms_v = 120, .est = {.inlet_bound_a = 1.3f, .tank_ceiling_w = INFINITY}};
    n21_line_agg_add(&idle, &r3);
    assert(n21_line_report(&idle, 1800, 300, &lv, &ia, &bw) && bw == 300 && isfinite(bw));
    assert(!n21_line_report(&idle, NAN, 300, &lv, &ia, &bw));
    tests++;
}

static bool ab_ok(void *c, const bridge_cycle_t *k) { (void)c; (void)k; return true; }
static bool ab_req(void *c, bool r) { (void)c; (void)r; return true; }
static void ab_inh(void *c) { (void)c; }
/* fullbridge_apply's own verdict on a feedback record (fresh adapter, one line record). */
static bool adapter_accepts(const bridge_feedback_t *f)
{
    fullbridge_adapter_t a;
    bridge_config_t cfg = {.timer_hz = 80000000, .frequency_hz = 50000, .input_deadtime_ns = 200,
                           .capture_age_us = 1000, .max_power_w = 1800, .inlet_target_a = 13.5f,
                           .commissioned = true};
    bridge_backend_t be = {ab_ok, ab_req, ab_inh, NULL};
    assert(fullbridge_init(&a, &cfg, &be));
    assert(fullbridge_line_cycle(&a, f->sampled_us, 120, 5, 1000));
    return fullbridge_apply(&a, f->sampled_us, f, 1.0f);
}

static void test_feedback(void)
{
    bridge_cycle_t c;
    assert(bridge_plan_cycle(80000000, 50000, 200, 1.0f, &c) && c.period == 1600 && c.dead_ticks == 16);
    n21_pwm_capture_t cap = {.t_us = 1234};
    for (unsigned n = 0; n < 4; n++) cap.out[n] = (n21_edge_t){c.pulse[n].rise, c.pulse[n].width, c.period, true};
    n21_status_rb_t s = {.permit = true, .bus_fault = false, .rail_ok = true, .sup_run_ok = true};
    bridge_feedback_t f;
    n21_feedback_from_capture(&cap, &s, 7, &f);
    assert(f.sampled_us == 1234 && f.serial == 7 && f.interlock_ok && f.rails_ok && !f.bus_fault);
    for (unsigned n = 0; n < 4; n++) assert(f.valid[n] && f.nonoverlap_ticks[n] == 16);
    assert(n21_capture_matches(&c, &f));
    /* Same verdict as the adapter itself on the same feedback. */
    assert(adapter_accepts(&f));
    /* Overlap: LA rises 10 ticks early -> non-overlap 6 < 16 */
    cap.out[1].rise -= 10;
    n21_feedback_from_capture(&cap, &s, 8, &f);
    assert(f.nonoverlap_ticks[1] == 6 && !n21_capture_matches(&c, &f) && !adapter_accepts(&f));
    cap.out[1].rise += 10;
    cap.out[2].valid = false;                       /* a missing output invalidates it and its pair */
    n21_feedback_from_capture(&cap, &s, 9, &f);
    assert(!f.valid[2] && !f.valid[3] && f.valid[0] && !n21_capture_matches(&c, &f) && !adapter_accepts(&f));
    cap.out[2].valid = true;
    cap.out[0].high += 3;
    n21_feedback_from_capture(&cap, &s, 10, &f);
    assert(!n21_capture_matches(&c, &f) && !adapter_accepts(&f));
    cap.out[0].high -= 1;      /* +2 ticks on HA's width alone eats LA's non-overlap: both reject */
    n21_feedback_from_capture(&cap, &s, 12, &f);
    assert(f.nonoverlap_ticks[1] == 14 && !n21_capture_matches(&c, &f) && !adapter_accepts(&f));
    cap.out[0].high -= 2;
    cap.out[1].rise += 2;      /* LA 2 ticks late, 2 ticks short: inside both windows */
    cap.out[1].high -= 2;
    n21_feedback_from_capture(&cap, &s, 13, &f);
    assert(n21_capture_matches(&c, &f) && adapter_accepts(&f));
    s.bus_fault = true;
    n21_feedback_from_capture(&cap, &s, 11, &f);
    assert(f.bus_fault);
    tests++;
}

/* ============================================================ binding tests */
static void test_default_is_inhibited(void)
{
    fake_reset(true);
    n21_config_t c = n21_config_default();
    assert(c.mode == N21_MODE_INHIBITED && !c.calibrated && c.frequency_hz == 0);
    power_binding_t pb;
    n21_hw_ops_t o = ops();
    F.pads_live = true; F.gate = true;              /* whatever state the pins were in */
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_INHIBITED);
    assert(inhibited() && !pb.config.commissioned && pb.sample == NULL);
    assert(!n21_bench_start(&B, 100, true));        /* no bench in INHIBITED */
    /* Acquisition still runs for telemetry, without touching the pads. */
    for (int k = 0; k < 200; k++) { F.now += 625; n21_acquire_step(&B); }
    n21_telemetry_t t;
    n21_telemetry(&B, &t);
    assert(t.zc_locked && t.halves_ok > 5 && NEAR(t.last_half.line_rms_v, 120, 1.5) && inhibited());

    c = commissioned_cfg();
    c.calibrated = false;
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_NOT_CALIBRATED && !pb.config.commissioned);
    fake_reset(false);                              /* controller as captured: no run gate */
    o = ops();
    c = commissioned_cfg();
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_NO_RUN_GATE && !pb.config.commissioned && inhibited());
    fake_reset(true);
    o = ops();
    c.frequency_hz = 0;
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_ERROR);
    c = commissioned_cfg();
    c.tank_peak_trip_a = 60;                        /* above the hardware band: refused */
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_ERROR);
    c = commissioned_cfg();
    c.acq_period_us = 1000;                         /* < 8 samples per half cycle */
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_ERROR);
    c = commissioned_cfg();
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_BIND && pb.config.commissioned);
    assert(pb.config.input_deadtime_ns == 200 && pb.config.timer_hz == 80000000 && !pb.burst.burst_enabled);
    assert(F.programs == 1 && F.programmed.period == 1600 && F.programmed.dead_ticks == 16);
    tests++;
}

static void test_runs_and_reports(void)
{
    fake_reset(true);
    assert(bind_commissioned(commissioned_cfg()));
    assert(inhibited());
    run_ms(100);
    /* Armed: pads qualified, gate still low (no power requested). */
    assert(F.pads_live && !F.gate && test_pwm_generation());
    power_set_level(50);
    run_ms(200);
    assert(F.gate && F.pads_live && test_pwm_generation());
    n21_telemetry_t t;
    n21_telemetry(&B, &t);
    assert(t.armed_line && t.fault == N21_FAULT_NONE && t.have_half);
    /* cos(phi) measured from CT_ZC: 30 degrees */
    assert(NEAR(t.last_half.est.tank_rms_a, 20 / sqrtf(2), 1.0));
    assert(t.last_half.est.inlet_bound_a > 1.3f && t.last_half.est.inlet_bound_a < 15);
    run_ms(1000);
    assert(test_pwm_generation() && F.gate);
    power_set_level(0);
    run_ms(50);
    assert(!F.gate && F.pads_live && test_pwm_generation());  /* stop without trip */
    assert(F.resets == 0);
    tests++;
}

typedef void (*inject_t)(void);
static void inj_bus_fault(void) { F.bus_fault = true; }
static void inj_rail(void) { F.rail_ok = false; }
static void inj_permit(void) { F.permit = false; }
static void inj_sup(void) { F.sup_run_ok = false; }
static void inj_status_fail(void) { F.status_fail = true; }
static void inj_vbus_over(void) { F.vbus_force_mv = 1215; }
static void inj_vbus_invalid(void) { F.vbus_force_mv = 50; }
static void inj_adc_fail(void) { F.adc_fail = true; }
static void inj_ct_peak(void) { F.ct_mon_extra_a = 47; }
static void inj_spi(void) { F.ext_fail = true; }
static void inj_ref(void) { F.ref_code_force = 2800; }
static void inj_tank_rms(void) { F.tank_rms_on = 26; F.lag_deg = 80; } /* > 23.1 A, low power */
static void inj_capacitive(void) { F.lag_deg = -10; }
static void inj_ct_zc_stale(void) { F.ct_zc_age = 5000; }
static void inj_ct_zc_fail(void) { F.ct_zc_fail = true; }
static void inj_line_lost(void) { F.line_present = false; }
static void inj_acq_stop(void) { F.acquiring = false; }
static void inj_skew(void) { F.capture_skew = true; }

static void test_any_fault_inhibits(void)
{
    /* want: the binding's latched reason, or NONE where the read-back/stale path (sample() false,
     * no latch) or the adapter itself is the expected stop. */
    static const struct { const char *name; inject_t f; n21_fault_t want; } cases[] = {
        {"bus_fault", inj_bus_fault, N21_FAULT_NONE}, {"rail_ok", inj_rail, N21_FAULT_NONE},
        {"permit", inj_permit, N21_FAULT_NONE}, {"sup_run_ok", inj_sup, N21_FAULT_NONE},
        {"status read", inj_status_fail, N21_FAULT_HW},
        {"vbus over-range", inj_vbus_over, N21_FAULT_VBUS_OVERRANGE},
        {"vbus invalid", inj_vbus_invalid, N21_FAULT_NONE}, {"adc1 read", inj_adc_fail, N21_FAULT_NONE},
        {"ct_mon peak", inj_ct_peak, N21_FAULT_TANK_PEAK}, {"mcp3202 spi", inj_spi, N21_FAULT_RMS_CHANNEL},
        {"lm4040 ref", inj_ref, N21_FAULT_RMS_CHANNEL},
        {"tank rms > 22 A envelope", inj_tank_rms, N21_FAULT_TANK_RMS},
        {"capacitive phase", inj_capacitive, N21_FAULT_PHASE},
        {"ct_zc stale", inj_ct_zc_stale, N21_FAULT_CT_ZC_STALE},
        {"ct_zc missing", inj_ct_zc_fail, N21_FAULT_CT_ZC_STALE},
        {"line_zc lost", inj_line_lost, N21_FAULT_NONE},
        {"acquisition stale", inj_acq_stop, N21_FAULT_NONE},
        {"pwm capture mismatch", inj_skew, N21_FAULT_NONE},
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        fake_reset(true);
        assert(bind_commissioned(commissioned_cfg()));
        power_set_level(60);
        run_ms(300);
        assert(F.gate && test_pwm_generation());
        cases[i].f();
        run_ms(60);
        if (!inhibited() || test_pwm_generation() || B.fault != cases[i].want) {
            printf("FAIL: %s: inhibited %d, fault %d (want %d)\n", cases[i].name, inhibited(),
                   (int)B.fault, (int)cases[i].want);
            assert(0);
        }
        /* Latched: restoring the input does not restart. */
        fake_t keep = F;
        fake_reset(true);
        F.now = keep.now; F.next_zero = keep.next_zero; F.pending = keep.pending;
        F.programmed = keep.programmed;
        power_set_level(60);
        run_ms(200);
        assert(inhibited() && !test_pwm_generation());
        assert(F.resets == 0 && keep.resets == 0);   /* never an automatic interlock reset */
    }
    tests++;
}

static void test_pre_arm_and_permit(void)
{
    /* PERMIT low at boot: the binding waits, pads stay low, nothing trips. */
    fake_reset(true);
    F.permit = false;
    assert(bind_commissioned(commissioned_cfg()));
    power_set_level(40);
    run_ms(300);
    assert(inhibited() && F.resets == 0 && F.outputs_on == 0);
    /* Refusals: no confirmation, a faulted source, rate limit. */
    assert(!n21_request_interlock_reset(&B, false) && F.resets == 0);
    F.bus_fault = true;
    assert(!n21_request_interlock_reset(&B, true) && F.resets == 0);
    F.bus_fault = false;
    assert(n21_request_interlock_reset(&B, true) && F.resets == 1 && F.permit);
    assert(!n21_request_interlock_reset(&B, true) && F.resets == 1);   /* already permitted */
    run_ms(300);
    assert(F.gate && F.pads_live && test_pwm_generation());
    /* Never while PWM is live or the gate is on. */
    F.permit = false;
    assert(!n21_request_interlock_reset(&B, true) && F.resets == 1);
    run_ms(50);
    assert(inhibited() && !test_pwm_generation() && F.resets == 1);
    /* The HAL table has no PERMIT output: the only interlock call is the reset request, and it is
     * only reachable through n21_request_interlock_reset (counted above). */
    tests++;
}

static void test_reset_rate_limit(void)
{
    fake_reset(true);
    F.permit = false;
    F.sup_run_ok = true;
    n21_config_t c = n21_config_default();
    n21_hw_ops_t o = ops();
    assert(n21_binding_init(&B, &c, &o, NULL) == N21_INIT_INHIBITED);
    F.rail_ok = false;                              /* the latch refuses: PERMIT stays low */
    assert(!n21_request_interlock_reset(&B, true) && F.resets == 0);
    F.rail_ok = true;
    F.bus_fault = false;
    /* A pulse that the latch does not honour (simulate another source faulted at the edge). */
    F.sup_run_ok = true;
    assert(n21_request_interlock_reset(&B, true) && F.resets == 1);
    F.permit = false;
    F.now += 500000;
    assert(!n21_request_interlock_reset(&B, true) && F.resets == 1);   /* < 1 s */
    F.now += 600000;
    assert(n21_request_interlock_reset(&B, true) && F.resets == 2);
    tests++;
}

static void test_bench_session(void)
{
    fake_reset(false);                              /* controller as captured */
    n21_config_t c = n21_config_default();
    c.mode = N21_MODE_BENCH;
    c.frequency_hz = 50000;
    n21_hw_ops_t o = ops();
    power_binding_t pb;
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_BENCH && !pb.config.commissioned && pb.sample == NULL);
    assert(inhibited());
    assert(!n21_bench_start(&B, 100, false));                       /* needs confirmation */
    assert(!n21_bench_start(&B, c.bench_max_ms + 1, true));          /* bounded */
    for (int k = 0; k < 4; k++) { F.now += 625; n21_acquire_step(&B); }
    assert(n21_bench_start(&B, 50, true) && F.pads_live);
    for (int k = 0; k < 40; k++) {
        F.now += 625;
        n21_acquire_step(&B);
        assert(n21_bench_poll(&B));
    }
    for (int k = 0; k < 60 && n21_bench_poll(&B); k++) { F.now += 625; n21_acquire_step(&B); }
    assert(inhibited() && !B.bench_active);                         /* timed out */
    /* Fault during a session stops it */
    assert(n21_bench_start(&B, 1000, true));
    F.capture_skew = true;
    F.now += 625; n21_acquire_step(&B);
    assert(!n21_bench_poll(&B) && inhibited() && B.fault == N21_FAULT_PWM);
    assert(!n21_bench_start(&B, 100, true));                        /* latched */
    /* Stale acquisition stops it */
    fake_reset(false);
    o = ops();
    assert(n21_binding_init(&B, &c, &o, NULL) == N21_INIT_BENCH);
    F.now += 625; n21_acquire_step(&B);
    assert(n21_bench_start(&B, 1000, true));
    F.now += 5000;
    assert(!n21_bench_poll(&B) && inhibited());
    /* Interlock inconsistent (PERMIT with BUS_FAULT): refused */
    F.bus_fault = true;
    assert(!n21_bench_start(&B, 100, true) && inhibited());
    /* BENCH never binds the adapter */
    assert(F.resets == 0);
    tests++;
}

static void test_hw_failures(void)
{
    fake_reset(true);
    F.outputs_fail = true;
    n21_config_t c = commissioned_cfg();
    n21_hw_ops_t o = ops();
    power_binding_t pb;
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_ERROR && inhibited());
    fake_reset(true);
    F.program_fail = true;
    o = ops();
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_ERROR && inhibited());
    /* Missing HAL entry */
    fake_reset(true);
    o = ops();
    o.read_ct_zc = NULL;
    assert(n21_binding_init(&B, &c, &o, &pb) == N21_INIT_ERROR && inhibited());
    tests++;
}

int main(void)
{
    test_scaling();
    test_mcp3202();
    test_cos_phi();
    test_half_cycle();
    test_feedback();
    test_default_is_inhibited();
    test_runs_and_reports();
    test_any_fault_inhibits();
    test_pre_arm_and_permit();
    test_reset_rate_limit();
    test_bench_session();
    test_hw_failures();
    printf("n21 binding: %u tests passed\n", tests);
    return 0;
}
