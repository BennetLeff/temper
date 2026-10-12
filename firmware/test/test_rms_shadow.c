/* Bench-only shadow tank RMS (rms_shadow.c): the pure computation, including the phase-lock case,
 * and the guarantee that the binding only copies it into telemetry. Evidence:
 * build-evidence/rms-estimator/README.md. */
#include "n21_binding.h"
#include "rms_shadow.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned tests;
#define TWO_PI 6.283185307179586
#define HALF_S (0.5 / 60.0)

/* The half-cycle RMS the shadow would compute (true value 22/sqrt2 A): a 22 A (envelope peak) carrier at f_hz under the
 * unsmoothed |sin| line envelope, CT_MON sampled in slots 1 and 3 of the 9-slot pattern at fs_hz,
 * pattern phase `off` seconds into the window, carrier phase `phi`. Returns percent error. */
static double shadow_error_pct(double f_hz, uint32_t fs_hz, double off, double phi)
{
    const double A = 22.0, tp = 9.0 / fs_hz, fs = fs_hz;
    rms_shadow_t s;
    rms_shadow_reset(&s);
    for (int p = -2; p < (int)(HALF_S / tp) + 3; p++)
        for (int q = 0; q < 2; q++) {
            double t = off + tp * p + (q ? 3.0 : 1.0) / fs;
            if (t < 0 || t >= HALF_S) continue;
            double a = A * 1.4142135623731 * fabs(sin(M_PI * t / HALF_S)) * sin(TWO_PI * f_hz * t + phi);
            rms_shadow_add_mv(&s, (float)(1650.0 + a * 15.0), 0.0f);
        }
    float rms;
    if (!rms_shadow_close(&s, &rms)) return NAN;
    return (rms / (A / 1.4142135623731) - 1.0) * 100.0;  /* half-cycle RMS of A|sin| */
}

static void worst_over_phase(double f_hz, uint32_t fs_hz, double *lo, double *hi)
{
    *lo = 1e9; *hi = -1e9;
    for (int i = 0; i < 12; i++)
        for (int j = 0; j < 8; j++) {
            double e = shadow_error_pct(f_hz, fs_hz, i * 9.0 / fs_hz / 12.0, j * TWO_PI / 8.0);
            assert(isfinite(e));
            if (e < *lo) *lo = e;
            if (e > *hi) *hi = e;
        }
}

static void test_clock_table(void)
{
    /* 64 candidates 80.000 .. 72.125 kS/s; VBUS (3 of 9 slots) stays above its 20 kS/s need. */
    assert(RMS_SHADOW_FS_NOMINAL_HZ - RMS_SHADOW_FS_STEP_HZ * (RMS_SHADOW_FS_COUNT - 1) == 72125u);
    assert(3.0 * 72125.0 / 9.0 >= 24000.0);
    for (float f = 31000.0f; f <= 55000.0f; f += 1000.0f) {
        uint32_t fs = rms_shadow_select_fs(f, NULL);
        assert(fs <= 80000u && fs >= 72125u && (80000u - fs) % 125u == 0);
    }
    assert(rms_shadow_lock_metric(NAN, 80000u) == 1.0f && rms_shadow_lock_metric(40000.0f, 0u) == 1.0f);
    tests++;
}

static void test_lock_case(void)
{
    /* 40 kHz and the multiples of 8.889 kHz (the 112.5 us pattern repeat): the as-built clock is
     * phase locked there; the selected clock is not. */
    static const double lock_f[] = {40000.0, 35555.6, 44444.4, 53333.3, 26666.7};
    double worst_fixed = 0, worst_sel = 0;
    for (unsigned k = 0; k < sizeof lock_f / sizeof lock_f[0]; k++) {
        float f = (float)lock_f[k];
        float m_fixed = rms_shadow_lock_metric(f, 80000u), m_sel;
        uint32_t fs = rms_shadow_select_fs(f, &m_sel);
        double lo, hi, slo, shi;
        worst_over_phase(f, 80000u, &lo, &hi);
        worst_over_phase(f, fs, &slo, &shi);
        double ef = fmax(fabs(lo), fabs(hi)), es = fmax(fabs(slo), fabs(shi));
        printf("f %.1f Hz: fixed 80 kS/s metric %.3f err %+.1f..%+.1f %% | selected %u S/s metric %.4f err %+.2f..%+.2f %%\n",
               lock_f[k], m_fixed, lo, hi, fs, m_sel, slo, shi);
        if (k < 4) assert(m_fixed > 0.5f && ef > 10.0);       /* the as-built clock is locked */
        assert(m_sel < 0.1f && fs != 80000u);                 /* selection leaves it */
        assert(es <= 3.0);
        if (ef > worst_fixed) worst_fixed = ef;
        if (es > worst_sel) worst_sel = es;
    }
    printf("lock cases: worst error fixed clock %.1f %%, selected clock %.2f %%\n", worst_fixed, worst_sel);
    tests++;
}

