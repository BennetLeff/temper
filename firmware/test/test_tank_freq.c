/* Stage-15 tank ceiling and per-pan frequency loop (tank_freq.c). Assertions are the oracle (built
 * with -UNDEBUG). The plant is a first-harmonic series RLC (round 6's FHA basis): constant L, C, R
 * per case, bridge fundamental v1 over the line cycle, peak = 2.17 x line RMS. */
#include "tank_freq.h"
#include "../config.h" /* TANK_NO_PAN_* */
#include <assert.h>
#include <math.h>
#include <stdio.h>

static unsigned tests;
#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))
#define PI 3.14159265358979

typedef struct { double L, C, R, v1; } tank_t;

static double f_res(const tank_t *k) { return 1.0 / (2 * PI * sqrt(k->L * k->C)); }

static tank_freq_obs_t observe(const tank_t *k, uint32_t f)
{
    double w = 2 * PI * f, x = w * k->L - 1.0 / (w * k->C), z = hypot(k->R, x), i = k->v1 / z;
    double p = i * i * k->R;
    return (tank_freq_obs_t){
        .valid = true, .phase_valid = true, .fit_ok = true, .f_hz = f, .f_fit_hz = (float)f, .phi_rad = (float)atan2(x, k->R),
        .tank_rms_a = (float)i, .inlet_a = (float)(p / 0.93 / 120.0 * 1.10 + 1.3),
        .peak_a = (float)(2.17 * i), .p_inv_w = (float)p, .p_in_w = (float)(p / 0.93),
        .r_lag_ohm = (float)k->R, /* |Z| cos(phi) */
    };
}

static tank_freq_limits_t limits(float ceiling)
{
    /* request: far above anything the stage can draw, so only the hardware limits bind */
    return (tank_freq_limits_t){.ceiling_a = ceiling, .inlet_max_a = 13.5f, .peak_trip_a = tank_peak_trip_for(ceiling),
                                .request_w = 1e6f};
}

/* Runs `halves` closed half cycles with the actuator following the target at once. Checks on every
 * step: |df| bounded, f inside [f_min, f_max], never below 1.05 f_res after a step down, and the
 * half-cycle RMS never at the 1.05 x ceiling trip. Returns the last reason. */
static tank_freq_reason_t run(const tank_t *k, const tank_freq_cfg_t *c, const tank_freq_limits_t *lim,
                              tank_freq_t *t, unsigned halves, tank_freq_obs_t *last)
{
    tank_freq_reason_t r = TF_HOLD_LIMIT;
    for (unsigned n = 0; n < halves; n++) {
        uint32_t f0 = t->f_hz;
        tank_freq_obs_t o = observe(k, f0);
        assert(o.tank_rms_a < tank_rms_trip_for(lim->ceiling_a));
        r = tank_freq_step(t, c, lim, &o);
        uint32_t d = t->f_hz > f0 ? t->f_hz - f0 : f0 - t->f_hz;
        assert(d <= (t->f_hz > f0 ? c->step_up_hz : c->step_down_hz));
        assert(t->f_hz >= c->f_min_hz && t->f_hz <= c->f_max_hz);
        if (r == TF_DOWN) assert(t->f_hz + 1.0 >= c->f_res_margin * f_res(k));
        if (last) *last = o;
    }
    return r;
}

/* ------------------------------------------------------------------ trips and caps */
static void test_trip_derivation(void)
{
    /* PLAN section 4: min(2.17 c + 3, 62); 1.05 c on the half RMS; 1.5 c per sample. */
    static const struct { float c, peak, rms, crest; } k[] = {
        {17.5f, 40.975f, 18.375f, 26.25f}, {18, 42.06f, 18.9f, 27.0f}, {20, 46.4f, 21.0f, 30.0f},
        {22, 50.74f, 23.1f, 33.0f}, {24, 55.08f, 25.2f, 36.0f}, {26, 59.42f, 27.3f, 39.0f},
        {28, 62.0f, 29.4f, 42.0f},
    };
    for (unsigned i = 0; i < sizeof k / sizeof k[0]; i++) {
        assert(NEAR(tank_peak_trip_for(k[i].c), k[i].peak, 1e-3));
        assert(NEAR(tank_rms_trip_for(k[i].c), k[i].rms, 1e-3));
        assert(NEAR(tank_crest_guard_for(k[i].c), k[i].crest, 1e-3));
        /* Firmware trip below the stage-15 CT band low corner (64.55 A) and the config cap. */
        assert(tank_peak_trip_for(k[i].c) < TANK_PEAK_TRIP_MAX_A && TANK_PEAK_TRIP_MAX_A < 64.55f);
        /* The crest guard sits above the crest (x1.41) of a half at the RMS trip. */
        assert(tank_crest_guard_for(k[i].c) > 1.41421356f * tank_rms_trip_for(k[i].c));
        /* Peak trip less the 3 A pickup margin covers 2.17 x ceiling up to 26 A ... */
        if (k[i].c <= 26) assert(tank_peak_trip_for(k[i].c) - 3.0f >= TANK_PEAK_PER_RMS * k[i].c - 1e-3f);
    }
    /* ... and the 62 A cap binds at 28 A: the loop's peak limit (62 - 3 A) holds the line RMS to
     * 59 / 2.17 = 27.19 A while the peak estimate is 2.17 x RMS (see test_stop_peak). */
    assert(tank_peak_trip_for(28) - 3.0f < TANK_PEAK_PER_RMS * 28);
    assert(NEAR(tank_peak_trip_for(27.0f), 61.59, 1e-3) && tank_peak_trip_for(30) == 62.0f);
    tests++;
}

static void test_config_caps(void)
{
    assert(tank_ceiling_ok(TANK_CEILING_DEFAULT_A) && tank_ceiling_ok(22) && tank_ceiling_ok(28) && tank_ceiling_ok(10));
    /* Shipping ceiling 17.5 A (power-stage OPEN-ITEMS S17, hot-copper B3 basis), inside the 10..28 A
     * commissioning range; not a whole number of amps. */
    assert(TANK_CEILING_DEFAULT_A == 17.5f && TANK_CEILING_DEFAULT_A < TANK_CEILING_MAX_A);
    assert(!tank_ceiling_ok(28.01f) && !tank_ceiling_ok(9.9f) && !tank_ceiling_ok(NAN) && !tank_ceiling_ok(44));
    tank_freq_cfg_t d = tank_freq_default(), c;
    assert(tank_freq_config_ok(&d) && d.f_min_hz == 35000 && d.f_max_hz == 60000 && d.f_res_margin == 1.05f);
    assert(!tank_freq_config_ok(NULL));
    c = d; c.f_min_hz = 34999; assert(!tank_freq_config_ok(&c));          /* below the window */
    c = d; c.f_max_hz = 60001; assert(!tank_freq_config_ok(&c));
    c = d; c.f_min_hz = 60000; assert(!tank_freq_config_ok(&c));          /* empty window */
    c = d; c.f_res_margin = 1.04f; assert(!tank_freq_config_ok(&c));      /* never inside 1.05 f_res */
    c = d; c.f_res_margin = NAN; assert(!tank_freq_config_ok(&c));
    c = d; c.step_down_hz = 0; assert(!tank_freq_config_ok(&c));          /* bounded, non-zero steps */
    c = d; c.step_down_hz = 1001; c.step_up_hz = 1001; assert(!tank_freq_config_ok(&c));
    c = d; c.step_up_hz = 2001; assert(!tank_freq_config_ok(&c));
    c = d; c.step_up_hz = 100; assert(!tank_freq_config_ok(&c));          /* retreat >= approach */
    c = d; c.peak_margin_a = 2.9f; assert(!tank_freq_config_ok(&c));      /* >= 3 A pickup */
    c = d; c.zvs_lag_deg = 44; assert(!tank_freq_config_ok(&c));      /* must prove 1.05 f_res at Q 10 */
    c = d; c.fit_lag_max_deg = 89; assert(!tank_freq_config_ok(&c));
    c = d; c.fit_sep_hz = 30000; assert(!tank_freq_config_ok(&c));
    c = d; c.pan_q_max = 0; assert(!tank_freq_config_ok(&c));
    c = d; c.pan_r_min_ohm = NAN; assert(!tank_freq_config_ok(&c));
    c = d; c.overrun_halves = 0; assert(!tank_freq_config_ok(&c));
    c = d; c.block_halves = 1201; assert(!tank_freq_config_ok(&c));
    c = d; c.power_band = 0.02f; assert(!tank_freq_config_ok(&c));        /* narrower than one step */
    c = d; c.power_band = NAN; assert(!tank_freq_config_ok(&c));
    tests++;
}