static void test_scan(void)
{
    /* 31-55 kHz in 50 Hz steps: with the selected clock the worst bin stays small. */
    double worst = 0, worst_f = 0;
    float worst_m = 0;
    unsigned over2 = 0, n = 0;
    for (float f = 31000.0f; f <= 55000.0f; f += 50.0f) {
        float m;
        uint32_t fs = rms_shadow_select_fs(f, &m);
        if (m > worst_m) worst_m = m;
        double lo, hi;
        worst_over_phase(f, fs, &lo, &hi);
        double e = fmax(fabs(lo), fabs(hi));
        if (e > worst) { worst = e; worst_f = f; }
        if (e > 2.0) over2++;
        n++;
    }
    printf("scan 31-55 kHz, 50 Hz bins (%u): worst error %.2f %% at %.0f Hz, bins over 2 %%: %u, worst metric %.4f\n",
           n, worst, worst_f, over2, worst_m);
    assert(over2 == 0 && worst <= 2.0 && worst_m < 0.1f);
    /* hold: the clock in use is kept while its figure is within RMS_SHADOW_LOCK_HOLD */
    float m;
    uint32_t fs = rms_shadow_select_fs(40000.0f, &m);
    assert(rms_shadow_hold_fs(40000.0f, fs) == fs);
    assert(rms_shadow_hold_fs(40000.0f, 80000u) == fs);      /* locked: reselected */
    assert(rms_shadow_hold_fs(40000.0f, 12345u) == fs);      /* not a table clock: reselected */
    tests++;
}

static void test_accumulator(void)
{
    rms_shadow_t s;
    rms_shadow_reset(&s);
    float r = 1;
    for (int i = 0; i < 99; i++) rms_shadow_add_mv(&s, 1650.0f + 15.0f * 10.0f, 0.0f);
    assert(!rms_shadow_close(&s, &r) && isnan(r) && s.n == 0);        /* too few, and reset */
    for (int i = 0; i < 200; i++) rms_shadow_add_mv(&s, 1650.0f + ((i & 1) ? 1 : -1) * 15.0f * 10.0f, 0.0f);
    assert(rms_shadow_close(&s, &r) && fabsf(r - 10.0f) < 1e-3f);     /* +-10 A square: 10 A RMS */
    rms_shadow_add_mv(&s, NAN, 0.0f);
    assert(s.n == 0);
    for (int i = 0; i < 150; i++) rms_shadow_add_mv(&s, 1700.0f + 15.0f * 4.0f, 1700.0f);  /* own zero */
    assert(rms_shadow_close(&s, &r) && fabsf(r - 4.0f) < 1e-3f);
    rms_shadow_add_sum(&s, 150.0 * 9.0, 150);
    assert(rms_shadow_close(&s, &r) && fabsf(r - 3.0f) < 1e-3f);
    rms_shadow_add_sum(&s, -1.0, 5);
    rms_shadow_add_sum(&s, NAN, 5);
    assert(s.n == 0);
    tests++;
}

/* ---- the binding only copies it into telemetry ---------------------------------------------------- */
typedef struct {
    uint64_t now;
    bool pads, gate;
    float shadow_value;
    uint32_t calls, last_f;
    bool shadow_ok;
    uint64_t next_zero;
    int pending;
} fk_t;
static fk_t K;
static n21_binding_t NB;
static uint64_t k_now(void *c) { (void)c; return K.now; }
static bool k_prog(void *c, const bridge_cycle_t *y) { (void)c; (void)y; return true; }
static bool k_out(void *c, bool live) { (void)c; K.pads = live; return true; }
static bool k_cap(void *c, n21_pwm_capture_t *y) { (void)c; memset(y, 0, sizeof *y); return true; }
static bool k_gate(void *c, bool on) { (void)c; K.gate = on; return true; }
static bool k_stat(void *c, n21_status_rb_t *s) { (void)c; *s = (n21_status_rb_t){true, false, true, true}; return true; }
static bool k_rst(void *c) { (void)c; return true; }
static bool k_adc1(void *c, float *v, float *ct)
{
    (void)c;
    *v = (N21_VBUS_BIAS_V + N21_VBUS_V_PER_V * 170.0f * fabsf(sinf(6.28318530718f * 60.0f * (float)K.now * 1e-6f))) * 1e3f;
    *ct = 1650.0f;
    return true;
}
static bool k_ext(void *c, unsigned ch, uint16_t *code)
{
    (void)c;
    if (ch == N21_MCP3202_CH_REF) *code = (uint16_t)lroundf(2.5f * 4096.0f / 3.3f);
    else {
        float rms = 14.0f * fabsf(sinf(6.28318530718f * 60.0f * (float)K.now * 1e-6f));
        *code = (uint16_t)lroundf(rms * N21_RMS_V_PER_A * (2.5f * 4096.0f / 3.3f) / 2.5f);
    }
    return true;
}
static bool k_zc(void *c, uint32_t *z, uint64_t *t) { (void)c; *z = 1000; *t = K.now; return true; }
static size_t k_edges(void *c, uint64_t *t, bool *lv, size_t max)
{
    (void)c;
    size_t n = 0;
    while (n < max) {
        uint64_t e = K.pending == 0 ? K.next_zero - 1000 : K.next_zero + 1000;
        if (e > K.now) break;
        t[n] = e; lv[n] = K.pending == 0; n++;
        if (K.pending == 1) K.next_zero += 8333;
        K.pending ^= 1;
    }
    return n;
}
static bool k_shadow(void *c, uint32_t f, float *rms, uint32_t *fs)
{
    (void)c;
    K.calls++;
    K.last_f = f;
    *rms = K.shadow_value;
    *fs = 75000u;
    return K.shadow_ok;
}