/* ------------------------------------------------------------------ f_res estimate */
static void test_fit(void)
{
    tank_t k = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 100};
    tank_freq_obs_t a = observe(&k, 50000), b = observe(&k, 48000);
    float w0sq, lr;
    assert(tank_freq_fit(50000, tanf(a.phi_rad), 48000, tanf(b.phi_rad), &w0sq, &lr));
    assert(NEAR(sqrt(w0sq) / (2 * PI), f_res(&k), 0.002 * f_res(&k)) && NEAR(lr, k.L / k.R, 1e-3 * k.L / k.R));
    /* Order does not matter; C cancels: the same lags fit whatever the bank tolerance. */
    float w2, l2;
    assert(tank_freq_fit(48000, tanf(b.phi_rad), 50000, tanf(a.phi_rad), &w2, &l2) && NEAR(w2, w0sq, 1e-3 * w0sq));
    /* Refused: same frequency, capacitive or zero lag, lag falling with f, non-finite. */
    assert(!tank_freq_fit(50000, 2, 50000, 2, &w0sq, &lr));
    assert(!tank_freq_fit(50000, -0.1f, 48000, 1, &w0sq, &lr));
    assert(!tank_freq_fit(50000, 1, 48000, 0, &w0sq, &lr));
    assert(!tank_freq_fit(50000, 1, 48000, 3, &w0sq, &lr));
    assert(!tank_freq_fit(50000, NAN, 48000, 1, &w0sq, &lr));
    /* Equal lags at two frequencies imply resonance above them: refused. */
    assert(!tank_freq_fit(50000, 0.577f, 48000, 0.577f, &w0sq, &lr));
    assert(tank_freq_slew(60000, 50000, 1000) == 59000 && tank_freq_slew(50000, 60000, 1000) == 51000);
    assert(tank_freq_slew(50000, 50400, 1000) == 50400 && tank_freq_slew(50000, 50000, 1000) == 50000);
    tests++;
}

/* ------------------------------------------------------------------ stops */
static tank_freq_cfg_t C;
static tank_freq_t T;

static void test_stop_floor_min(void)
{
    /* Low line: no limit binds anywhere above 35 kHz, f_res ~ 27 kHz: stops at f_min. */
    tank_t k = {.L = 66.5e-6, .C = 0.5e-6, .R = 2.0, .v1 = 40};
    tank_freq_limits_t lim = limits(22);
    tank_freq_reset(&T, &C);
    tank_freq_obs_t o;
    assert(run(&k, &C, &lim, &T, 300, &o) == TF_HOLD_FLOOR_MIN);
    assert(T.f_hz == 35000 && T.floor_hz == 35000 && T.have_fit && NEAR(T.f_res_hz, f_res(&k), 50));
    assert(o.phi_rad > 45 * 0.0174533f);
    assert(o.tank_rms_a < 22 * 0.98f);
    tests++;
}

static void test_stop_zvs(void)
{
    /* (a) f_res 41.1 kHz, Q 6.5: the 45 deg lag binds (at ~1.08 f_res) before any current limit. */
    tank_t k = {.L = 50e-6, .C = 0.3e-6, .R = 2.0, .v1 = 30};
    tank_freq_limits_t lim = limits(22);
    tank_freq_reset(&T, &C);
    tank_freq_obs_t o;
    (void)run(&k, &C, &lim, &T, 300, &o);
    o = observe(&k, T.f_hz);
    assert(T.f_hz >= 1.05 * f_res(&k) && o.phi_rad >= 45 * 0.0174533f && o.phi_rad < 47 * 0.0174533f);
    assert(T.have_fit && NEAR(T.f_res_hz, f_res(&k), 50) && o.tank_rms_a < 22 * 0.98f);
    /* (b) Same f_res, Q 20 (outside the lag argument): the fitted 1.05 f_res floor (43.1 kHz) binds. */
    tank_t q20 = {.L = 50e-6, .C = 0.3e-6, .R = 0.65, .v1 = 20};
    tank_freq_reset(&T, &C);
    assert(run(&q20, &C, &lim, &T, 300, &o) == TF_HOLD_FLOOR_ZVS);
    assert(T.f_hz >= 1.05 * f_res(&q20) && T.f_hz <= 1.05 * f_res(&q20) + 30 && T.floor_hz == T.f_hz);
    assert(NEAR(T.f_res_hz, f_res(&q20), 30) && observe(&q20, T.f_hz).tank_rms_a < 22 * 0.98f);
    /* Never below the floor with a generous ceiling either. */
    lim.ceiling_a = 28;
    assert(run(&q20, &C, &lim, &T, 100, NULL) == TF_HOLD_FLOOR_ZVS && T.f_hz >= 1.05 * f_res(&q20));
    tests++;
}

static void test_stop_rms(void)
{
    /* Pan R 1.4 ohm: the ceiling binds well above the floor. At the 17.5 A shipping ceiling the
     * no-pan clamp equals the ceiling, so that is the plain RMS stop; above it (commissioned
     * raises 18 .. 26 A) the pan must be established to reach the ceiling. */
    tank_t k = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 108};
    static const float ceilings[] = {TANK_CEILING_DEFAULT_A, 18, 20, 22, 24, 26};
    for (unsigned i = 0; i < sizeof ceilings / sizeof ceilings[0]; i++) {
        const float ceiling = ceilings[i];
        tank_freq_limits_t lim = limits(ceiling);
        tank_freq_reset(&T, &C);
        tank_freq_obs_t o;
        tank_freq_reason_t r = run(&k, &C, &lim, &T, 400, &o);
        assert(r == TF_HOLD_LIMIT || r == TF_DOWN || r == TF_UP_RMS);
        /* Settled on the RMS limit: within one step of it, and above the floor. */
        o = observe(&k, T.f_hz);
        assert(o.tank_rms_a <= ceiling * 1.0f + 1e-3f || r == TF_UP_RMS);
        assert(o.tank_rms_a >= ceiling * 0.93f && T.f_hz > T.floor_hz);
        assert(o.inlet_a < 13.5f && o.peak_a <= lim.peak_trip_a - 3 + 1e-3f);
        assert(T.pan_present && T.q < 10 && T.ceiling_eff_a == ceiling);
    }
    tests++;
}

static void test_stop_inlet(void)
{
    /* High-R pan (3.5 ohm): 1238 W of stage power at ~18.8 A (lag ~52 deg), so the 13.5 A inlet
     * hold binds first. */
    tank_t k = {.L = 55e-6, .C = 0.5e-6, .R = 3.5, .v1 = 108};
    tank_freq_limits_t lim = limits(28);
    tank_freq_reset(&T, &C);
    tank_freq_obs_t o;
    (void)run(&k, &C, &lim, &T, 400, &o);
    o = observe(&k, T.f_hz);
    assert(o.inlet_a <= 13.5f * 1.02f && o.inlet_a >= 13.5f * 0.95f);
    assert(o.tank_rms_a < 20 && T.f_hz > T.floor_hz);
    tests++;
}

static void test_stop_peak(void)
{
    /* Ceiling 28 A, low-R pan: the peak limit (62 - 3 A) binds at 2.17 x I = 59 A, i.e. 27.2 A
     * line RMS, before the 28 A RMS limit. A bench-lowered peak trip binds earlier still. */
    tank_t k = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 108};
    tank_freq_limits_t lim = limits(28);
    tank_freq_reset(&T, &C);
    tank_freq_obs_t o;
    (void)run(&k, &C, &lim, &T, 400, &o);
    o = observe(&k, T.f_hz);
    assert(T.pan_present && o.peak_a <= 59.0f * 1.001f && o.peak_a >= 59.0f * 0.93f);
    assert(o.tank_rms_a < 27.2f && o.tank_rms_a > 25);
    lim.peak_trip_a = 45;
    tank_freq_reset(&T, &C);
    (void)run(&k, &C, &lim, &T, 400, &o);
    o = observe(&k, T.f_hz);
    assert(o.peak_a <= 42.0f * 1.001f && o.peak_a >= 42.0f * 0.93f && o.tank_rms_a < 20);
    tests++;
}

static void test_up_on_violation(void)
{
    /* At a point that violates each limit, the loop steps up by step_up_hz (bounded), never more. */
    tank_t k = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 108};
    tank_freq_limits_t lim = limits(22);
    tank_freq_reset(&T, &C);
    (void)run(&k, &C, &lim, &T, 400, NULL);
    uint32_t f = T.f_hz;
    tank_freq_obs_t o = observe(&k, f);
    o.tank_rms_a = 22.5f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_RMS && T.f_hz == f + C.step_up_hz);
    o = observe(&k, f);
    o.inlet_a = 14.0f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_INLET && T.f_hz == f + C.step_up_hz);
    o = observe(&k, f);
    o.peak_a = lim.peak_trip_a - 1.0f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_PEAK && T.f_hz == f + C.step_up_hz);
    /* A marginal excess (<= hyst) retreats one approach step, and blocks re-approach to f. */
    o = observe(&k, f);
    o.tank_rms_a = 22.2f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_RMS && T.f_hz == f + C.step_down_hz);
    assert(T.block_hz == f && T.block_left == C.block_halves);
    o = observe(&k, f + C.step_down_hz);
    o.tank_rms_a = 15.0f; /* plenty of room, but the next step down would be f again */
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_HOLD_LIMIT && T.f_hz == f + C.step_down_hz);
    for (unsigned n = 0; n < C.block_halves; n++) (void)tank_freq_step(&T, &C, &lim, &o);
    assert(T.reason == TF_DOWN && T.f_hz == f); /* retried after block_halves */
    /* Clamped at f_max. */
    o = observe(&k, 59800);
    o.tank_rms_a = 30;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_RMS && T.f_hz == 60000);
    tests++;
}

/* ------------------------------------------------------------------ fault inputs */
static void test_fault_inputs(void)
{
    tank_t k = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 108};
    tank_freq_limits_t lim = limits(26);
    tank_freq_reset(&T, &C);
    (void)run(&k, &C, &lim, &T, 400, NULL);
    assert(T.pan_present && T.f_hz < 45000);
    uint32_t f = T.f_hz;
    /* Missing CT_ZC: no lag over the half. Steps up, drops the pan (clamp to the 17.5 A default). */
    tank_freq_obs_t o = observe(&k, f);
    o.phase_valid = false;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_NO_PHASE && T.f_hz == f + C.step_up_hz);
    assert(!T.pan_present && T.ceiling_eff_a == TANK_CEILING_DEFAULT_A);
    /* Stale / broken half: steps up from the target, pan stays dropped. */
    uint32_t g = T.f_hz;
    tank_freq_obs_t bad = {.valid = false};
    assert(tank_freq_step(&T, &C, &lim, &bad) == TF_UP_INVALID && T.f_hz == g + C.step_up_hz);
    assert(tank_freq_step(&T, &C, &lim, NULL) == TF_UP_INVALID && !T.pan_present);
    /* Non-finite or out-of-window inputs are the same as stale. */
    o = observe(&k, f); o.tank_rms_a = NAN;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_INVALID);
    o = observe(&k, f); o.phi_rad = NAN;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_INVALID);
    o = observe(&k, 30000);
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_INVALID);
    tank_freq_limits_t badlim = lim; badlim.ceiling_a = NAN;
    o = observe(&k, f);
    assert(tank_freq_step(&T, &C, &badlim, &o) == TF_UP_INVALID);
    /* Repeated faults walk back to f_max and stay there. */
    for (int n = 0; n < 40; n++) (void)tank_freq_step(&T, &C, &lim, &bad);
    assert(T.f_hz == 60000);
    /* A lag at or below zero puts f_res at/above f: below the floor, up. */
    tank_freq_reset(&T, &C);
    (void)run(&k, &C, &lim, &T, 150, NULL);
    assert(T.have_fit);
    f = T.f_hz;
    o = observe(&k, f); o.phi_rad = -0.05f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_BELOW_FLOOR && T.f_hz == f + C.step_up_hz);
    /* ZVS (a), the lag: below 45 deg retreats (a full step when beyond the band), blocks, and
     * inside the band holds. */
    tank_freq_reset(&T, &C);
    o = observe(&k, 50000); o.phi_rad = 40 * 0.0174533f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_LAG && T.f_hz == 51000 && T.block_hz == 50000);
    o = observe(&k, 50000); o.phi_rad = 44.5f * 0.0174533f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_UP_LAG && T.f_hz == 50250);
    tank_freq_reset(&T, &C);
    o = observe(&k, 50000); o.phi_rad = 45.5f * 0.0174533f;
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_HOLD_LIMIT && T.f_hz == 50000);
    /* Without any f_res fit (lags never usable) the lag criterion alone still stops the descent
     * above 1.05 f_res for Q <= 10 (run() checks every step down). */
    tank_t hi = {.L = 50e-6, .C = 0.3e-6, .R = 2.0, .v1 = 30}; /* f_res 41.1 kHz, Q 6.5 */
    tank_freq_reset(&T, &C);
    for (int n = 0; n < 300; n++) {
        o = observe(&hi, T.f_hz);
        o.fit_ok = false;
        tank_freq_reason_t r = tank_freq_step(&T, &C, &lim, &o);
        if (r == TF_DOWN) assert(T.f_hz >= 1.05 * f_res(&hi));
    }
    assert(!T.have_fit && T.f_hz >= 1.05 * f_res(&hi) && T.f_hz < 1.12 * f_res(&hi));
    tests++;
}