static bool G_shadow_ok = true;
static void run_shadow_binding(bool with_shadow, float value, n21_telemetry_t *t, n21_fault_t *fault)
{
    memset(&K, 0, sizeof K);
    K.now = 1000000; K.next_zero = 1003000; K.shadow_value = value; K.shadow_ok = G_shadow_ok;
    n21_config_t c = n21_config_default();
    c.mode = N21_MODE_BENCH;
    n21_hw_ops_t o = {
        .now_us = k_now, .pwm_program = k_prog, .pwm_outputs = k_out, .pwm_capture = k_cap, .run_gate = k_gate,
        .read_status = k_stat, .interlock_reset_pulse = k_rst, .read_adc1 = k_adc1, .read_ext_adc = k_ext,
        .read_ct_zc = k_zc, .line_zc_edges = k_edges, .shadow_half = with_shadow ? k_shadow : NULL,
    };
    assert(n21_binding_init(&NB, &c, &o, NULL) == N21_INIT_BENCH);
    for (unsigned i = 0; i < 4000; i++) {          /* 2.5 s of 625 us acquisition */
        K.now += 625;
        n21_acquire_step(&NB);
    }
    n21_telemetry(&NB, t);
    *fault = NB.fault;
}

static void test_telemetry_only(void)
{
    n21_telemetry_t base, a, b, c;
    n21_fault_t fb, fa, fbad, fc;
    run_shadow_binding(false, 0.0f, &base, &fb);
    assert(base.have_half && !base.shadow_valid && base.halves_ok > 100);
    /* Shadow wildly wrong in either direction: not one limit, fault or estimate moves. */
    float vals[3] = {0.0f, 22.0f, 900.0f};
    for (unsigned k = 0; k < 3; k++) {
        n21_telemetry_t *tt = k == 0 ? &a : k == 1 ? &b : &c;
        n21_fault_t *ff = k == 0 ? &fa : k == 1 ? &fbad : &fc;
        run_shadow_binding(true, vals[k], tt, ff);
        assert(*ff == fb && tt->fault == base.fault);
        assert(tt->halves_ok == base.halves_ok && tt->halves_bad == base.halves_bad);
        assert(tt->last_half.est.tank_rms_a == base.last_half.est.tank_rms_a);
        assert(tt->last_half.est.inlet_bound_a == base.last_half.est.inlet_bound_a);
        assert(tt->last_half.est.tank_ceiling_w == base.last_half.est.tank_ceiling_w);
        assert(tt->freq_hz == base.freq_hz && tt->freq_reason == base.freq_reason &&
               tt->ceiling_eff_a == base.ceiling_eff_a);
        assert(tt->shadow_valid && tt->shadow_fs_hz == 75000u && tt->shadow_rms_a == vals[k]);
        assert(K.calls >= tt->halves_ok + tt->halves_bad && K.calls <= tt->halves_ok + tt->halves_bad + 1 &&
               K.last_f == tt->freq_hz);   /* once per LINE_ZC edge (the first opens a half) */
    }
    assert(fb == N21_FAULT_NONE);
    /* A half the shadow could not close reports invalid and NAN, nothing else changes. */
    G_shadow_ok = false;
    n21_telemetry_t t;
    n21_fault_t f;
    run_shadow_binding(true, 5.0f, &t, &f);
    G_shadow_ok = true;
    assert(!t.shadow_valid && isnan(t.shadow_rms_a) && f == N21_FAULT_NONE &&
           t.halves_ok == base.halves_ok && t.last_half.est.tank_rms_a == base.last_half.est.tank_rms_a);
    tests++;
}

int main(void)
{
    test_clock_table();
    test_lock_case();
    test_scan();
    test_accumulator();
    test_telemetry_only();
    printf("rms shadow: %u tests passed\n", tests);
    return 0;
}