/* ------------------------------------------------------------------ no-pan clamp */
static void test_no_pan_clamp(void)
{
    /* Empty coil: R 0.2 ohm, 66.5 uH, Q ~ 55. Configured ceiling 28 A, but no pan is ever
     * established, so the loop holds the tank at or below the 17.5 A no-pan clamp. This is the
     * layer under the no-pan stop (test_no_pan_stop): it runs here with the stop off so the clamp
     * is seen on its own over 400 halves (the stop would end the run at half 240). */
    const tank_freq_cfg_t C_on = C;
    C.no_pan_stop = false;
    tank_t empty = {.L = 66.5e-6, .C = 0.5e-6, .R = 0.2, .v1 = 150};
    tank_freq_limits_t lim = limits(28);
    tank_freq_reset(&T, &C);
    tank_freq_obs_t o;
    for (unsigned n = 0; n < 400; n++) {
        o = observe(&empty, T.f_hz);
        assert(o.tank_rms_a <= TANK_CEILING_DEFAULT_A * 1.05f);
        tank_freq_reason_t r = tank_freq_step(&T, &C, &lim, &o);
        assert(r != TF_FAULT_OVERRUN && !T.pan_present && T.ceiling_eff_a == TANK_CEILING_DEFAULT_A);
    }
    o = observe(&empty, T.f_hz);
    /* Its ~88 deg lag never feeds a fit, so it can never show pan evidence. */
    assert(o.tank_rms_a <= TANK_CEILING_DEFAULT_A && o.tank_rms_a > TANK_CEILING_DEFAULT_A - 2 && !T.have_fit &&
           o.phi_rad > 85 * 0.0174533f);
    /* Would have gone well past the clamp (and the old 22 A one) at the floor. */
    assert(observe(&empty, 35000).tank_rms_a > 22.5f);

    /* A real pan establishes after pan_confirm_halves and gets the full ceiling. */
    tank_t pan = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 108};
    tank_freq_reset(&T, &C);
    (void)run(&pan, &C, &lim, &T, 400, &o);
    assert(T.pan_present && T.ceiling_eff_a == 28.0f && observe(&pan, T.f_hz).tank_rms_a > 25);
    uint32_t f_pan = T.f_hz;
    /* Pan lifted at that frequency: the evidence fails at once, the clamp returns to 17.5 A and the
     * loop retreats; holding above 1.05 x 17.5 A for more than overrun_halves latches. */
    tank_freq_obs_t lifted = observe(&pan, f_pan);
    lifted.p_inv_w = 0.2f * lifted.tank_rms_a * lifted.tank_rms_a; /* power per A^2 of an empty coil */
    assert(lifted.tank_rms_a > tank_rms_trip_for(TANK_CEILING_DEFAULT_A));
    tank_freq_reason_t r = TF_DOWN;
    unsigned n = 0;
    for (; n < 40 && r != TF_FAULT_OVERRUN; n++) {
        lifted.f_hz = f_pan; /* the actuator stuck: worst case */
        r = tank_freq_step(&T, &C, &lim, &lifted);
        assert(!T.pan_present && T.ceiling_eff_a == TANK_CEILING_DEFAULT_A);
        if (r != TF_FAULT_OVERRUN) assert(r == TF_UP_RMS || r == TF_UP_NO_PHASE || r == TF_UP_BELOW_FLOOR);
    }
    assert(r == TF_FAULT_OVERRUN && n == C.overrun_halves + 1);
    /* Evidence rules, one at a time, from an established pan. */
    static const int which[] = {0, 1, 2, 3};
    for (unsigned w = 0; w < 4; w++) {
        tank_freq_reset(&T, &C);
        (void)run(&pan, &C, &lim, &T, 400, NULL);
        assert(T.pan_present);
        o = observe(&pan, T.f_hz);
        switch (which[w]) {
        case 0: o.p_inv_w = 0.5f * o.tank_rms_a * o.tank_rms_a; break;  /* R below 0.8 ohm */
        case 1: o.tank_rms_a = 3.0f; o.p_inv_w = 9.0f * 1.4f; break;     /* too little current */
        case 2: o.phase_valid = false; break;                             /* no lag */
        case 3: o.valid = false; break;                                   /* stale */
        }
        (void)tank_freq_step(&T, &C, &lim, &o);
        assert(!T.pan_present && T.ceiling_eff_a == TANK_CEILING_DEFAULT_A);
    }
    /* Confirmation needs pan_confirm_halves consecutive halves of evidence. */
    tank_freq_reset(&T, &C);
    unsigned first = 0;
    for (unsigned h = 0; h < 400 && !first; h++) {
        o = observe(&pan, T.f_hz);
        (void)tank_freq_step(&T, &C, &lim, &o);
        if (T.pan_present) first = h;
    }
    assert(first >= C.pan_confirm_halves);
    /* With a ceiling at or below 17.5 A the clamp changes nothing; a raised 18 A or 20 A one is
     * clamped to 17.5 A until a pan is established. */
    tank_freq_limits_t l16 = limits(16), l18 = limits(18), l20 = limits(20);
    tank_freq_reset(&T, &C);
    o = observe(&empty, 60000);
    (void)tank_freq_step(&T, &C, &l16, &o);
    assert(T.ceiling_eff_a == 16.0f);
    tank_freq_reset(&T, &C);
    (void)tank_freq_step(&T, &C, &l18, &o);
    assert(!T.pan_present && T.ceiling_eff_a == TANK_CEILING_DEFAULT_A);
    tank_freq_reset(&T, &C);
    (void)tank_freq_step(&T, &C, &l20, &o);
    assert(!T.pan_present && T.ceiling_eff_a == TANK_CEILING_DEFAULT_A);
    C = C_on;
    tests++;
}

/* ------------------------------------------------------------------ power request */
static const tank_t PAN = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 108}; /* 120 V line */

static bool in_band(float p, float req) { return p >= (1 - C.power_band) * req && p <= (1 + C.power_band) * req; }

static void test_power_tracking(void)
{
    tank_freq_limits_t lim = limits(22);
    /* Limit-bound maximum for this pan at 22 A (the RMS stop). */
    tank_freq_reset(&T, &C);
    (void)run(&PAN, &C, &lim, &T, 400, NULL);
    uint32_t f_lim = T.f_hz;
    float p_max = observe(&PAN, f_lim).p_in_w;
    assert(p_max > 650 && p_max < 750);
    /* Mid request: 400 W tracked inside the dead band, above the limit-bound frequency. */
    lim.request_w = 400;
    tank_freq_reset(&T, &C);
    assert(run(&PAN, &C, &lim, &T, 400, NULL) == TF_HOLD_POWER);
    assert(in_band(observe(&PAN, T.f_hz).p_in_w, 400) && T.f_hz > f_lim);
    assert(observe(&PAN, T.f_hz).tank_rms_a < 22 * 0.98f);
    /* Request above the limit-bound maximum: the limits win, same stop as no request. */
    lim.request_w = 1500;
    tank_freq_reset(&T, &C);
    tank_freq_reason_t r = run(&PAN, &C, &lim, &T, 400, NULL);
    assert(r != TF_HOLD_POWER && T.f_hz == f_lim && observe(&PAN, T.f_hz).p_in_w < 1500 * 0.94f);
    tests++;
}

static void test_power_steps(void)
{
    tank_freq_limits_t lim = limits(22);
    lim.request_w = 300;
    tank_freq_reset(&T, &C);
    (void)run(&PAN, &C, &lim, &T, 400, NULL);
    uint32_t f300 = T.f_hz;
    assert(in_band(observe(&PAN, f300).p_in_w, 300));
    /* Step up to 600 W while running: bounded steps down in f (run() checks each), settles. */
    lim.request_w = 600;
    unsigned n = 0;
    while (!in_band(observe(&PAN, T.f_hz).p_in_w, 600) && n < 400) { (void)run(&PAN, &C, &lim, &T, 1, NULL); n++; }
    assert(n < 400 && T.f_hz < f300);
    (void)run(&PAN, &C, &lim, &T, 200, NULL);
    assert(in_band(observe(&PAN, T.f_hz).p_in_w, 600));
    uint32_t f600 = T.f_hz;
    /* Step down to 200 W: retreats up in f with the same bounded steps, settles in band. */
    lim.request_w = 200;
    for (n = 0; n < 400 && !in_band(observe(&PAN, T.f_hz).p_in_w, 200); n++) {
        uint32_t f0 = T.f_hz;
        (void)run(&PAN, &C, &lim, &T, 1, NULL);
        assert(T.f_hz >= f0 && T.f_hz - f0 <= C.step_up_hz);
    }
    assert(n < 400 && T.f_hz > f600);
    (void)run(&PAN, &C, &lim, &T, 400, NULL);
    assert(in_band(observe(&PAN, T.f_hz).p_in_w, 200));
    /* Step back up after the retreat: the raised request clears the re-approach block. */
    lim.request_w = 500;
    (void)run(&PAN, &C, &lim, &T, 300, NULL);
    assert(in_band(observe(&PAN, T.f_hz).p_in_w, 500));
    /* An RMS limit still wins over a request that is raised further. */
    lim.ceiling_a = 15;
    lim.request_w = 1500;
    tank_freq_reset(&T, &C); /* a ceiling cut below the running current would trip: restart */
    (void)run(&PAN, &C, &lim, &T, 400, NULL);
    assert(observe(&PAN, T.f_hz).tank_rms_a <= 15.0f * 1.001f && observe(&PAN, T.f_hz).tank_rms_a > 14);
    tests++;
}

static void test_power_no_chatter(void)
{
    /* Across the whole range of requests, on a low-R pan (2.8 % current per step near the floor)
     * and a nominal one: once settled, 600 more halves without a single frequency change. */
    static const tank_t pans[] = {{55e-6, 0.5e-6, 1.4, 108}, {55e-6, 0.5e-6, 1.0, 108}, {60e-6, 0.5e-6, 2.5, 108}};
    unsigned cases = 0;
    for (unsigned k = 0; k < 3; k++) {
        for (float req = 100; req <= 1300; req += 37) {
            tank_freq_limits_t lim = limits(22);
            lim.request_w = req;
            tank_freq_reset(&T, &C);
            (void)run(&pans[k], &C, &lim, &T, 600, NULL);
            uint32_t f = T.f_hz;
            unsigned changes = 0;
            for (unsigned h = 0; h < 600; h++) {
                uint32_t f0 = T.f_hz;
                (void)run(&pans[k], &C, &lim, &T, 1, NULL);
                if (T.f_hz != f0) changes++;
            }
            /* a block retry (once per block_halves) is the only change allowed at a hard limit */
            assert(changes <= 2 * (600 / C.block_halves + 1));
            if (T.reason == TF_HOLD_POWER) { assert(changes == 0 && T.f_hz == f); cases++; }
        }
    }
    assert(cases > 20);
    tests++;
}

static void test_power_below_fmax_minimum(void)
{
    /* The minimum continuous input power at 60 kHz (FHA model, 120 V line; 132 V is x1.21). */
    static const struct { tank_t k; const char *name; } pans[] = {
        {{55e-6, 0.5e-6, 1.4, 108}, "low-R pan (1.4 ohm)"},
        {{55e-6, 0.5e-6, 2.0, 108}, "typical pan (2.0 ohm)"},
        {{55e-6, 0.5e-6, 3.5, 108}, "high-R pan (3.5 ohm)"},
    };
    for (unsigned i = 0; i < 3; i++) {
        float p_min = observe(&pans[i].k, 60000).p_in_w;
        printf("  min continuous power at 60 kHz, %s: %.0f W in (%.1f A tank)\n", pans[i].name, p_min,
               observe(&pans[i].k, 60000).tank_rms_a);
        tank_freq_limits_t lim = limits(22);
        lim.request_w = 0.5f * p_min;          /* below what 60 kHz delivers */
        tank_freq_reset(&T, &C);
        assert(run(&pans[i].k, &C, &lim, &T, 50, NULL) == TF_POWER_AT_FMAX && T.f_hz == 60000);
        /* From a running point, a request cut below the minimum walks back up and caps at f_max. */
        lim.request_w = 800;
        (void)run(&pans[i].k, &C, &lim, &T, 300, NULL);
        assert(T.f_hz < 50000);
        lim.request_w = 10;
        assert(run(&pans[i].k, &C, &lim, &T, 300, NULL) == TF_POWER_AT_FMAX && T.f_hz == 60000);
        lim.request_w = 0;                     /* zero (the adapter stops the bridge anyway) */
        assert(run(&pans[i].k, &C, &lim, &T, 5, NULL) == TF_POWER_AT_FMAX && T.f_hz == 60000);
    }
    tests++;
}

/* ------------------------------------------------------------------ coil of record (F1) */
/* Coil study temper-coil-r1 (branch study/coil-r1, output/temper-coil-r1/README.md section 1 and
 * model/results/TABLES.md): winding R1, 81.1 uH free air, 77.0 uH installed, on the 0.5 uF bank
 * (5 x 100 nF +/-5 %: 0.475-0.525 uF). Loaded L and R at 40 kHz, 3D-corrected (run_pans.py):
 * ferrous 33-63 uH / 2.1-6.2 ohm (carbon steel mu-low .. 430 mu-high), cast iron nominal
 * 46.1 uH / 4.26 ohm; the 1 ohm case is the round-4 priors basis (coil_mc.rs low-R classes). The
 * special loads: no pan 77 uH / 0.13 ohm (Litz R_ac + enclosure eddy, Q ~ 250), aluminium 240 mm
 * 23.6 uH / 0.24 ohm (0.13 reflected + 0.11 Litz at 100 C). R is held constant over frequency, as
 * in the rest of this file. Lines 108 / 120 / 132 V (v1 = 0.9 x line, round 6 FHA). */
typedef struct { const char *name; double L, R; } plant_t;
static const plant_t HEATABLE[] = {
    {"carbon steel mu-low", 33e-6, 2.1}, {"cast iron nominal", 46e-6, 4.3}, {"430 mu-high", 63e-6, 6.2},
    {"priors low-R", 55e-6, 1.0},
};
static const plant_t NO_PAN = {"no pan", 77e-6, 0.13};
static const plant_t ALUMINIUM = {"aluminium 240 mm", 23.6e-6, 0.24};
static const double LINES_V[] = {108, 120, 132};
static const double BANK_F[] = {0.475e-6, 0.5e-6, 0.525e-6};

static tank_t plant(const plant_t *p, double line_v, double c_f)
{
    return (tank_t){.L = p->L, .C = c_f, .R = p->R, .v1 = 0.9 * line_v};
}

static void test_coil_of_record_heatable(void)
{
    /* Every heatable plant at every line / bank corner, at the shipping 17.5 A and a raised 22 A
     * ceiling: run() checks the step bounds, the 1.05 f_res floor and that no half reaches the
     * RMS trip; the end point holds every limit with ZVS margin. */
    static const float ceilings[] = {TANK_CEILING_DEFAULT_A, 22.0f};
    unsigned cases = 0;
    for (unsigned ci = 0; ci < 2; ci++)
        for (unsigned p = 0; p < sizeof HEATABLE / sizeof HEATABLE[0]; p++)
            for (unsigned li = 0; li < 3; li++)
                for (unsigned k = 0; k < 3; k++) {
                    tank_t pl = plant(&HEATABLE[p], LINES_V[li], BANK_F[k]);
                    tank_freq_limits_t lim = limits(ceilings[ci]);
                    tank_freq_reset(&T, &C);
                    tank_freq_reason_t r = run(&pl, &C, &lim, &T, 1200, NULL);
                    tank_freq_obs_t o = observe(&pl, T.f_hz);
                    assert(r != TF_FAULT_OVERRUN && r != TF_UP_INVALID && r != TF_UP_NO_PHASE);
                    assert(T.f_hz + 1.0 >= 1.05 * f_res(&pl) && o.phi_rad >= 0.98f * 45 * 0.0174533f);
                    assert(o.tank_rms_a <= ceilings[ci] * 1.001f && o.peak_a <= lim.peak_trip_a - 3 + 1e-3f);
                    assert(o.inlet_a <= 13.5f * 1.001f);
                    cases++;
                }
    assert(cases == 72);
    tests++;
}

static void test_coil_of_record_special_loads_baseline(void)
{
    /* What the loop does with the two special loads on its own (the F1 record; F3 and F4 below
     * act on exactly these). Aluminium: 25-36 A at the 60 kHz start, over the 1.05 x 17.5 A RMS
     * trip and the 2.17 x RMS peak estimate over the 41 A peak trip from the first half, at every
     * corner. No pan: walks down to the 35 kHz floor and holds there at 11.7-16.1 A, under the
     * 17.5 A no-pan clamp, with no trip. */
    for (unsigned li = 0; li < 3; li++)
        for (unsigned k = 0; k < 3; k++) {
            tank_t al = plant(&ALUMINIUM, LINES_V[li], BANK_F[k]);
            tank_freq_obs_t o = observe(&al, 60000);
            assert(o.tank_rms_a > 25 && o.tank_rms_a < 36);
            assert(o.tank_rms_a > tank_rms_trip_for(TANK_CEILING_DEFAULT_A) &&
                   o.peak_a > tank_peak_trip_for(TANK_CEILING_DEFAULT_A));
            assert(o.phi_rad > 85 * 0.0174533f && f_res(&al) > 45000);
            tank_t np = plant(&NO_PAN, LINES_V[li], BANK_F[k]);
            assert(f_res(&np) >= 24900 && f_res(&np) <= 26400 && 1.05 * f_res(&np) < 35000);
            o = observe(&np, 35000);
            assert(o.tank_rms_a > 11.5f && o.tank_rms_a < 16.2f && o.phi_rad > 88.5f * 0.0174533f);
            assert(observe(&np, 60000).tank_rms_a > 4.0f);
        }
    tests++;
}

/* ------------------------------------------------------------------ no-pan stop (F4) */
/* A half as the binding builds it when CT_ZC reads err_deg off: the lag is phi + err, and the
 * delivered power (input_limits: 0.9 x bus x I x cos(phi), clamped at 0) and the series R from the
 * lag (|Z| cos(phi)) come from it. */
static tank_freq_obs_t observe_err(const tank_t *k, uint32_t f, double err_deg)
{
    tank_freq_obs_t o = observe(k, f);
    double phi = o.phi_rad + err_deg * PI / 180;
    o.phi_rad = (float)phi;
    o.p_inv_w = (float)fmax(0, k->v1 * o.tank_rms_a * cos(phi));
    o.p_in_w = o.p_inv_w / 0.93f;
    o.r_lag_ohm = (float)(k->v1 / o.tank_rms_a * cos(phi));
    return o;
}

/* Halves (from the current state of T) until the loop returns TF_STOP_NO_PAN, 0 if it does not
 * within max_halves. The run() invariants hold on the way. */
static unsigned halves_to_stop(const tank_t *k, const tank_freq_cfg_t *c, const tank_freq_limits_t *lim,
                               unsigned max_halves, double err_deg)
{
    for (unsigned n = 0; n < max_halves; n++) {
        uint32_t f0 = T.f_hz;
        tank_freq_obs_t o = observe_err(k, f0, err_deg);
        assert(o.tank_rms_a < tank_rms_trip_for(lim->ceiling_a));
        tank_freq_reason_t r = tank_freq_step(&T, c, lim, &o);
        if (r == TF_STOP_NO_PAN) return n + 1;
        uint32_t d = T.f_hz > f0 ? T.f_hz - f0 : f0 - T.f_hz;
        assert(d <= c->step_up_hz && T.f_hz >= c->f_min_hz && T.f_hz <= c->f_max_hz);
    }
    return 0;
}

static const double LAG_ERR_DEG[] = {-2.5, -1, 0, 1, 2.5};
#define HALVES_PER_S 120u
#define UL858_47_8_HALVES (30u * HALVES_PER_S) /* off within 30 s of vessel removal */

/* The empty coil of record stops within 2 s (+ the walk to where the lag error still leaves it
 * under 0.5 ohm), at every line / bank corner and lag error, whatever the ceiling. */
static bool empty_coil_stops(const tank_freq_cfg_t *c)
{
    for (unsigned li = 0; li < 3; li++)
        for (unsigned k = 0; k < 3; k++)
            for (unsigned e = 0; e < sizeof LAG_ERR_DEG / sizeof LAG_ERR_DEG[0]; e++)
                for (unsigned ci = 0; ci < 2; ci++) {
                    tank_t np = plant(&NO_PAN, LINES_V[li], BANK_F[k]);
                    tank_freq_limits_t lim = limits(ci ? 28.0f : TANK_CEILING_DEFAULT_A);
                    tank_freq_reset(&T, c);
                    unsigned n = halves_to_stop(&np, c, &lim, UL858_47_8_HALVES, LAG_ERR_DEG[e]);
                    if (n == 0) return false;
                    /* Evidence from the first half within +/-1 deg; at -2.5 deg only below ~45 kHz. */
                    assert(n >= c->no_pan_halves && n <= c->no_pan_halves + 2 * HALVES_PER_S);
                    if (fabs(LAG_ERR_DEG[e]) <= 1.0) assert(n <= c->no_pan_halves + HALVES_PER_S / 2);
                    assert(!T.pan_present && T.no_pan_stopped && T.f_hz == c->f_max_hz);
                }
    return true;
}

static void test_no_pan_stop(void)
{
    /* Positive: the empty coil stops (it held 11.7-16.1 A at 35 kHz indefinitely before, F1). */
    assert(empty_coil_stops(&C));
    /* Held: every later half returns the stop and the f_max target, whatever it observes. */
    tank_t np = plant(&NO_PAN, 120, 0.5e-6);
    tank_t pan = plant(&HEATABLE[1], 120, 0.5e-6);
    tank_freq_limits_t lim = limits(TANK_CEILING_DEFAULT_A);
    tank_freq_reset(&T, &C);
    assert(halves_to_stop(&np, &C, &lim, 1000, 0) == C.no_pan_halves);
    for (unsigned n = 0; n < 50; n++) {
        tank_freq_obs_t o = observe(&pan, 40000);
        assert(tank_freq_step(&T, &C, &lim, &o) == TF_STOP_NO_PAN && T.f_hz == C.f_max_hz);
    }
    tank_freq_reset(&T, &C); /* the binding resets the loop whenever the bridge is off */
    assert(!T.no_pan_stopped && T.no_pan_count == 0);

    /* Pan lifted mid-cook: every heatable plant settled at every corner, then the plant becomes the
     * empty coil at that frequency. The stop follows no_pan_halves later (UL 858 47.8: 30 s). */
    for (unsigned p = 0; p < sizeof HEATABLE / sizeof HEATABLE[0]; p++)
        for (unsigned li = 0; li < 3; li++)
            for (unsigned k = 0; k < 3; k++)
                for (unsigned e = 1; e < 4; e++) { /* -1, 0, +1 deg */
                    tank_t hp = plant(&HEATABLE[p], LINES_V[li], BANK_F[k]);
                    tank_t lifted = plant(&NO_PAN, LINES_V[li], BANK_F[k]);
                    tank_freq_reset(&T, &C);
                    assert(halves_to_stop(&hp, &C, &lim, 1200, LAG_ERR_DEG[e]) == 0);
                    unsigned n = halves_to_stop(&lifted, &C, &lim, UL858_47_8_HALVES, LAG_ERR_DEG[e]);
                    assert(n >= C.no_pan_halves && n <= C.no_pan_halves + HALVES_PER_S / 2);
                }

    /* Negative: no heatable plant stops over 30 s, at any corner, ceiling or lag error up to
     * 2.5 deg (the priors 1 ohm pan reads 0.72 ohm or more at 60 kHz with +1 deg, and its stop
     * lag is under 84 deg). */
    for (unsigned p = 0; p < sizeof HEATABLE / sizeof HEATABLE[0]; p++)
        for (unsigned li = 0; li < 3; li++)
            for (unsigned k = 0; k < 3; k++)
                for (unsigned e = 0; e < sizeof LAG_ERR_DEG / sizeof LAG_ERR_DEG[0]; e++)
                    for (unsigned ci = 0; ci < 2; ci++) {
                        tank_t hp = plant(&HEATABLE[p], LINES_V[li], BANK_F[k]);
                        tank_freq_limits_t l = limits(ci ? 22.0f : TANK_CEILING_DEFAULT_A);
                        tank_freq_reset(&T, &C);
                        assert(halves_to_stop(&hp, &C, &l, UL858_47_8_HALVES, LAG_ERR_DEG[e]) == 0);
                        assert(!T.no_pan_stopped);
                    }
    /* The other pans this file uses (1.4 / 2.0 / 2.5 / 3.5 ohm) do not stop either. */
    static const tank_t others[] = {{55e-6, 0.5e-6, 1.4, 108}, {55e-6, 0.5e-6, 2.0, 108},
                                    {60e-6, 0.5e-6, 2.5, 108}, {55e-6, 0.5e-6, 3.5, 108}};
    for (unsigned i = 0; i < 4; i++) {
        tank_freq_limits_t l = limits(22);
        tank_freq_reset(&T, &C);
        assert(halves_to_stop(&others[i], &C, &l, UL858_47_8_HALVES, 0) == 0);
    }

    /* A half without a lag, or an invalid one, holds the count; a measured non-evidence half
     * clears it. */
    tank_freq_reset(&T, &C);
    assert(halves_to_stop(&np, &C, &lim, 100, 0) == 0 && T.no_pan_count == 100);
    tank_freq_obs_t o = observe(&np, T.f_hz);
    o.phase_valid = false;
    for (unsigned n = 0; n < 30; n++) (void)tank_freq_step(&T, &C, &lim, &o);
    tank_freq_obs_t bad = {.valid = false};
    for (unsigned n = 0; n < 30; n++) (void)tank_freq_step(&T, &C, &lim, &bad);
    assert(T.no_pan_count == 100 && !T.no_pan_stopped);
    assert(halves_to_stop(&np, &C, &lim, 1000, 0) == C.no_pan_halves - 100);
    tank_freq_reset(&T, &C);
    assert(halves_to_stop(&np, &C, &lim, 200, 0) == 0);
    o = observe(&pan, T.f_hz); /* one pan-like half (lag 48 deg) */
    (void)tank_freq_step(&T, &C, &lim, &o);
    assert(T.no_pan_count == 0);
    /* Too little current to judge (below no_pan_min_rms_a) is not evidence. */
    tank_t weak = np;
    weak.v1 = 0.9 * 50;
    tank_freq_reset(&T, &C);
    o = observe(&weak, 60000);
    assert(o.tank_rms_a < C.no_pan_min_rms_a && o.phase_valid);
    (void)tank_freq_step(&T, &C, &lim, &o);
    assert(T.no_pan_count == 0);
    /* No R from the lag (line RMS unknown): no information, the count holds. */
    tank_freq_reset(&T, &C);
    assert(halves_to_stop(&np, &C, &lim, 50, 0) == 0 && T.no_pan_count == 50);
    o = observe(&np, T.f_hz);
    o.r_lag_ohm = NAN;
    (void)tank_freq_step(&T, &C, &lim, &o);
    assert(T.no_pan_count == 50);
    /* The overrun latch still wins: a stop never masks it. */
    tank_freq_reset(&T, &C);
    T.no_pan_count = C.no_pan_halves;
    T.overrun = C.overrun_halves;
    o = observe(&np, 60000);
    o.tank_rms_a = 19.0f; /* above 1.05 x 17.5 A */
    assert(tank_freq_step(&T, &C, &lim, &o) == TF_FAULT_OVERRUN);

    /* Negative control: with the stop off the same empty-coil check fails (the clamp alone holds
     * the coil at the floor for the whole 30 s). */
    tank_freq_cfg_t off = C;
    off.no_pan_stop = false;
    assert(!empty_coil_stops(&off));
    tank_freq_reset(&T, &off);
    assert(halves_to_stop(&np, &off, &lim, UL858_47_8_HALVES, 0) == 0 && T.f_hz == 35000 &&
           T.reason == TF_HOLD_FLOOR_MIN);
    tests++;
}

static void test_no_pan_config(void)
{
    /* Defaults are config.yaml's (TANK_NO_PAN_*). */
    assert(C.no_pan_stop && C.no_pan_lag_deg == TANK_NO_PAN_LAG_DEG && C.no_pan_r_max_ohm == TANK_NO_PAN_R_MAX_OHM &&
           C.no_pan_min_rms_a == TANK_NO_PAN_MIN_RMS_A && C.no_pan_halves == TANK_NO_PAN_STOP_HALVES);
    /* Within UL 858 47.8's 30 s, with margin. */
    assert(TANK_NO_PAN_STOP_HALVES < UL858_47_8_HALVES / 10);
    tank_freq_cfg_t c;
    c = C; c.no_pan_lag_deg = C.fit_lag_max_deg; assert(!tank_freq_config_ok(&c)); /* overlaps the fit */
    c = C; c.no_pan_lag_deg = 89.6f; assert(!tank_freq_config_ok(&c));
    c = C; c.no_pan_lag_deg = NAN; assert(!tank_freq_config_ok(&c));
    c = C; c.no_pan_r_max_ohm = C.pan_r_min_ohm + 0.01f; assert(!tank_freq_config_ok(&c)); /* overlaps pan */
    c = C; c.no_pan_r_max_ohm = 0; assert(!tank_freq_config_ok(&c));
    c = C; c.no_pan_min_rms_a = 0.5f; assert(!tank_freq_config_ok(&c));
    c = C; c.no_pan_halves = 0; assert(!tank_freq_config_ok(&c));
    c = C; c.no_pan_halves = 3001; assert(!tank_freq_config_ok(&c)); /* > 25 s */
    c = C; c.no_pan_stop = false; assert(tank_freq_config_ok(&c));
    tests++;
}

/* ------------------------------------------------------------------ start transient (F3) */
/* Why the loop has no pre-start pan probe (coil study F3), in numbers this test reproduces.
 * Time-domain series RLC (constant L, R, C per plant) driven by the bridge, starting from rest.
 * With the bridge idle the 9 uF film bus holds the line peak (power-stage DECISIONS 2026-10-06:
 * "with the bridge idle, the film bus capacitors hold the line peak"; 9 uF since stage 14,
 * 2026-10-09), so a start at any line phase sees the full bus, 1.414 x line, not |v_line|.
 *   BUS_DROOP: the 9 uF bus discharging into the bridge, no rectifier recharge (a start at a line
 *     zero: the least energy any start can have), for claims that a current is at least X.
 *   BUS_STIFF: an ideal bus at the line peak, for claims that a current stays below X.
 * After the drive ends the switches are off and the body diodes clamp the bridge to -sign(i) x bus
 * until the current reaches zero (then it stays there), or, in RING mode, both low sides conduct
 * and the tank rings freely (a primitive the HAL does not have; for the recommendation only).
 * Sampling it would have to beat (n21_hw_esp32.c, controller DECISIONS C12 / C19): ADC1 at 80 kS/s
 * in a 9-slot pattern with CT_MON in slots 1 and 3, i.e. CT_MON samples 25 us then 87.5 us apart;
 * 64-result frames of 0.8 ms read by the acquisition context every 625 us; the AD8436 settles in
 * ~3.4 ms to 0.1 % (tau ~0.49 ms; controller README "Settling"). */
#define BUS_C_F 9e-6
#define CT_BAND_LO_A 64.55
#define CT_MON_GAP_MIN_US 25.0
#define AD8436_TAU_US 490.0
#define F_START_HZ (80e6 / 1334) /* f_max's cycle: bridge_plan_cycle(80 MHz, 60 kHz) = 1334 ticks */
typedef enum { BUS_STIFF, BUS_DROOP } bus_t;
typedef enum { END_DIODES, END_RING } end_t;
typedef struct { double i_pk, t_pk_us, above_trip_us, ring_f_hz; unsigned ring_edges; } transient_t;

static transient_t start_transient(const plant_t *p, double c_f, double line_v, double drive_us,
                                   bus_t bus, end_t end, double window_us)
{
    const double dt = 5e-9, T = 1.0 / F_START_HZ, trip = tank_peak_trip_for(TANK_CEILING_DEFAULT_A);
    double vb = 1.41421356 * line_v, i = 0, vc = 0;
    transient_t r = {0};
    int sign = 0;
    bool armed = false, done = false;
    double t_first = 0, t_last = 0;
    for (double t = 0; t < window_us * 1e-6; t += dt) {
        double v, ib;
        if (t < drive_us * 1e-6) {
            double s = fmod(t, T) < T / 2 ? 1.0 : -1.0;
            v = s * vb;
            ib = s * i;
        } else if (end == END_RING) {
            v = 0;
            ib = 0;
        } else {
            if (done || fabs(i) < 1e-3) { done = true; i = 0; continue; }
            double s = i > 0 ? -1.0 : 1.0;
            v = s * vb;
            ib = s * i;
            if ((i > 0) != (i + (v - p->R * i - vc) / p->L * dt > 0)) done = true; /* reached zero */
        }
        i += (v - p->R * i - vc) / p->L * dt; /* semi-implicit Euler: i first, then vc with it */
        vc += i / c_f * dt;
        if (bus == BUS_DROOP) vb -= ib / BUS_C_F * dt;
        if (fabs(i) > r.i_pk) { r.i_pk = fabs(i); r.t_pk_us = t * 1e6; }
        if (fabs(i) > trip) r.above_trip_us += dt * 1e6;
        if (end == END_RING && t >= drive_us * 1e-6) { /* CT_ZC-like edges with 1 A hysteresis */
            int sg = i > 0 ? 1 : -1;
            if (fabs(i) > 1.0) armed = true;
            if (armed && sign && sg != sign) {
                if (!r.ring_edges) t_first = t;
                t_last = t;
                r.ring_edges++;
                armed = false;
            }
            sign = sg;
        }
    }
    if (r.ring_edges >= 3) r.ring_f_hz = (r.ring_edges - 1) / 2.0 / (t_last - t_first);
    return r;
}

static void test_start_transient_evidence(void)
{
    const plant_t AL180 = {"aluminium 180 mm", 30.8e-6, 0.28}; /* 30.8 uH, 0.17 + 0.11 ohm */
    const double half_pulse_us = 0.5e6 / F_START_HZ;           /* one bridge pulse, 8.34 us */
    const double trip = tank_peak_trip_for(TANK_CEILING_DEFAULT_A);
    printf("  start transient from the held bus (peak A at 132 V, C -5 %% / +5 %%):\n");
    for (unsigned k = 0; k < 2; k++) {
        double c_f = BANK_F[2 * k];
        /* 1. A continuous start (the loop's first half, or any "short session" at f_max) puts
         *    aluminium over the CT band (240 mm) or the firmware peak trip (180 mm) within 40 us,
         *    even from the least-energy start, at every line: 16 x faster than one acquisition
         *    period, so no firmware early abort can land before it. */
        for (unsigned li = 0; li < 3; li++) {
            transient_t a = start_transient(&ALUMINIUM, c_f, LINES_V[li], 400, BUS_DROOP, END_DIODES, 400);
            transient_t b = start_transient(&AL180, c_f, LINES_V[li], 400, BUS_DROOP, END_DIODES, 400);
            assert(a.i_pk > CT_BAND_LO_A && a.t_pk_us < 40 && b.i_pk > trip && b.t_pk_us < 40);
            if (li == 2) printf("    continuous: %s %.0f A at %.0f us, %s %.0f A at %.0f us\n", ALUMINIUM.name,
                                a.i_pk, a.t_pk_us, AL180.name, b.i_pk, b.t_pk_us);
        }
        /* 2. Only a single pulse stays under every trip for every load (stiff bus, the upper
         *    bound); two pulses already put aluminium 240 mm over the firmware trip, and into the CT
         *    band at 132 V. */
        transient_t one = start_transient(&ALUMINIUM, c_f, 132, half_pulse_us, BUS_STIFF, END_DIODES, 100);
        transient_t two = start_transient(&ALUMINIUM, c_f, 132, 2 * half_pulse_us, BUS_DROOP, END_DIODES, 100);
        assert(one.i_pk < trip && two.i_pk > CT_BAND_LO_A);
        for (unsigned li = 0; li < 3; li++)
            assert(start_transient(&ALUMINIUM, c_f, LINES_V[li], 2 * half_pulse_us, BUS_DROOP, END_DIODES, 100).i_pk > trip);
        printf("    one pulse: %s %.1f A; two pulses %.1f A\n", ALUMINIUM.name, one.i_pk, two.i_pk);
        /* 3. A single pulse cannot be measured: it is shorter than the shortest CT_MON gap, and the
         *    AD8436 would see under 2 % of it. Its peak per volt barely separates the loads either
         *    (against carbon steel mu-low: aluminium 180 mm 1.2 x, 240 mm 1.4 x, which the CT_MON, VBUS
         *    and bank tolerances would have to resolve from one sample). */
        assert(half_pulse_us < CT_MON_GAP_MIN_US / 2 && half_pulse_us / AD8436_TAU_US < 0.02);
        double y180 = start_transient(&AL180, c_f, 132, half_pulse_us, BUS_STIFF, END_DIODES, 100).i_pk;
        double ycs = start_transient(&HEATABLE[0], c_f, 132, half_pulse_us, BUS_STIFF, END_DIODES, 100).i_pk;
        assert(y180 / ycs < 1.25 && one.i_pk / ycs < 1.45);
        /* 4. The heatable pans' own start transient: under the trip, except carbon steel mu-low at
         *    132 V, a few us over 41 A (a CT_MON sample catches it in a few per cent of starts:
         *    a possible nuisance TANK_PEAK latch at a start; reported, not changed). */
        for (unsigned p = 0; p < sizeof HEATABLE / sizeof HEATABLE[0]; p++) {
            transient_t h = start_transient(&HEATABLE[p], c_f, 132, 400, BUS_STIFF, END_DIODES, 400);
            assert(h.i_pk < CT_BAND_LO_A);
            if (p == 0) assert(h.i_pk > trip && h.above_trip_us < 10);
            else assert(h.i_pk < trip);
            printf("    continuous: %-20s %.1f A (%.1f us over %.1f A)\n", HEATABLE[p].name, h.i_pk, h.above_trip_us, trip);
        }
        transient_t np = start_transient(&NO_PAN, c_f, 132, 400, BUS_STIFF, END_DIODES, 400);
        assert(np.i_pk < trip);
        /* 5. What would work (recommendation, not implemented): one short pulse, then both low
         *    sides on so the tank rings, and CT_ZC edges counted. The ring frequency is f_res:
         *    aluminium 240 mm 45-48 kHz against <= 41 kHz for every ferrous pan and 25-26 kHz with
         *    no pan, and aluminium rings longest. With a full half-period pulse the ring reaches
         *    ~49 A on aluminium, so the pulse must be shorter than the bridge's half period: a PWM
         *    pattern the HAL does not have. */
        transient_t ra = start_transient(&ALUMINIUM, c_f, 132, half_pulse_us, BUS_STIFF, END_RING, 220);
        transient_t rn = start_transient(&NO_PAN, c_f, 132, half_pulse_us, BUS_STIFF, END_RING, 220);
        assert(ra.ring_f_hz > 44000 && rn.ring_f_hz < 27000 && ra.i_pk > trip);
        for (unsigned p = 0; p < sizeof HEATABLE / sizeof HEATABLE[0]; p++) {
            transient_t rh = start_transient(&HEATABLE[p], c_f, 132, half_pulse_us, BUS_STIFF, END_RING, 220);
            assert(rh.ring_f_hz < 42000 && rh.ring_edges < ra.ring_edges);
        }
        printf("    ring-down: %s %.1f kHz %u edges, peak %.1f A; no pan %.1f kHz\n", ALUMINIUM.name,
               ra.ring_f_hz / 1e3, ra.ring_edges, ra.i_pk, rn.ring_f_hz / 1e3);
    }
    tests++;
}

static void test_reset(void)
{
    tank_t k = {.L = 55e-6, .C = 0.5e-6, .R = 1.4, .v1 = 108};
    tank_freq_limits_t lim = limits(26);
    tank_freq_reset(&T, &C);
    (void)run(&k, &C, &lim, &T, 400, NULL);
    tank_freq_reset(&T, &C);
    assert(T.f_hz == 60000 && !T.have_fit && !T.pan_present && T.ceiling_eff_a == TANK_CEILING_DEFAULT_A);
    tests++;
}

int main(void)
{
    C = tank_freq_default();
    test_trip_derivation();
    test_config_caps();
    test_fit();
    test_stop_floor_min();
    test_stop_zvs();
    test_stop_rms();
    test_stop_inlet();
    test_stop_peak();
    test_up_on_violation();
    test_fault_inputs();
    test_no_pan_clamp();
    test_power_tracking();
    test_power_steps();
    test_power_no_chatter();
    test_power_below_fmax_minimum();
    test_coil_of_record_heatable();
    test_coil_of_record_special_loads_baseline();
    test_no_pan_stop();
    test_no_pan_config();
    test_start_transient_evidence();
    test_reset();
    printf("tank_freq: %u tests passed\n", tests);
    return 0;
}
