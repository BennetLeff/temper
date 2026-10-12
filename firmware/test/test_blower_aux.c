/* Stage-16 blower supply PS3: the inlet allowance scheduled from the blower drive (blower_aux.c),
 * power-stage DECISIONS 16 and stage-16 PLAN section 5 (budget16.py). Assertions are the oracle
 * (built with -UNDEBUG).
 *  - the model against its sources: the C28 drive map (recomputed over its corners), Delta's
 *    32.4 W maximum, IRM-60-15 efficiency and AC current, budget16.py's 1.27 A at full blower;
 *  - the allowance at blower off / slowest / typical / fan-law cap / full / unknown;
 *  - the schedule: allowance first on a speed-up, at once on a fault, released late on a
 *    slow-down, worst case on every unknown;
 *  - closed loop with the real frequency loop (tank_freq.c) on a first-harmonic RLC pan held at the
 *    inlet limit: a blower step-up never takes the real inlet over 13.5 A, never puts the PS3 draw
 *    above the allowance in force, and never trips the adapter's 15 A bound;
 *  - the tank hold at typical and full blower, 108 / 120 / 132 V;
 *  - C33: BLW_PG = 0 (PS3 absent) never lowers the allowance. */
#include "blower_aux.h"
#include "input_limits.h"
#include "tank_freq.h"
#include "thermal_mgmt.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static unsigned tests;
#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))
#define PI 3.14159265358979

static blower_aux_cfg_t C;

/* drive -> commanded duty through the firmware's own map (thermal_mgmt.c). */
static float duty_of(float drive) { return blower_pwm_duty_from_drive(drive); }
static float level_drive(float drive) { return blower_aux_level_a(&C, true, duty_of(drive)); }

/* C28 buck output over its 32 corners (as test_thermal_mgmt.c blower_vout_band). */
static double vout_corner_max(double duty)
{
    double hi = -1e9;
    for (unsigned m = 0; m < 32; m++) {
        double vfb = (m & 1u) ? 0.812 : 0.788, vh = (m & 2u) ? 3.367 : 3.242;
        double rt = 140e3 * ((m & 4u) ? 1.001 : 0.999), rb = 11.5e3 * ((m & 8u) ? 1.001 : 0.999);
        double ri = 68.3e3 * ((m & 16u) ? 1.01 : 0.99);
        double v = vfb + rt * (vfb / rb - (duty * vh - vfb) / ri);
        if (v > hi) hi = v;
    }
    return hi;
}

/* ------------------------------------------------------------------ model */
static void test_config(void)
{
    assert(blower_aux_config_ok(&C) && !blower_aux_config_ok(NULL));
    blower_aux_cfg_t b = C; b.ps3_pf = 0; assert(!blower_aux_config_ok(&b));
    b = C; b.ps3_eta = 1.2f; assert(!blower_aux_config_ok(&b));
    b = C; b.fan_law_exp = NAN; assert(!blower_aux_config_ok(&b));
    b = C; b.margin = -0.1f; assert(!blower_aux_config_ok(&b));
    b = C; b.urgent_a_per_s = 1.0f; assert(!blower_aux_config_ok(&b));    /* urgent >= normal rise */
    b = C; b.lead_ms = 50u; assert(!blower_aux_config_ok(&b));            /* < one blower tick */
    b = C; b.p_rated_max_w = 200.0f; assert(!blower_aux_config_ok(&b));   /* worst case >= 5 A */
    /* Off is confirmed against the stall threshold the blower controller uses. */
    assert(C.off_rpm == BLOWER_STALL_RPM);
    /* input_limits takes its static part and its worst case from here. */
    input_limits_cfg_t l = input_limits_native21();
    assert(input_limits_config_ok(&l));
    assert(l.aux_min_a == C.base_a && l.aux_min_a == 1.3f);
    assert(NEAR(l.aux_max_a, blower_aux_worst_a(&C), 1e-6));
    input_limits_cfg_t bad = l; bad.aux_min_a = l.aux_max_a + 0.1f; assert(!input_limits_config_ok(&bad));
    bad = l; bad.aux_min_a = NAN; assert(!input_limits_config_ok(&bad));
    tests++;
}

static void test_model_sources(void)
{
    /* IRM-60-SPEC p.2: PF implied by 1.8 A at 115 Vac, 60 W out at 89 %. */
    assert(NEAR(C.ps3_pf, 0.3257, 1e-4));
    /* Drive map: the model is an upper bound on the C28 buck output at every duty the firmware can
     * command (0 .. BLOWER_PWM_DUTY_MAX), and tight (< 60 mV above the corner envelope). */
    for (float d = 0; d <= BLOWER_PWM_DUTY_MAX + 1e-6f; d += 0.01f) {
        double env = vout_corner_max(d), v = blower_aux_vout_max_v(&C, d);
        assert(v >= env - 1e-4 && v - env < 0.06);
    }
    assert(NEAR(blower_aux_vout_max_v(&C, 0), 12.40, 1e-6));
    assert(blower_aux_vout_max_v(&C, NAN) == C.vout_max_v && blower_aux_vout_max_v(&C, -1) == C.vout_max_v);
    /* Anchor: Delta's maximum 32.4 W at 12 V -> 36 W out of PS3 -> 1.8 A x 115/108 x 36/60 at 108 V. */
    assert(NEAR(blower_aux_ps3_model_a(&C, 12.0f), 1.8 * 115.0 / 108.0 * 36.0 / 60.0, 1e-4));
    /* Full blower at the 12.40 V corner: 35.7 W, budget16.py's 1.27 A of PS3 input. */
    double p12 = 32.4 * pow(12.4 / 12.0, 3);
    assert(NEAR(p12, 35.75, 0.01));
    assert(NEAR(blower_aux_ps3_model_a(&C, 12.40f), 1.27, 0.005));
    assert(NEAR(blower_aux_worst_a(&C), 2.569, 0.002));
    /* Fan law V^3: half the voltage, an eighth of the current. */
    assert(NEAR(blower_aux_ps3_model_a(&C, 6.0f), blower_aux_ps3_model_a(&C, 12.0f) / 8, 1e-5));
    tests++;
}

static void test_allowance_points(void)
{
    float worst = blower_aux_worst_a(&C);
    float off = blower_aux_level_a(&C, false, 0.0f);
    float slowest = level_drive(0.0f), typical = level_drive(0.5f), cap = level_drive(FAN_DRIVE_CAP);
    float full = level_drive(1.0f);
    float unknown = blower_aux_level_a(&C, true, NAN);
    /* "Typical": drive 0.5 puts the blower at <= 9.61 V, where the max-anchored fan law gives
     * 16.6 W, Delta's typical 17.0 W rating. */
    double v_typ = blower_aux_vout_max_v(&C, duty_of(0.5f));
    double p_typ = C.p_rated_max_w * pow(v_typ / C.v_rated_v, 3);
    printf("  aux allowance: off %.3f, slowest (drive 0) %.3f, typical (drive 0.5, %.2f V, %.1f W) %.3f,\n"
           "                 fan-law cap (drive %.1f) %.3f, full %.3f, unknown %.3f A\n",
           off, slowest, v_typ, p_typ, typical, (double)FAN_DRIVE_CAP, cap, full, unknown);
    assert(NEAR(off, 1.35, 1e-5));                       /* PS1 + PS2 + PS3 idle */
    assert(NEAR(slowest, 1.592, 0.002));
    assert(p_typ > 16.0 && p_typ < 17.1 && NEAR(typical, 2.029, 0.002));
    assert(NEAR(cap, 2.449, 0.002));
    assert(full == worst && unknown == worst);
    assert(blower_aux_level_a(&C, true, -0.1f) == worst && blower_aux_level_a(&C, true, 1.5f) == worst);
    assert(blower_aux_level_a(&C, true, INFINITY) == worst);
    /* Monotonic in drive, between off and the worst case; the margin is never below the model. */
    float prev = off;
    for (float d = 0; d <= 1.0001f; d += 0.05f) {
        float a = level_drive(d);
        assert(a >= prev && a <= worst);
        double model = C.base_a + blower_aux_ps3_model_a(&C, blower_aux_vout_max_v(&C, duty_of(d)));
        assert(a >= model - 1e-5);
        prev = a;
    }
    tests++;
}

/* ------------------------------------------------------------------ schedule */
static blower_aux_out_t tick(blower_aux_t *s, bool on, float drive, bool urgent, bool known, float rpm,
                             uint32_t now)
{
    blower_aux_in_t in = {.on = on, .duty = on ? duty_of(drive) : 0.0f, .urgent = urgent, .known = known,
                          .tach_rpm = rpm};
    blower_aux_out_t o = blower_aux_step(s, &C, &in, now);
    /* The invariant: the blower as applied never needs more than the allowance (fault path aside). */
    if (!urgent && known) assert(blower_aux_level_a(&C, o.on, o.duty) <= o.allowance_a + 1e-5f);
    return o;
}

static void test_schedule(void)
{
    float worst = blower_aux_worst_a(&C), off = blower_aux_level_a(&C, false, 0);
    blower_aux_t s;
    blower_aux_init(&s, &C);
    /* Boot: worst case, blower at its reset state (on, full). The first write is unknown. */
    blower_aux_out_t o = tick(&s, false, 0, false, false, NAN, 0);
    assert(o.allowance_a == worst && !o.on);
    /* Off commanded but the tach has no reading yet, or still shows the blower turning: worst. */
    uint32_t t = 100;
    o = tick(&s, false, 0, false, true, NAN, t);
    assert(o.target_a == worst && o.allowance_a == worst);
    o = tick(&s, false, 0, false, true, 2500.0f, t += 100);
    assert(o.target_a == worst);
    /* Stopped: the allowance is released release_ms later, at fall_a_per_s. */
    o = tick(&s, false, 0, false, true, 0.0f, t += 100);
    uint32_t t_stop = t;
    assert(o.target_a == off && o.allowance_a == worst);
    while (t - t_stop < C.release_ms) {
        o = tick(&s, false, 0, false, true, 0.0f, t += 100);
        if (t - t_stop < C.release_ms) assert(o.allowance_a == worst);
    }
    for (unsigned n = 0; n < 40; n++) o = tick(&s, false, 0, false, true, 0.0f, t += 100);
    assert(o.allowance_a == off);

    /* Speed-up, off -> drive 0.5: the blower waits; the allowance rises at rise_a_per_s per tick
     * and the blower starts lead_ms after it reached the level. */
    float need = level_drive(0.5f);
    uint32_t t0 = t, t_reached = 0, t_on = 0;
    for (unsigned n = 0; n < 30; n++) {
        float before = s.allowance_a;
        o = tick(&s, true, 0.5f, false, true, 0.0f, t += 100);
        assert(o.allowance_a - before <= C.rise_a_per_s * 0.1f + 1e-5f);
        if (!t_reached && o.allowance_a >= need) t_reached = t;
        if (!t_on && o.on) t_on = t;
        if (!o.on) assert(o.holding);
    }
    assert(t_reached && t_on && t_on - t_reached >= C.lead_ms && t_on - t_reached < C.lead_ms + 100);
    assert(o.on && o.duty == duty_of(0.5f) && o.allowance_a == need && !o.holding);
    printf("  speed-up off -> drive 0.5: allowance %.2f -> %.2f A in %u ms, blower released at %u ms\n",
           off, need, (unsigned)(t_reached - t0), (unsigned)(t_on - t0));
    /* Further up to the fan-law cap: same, from a running blower (the old drive is kept meanwhile). */
    for (unsigned n = 0; n < 2; n++) {
        o = tick(&s, true, FAN_DRIVE_CAP, false, true, 2000.0f, t += 100);
        assert(o.on && o.duty == duty_of(0.5f) && o.holding);
    }
    for (unsigned n = 0; n < 20; n++) o = tick(&s, true, FAN_DRIVE_CAP, false, true, 2000.0f, t += 100);
    assert(o.duty == duty_of(FAN_DRIVE_CAP) && o.allowance_a == level_drive(FAN_DRIVE_CAP));

    /* Slow-down: the blower at once, the allowance after release_ms. */
    o = tick(&s, true, 0.2f, false, true, 2000.0f, t += 100);
    assert(o.duty == duty_of(0.2f) && o.allowance_a == level_drive(FAN_DRIVE_CAP));
    for (unsigned n = 0; n < 60; n++) o = tick(&s, true, 0.2f, false, true, 1500.0f, t += 100);
    assert(o.allowance_a == level_drive(0.2f));

    /* Fault (urgent): full speed now, the allowance follows at urgent_a_per_s, no hold. */
    o = tick(&s, true, 1.0f, true, true, 1500.0f, t += 100);
    assert(o.on && o.duty == 0.0f && !o.holding && o.target_a == worst);
    o = tick(&s, true, 1.0f, true, true, 1500.0f, t += 100);
    assert(o.allowance_a == worst);
    /* Back to normal: drops after the release. */
    for (unsigned n = 0; n < 60; n++) o = tick(&s, true, 0.2f, false, true, 1500.0f, t += 100);
    assert(o.allowance_a == level_drive(0.2f));

    /* Unknown (failed write, or a stalled blower): worst case and no hold, whatever is commanded. */
    o = tick(&s, true, 0.2f, false, false, 1500.0f, t += 100);
    assert(o.target_a == worst && o.allowance_a > level_drive(0.2f) && !o.holding);
    o = tick(&s, true, 0.2f, false, false, 0.0f, t += 100);
    assert(o.allowance_a == worst);
    /* NaN duty while on: worst, applied as full speed. */
    blower_aux_in_t in = {.on = true, .duty = NAN, .known = true, .tach_rpm = 0};
    o = blower_aux_step(&s, &C, &in, t += 100);
    assert(o.target_a == worst && o.on && o.duty == 0.0f);
    /* A clock that jumps does not ramp more than one second's worth. */
    blower_aux_init(&s, &C);
    (void)tick(&s, false, 0, false, true, 0.0f, 0);
    for (unsigned n = 0; n < 40; n++) (void)tick(&s, false, 0, false, true, 0.0f, 1000u + 100u * n);
    assert(s.allowance_a == off);
    o = tick(&s, true, 0.5f, false, true, 0.0f, 0xFFFFFF00u);
    assert(o.allowance_a <= off + C.rise_a_per_s * 1.0f + 1e-5f && !o.on);
    tests++;
}

/* ------------------------------------------------------------------ closed loop */
/* First-harmonic series RLC (test_tank_freq.c's plant): the high-R pan whose 13.5 A inlet hold
 * binds first. Line 120 V; the power-stage estimate is exact here (est_error is the margin). */
typedef struct { double L, C, R, v1; } tank_t;
static const tank_t PAN = {.L = 55e-6, .C = 0.5e-6, .R = 3.5, .v1 = 108};
#define LINE_V 120.0
#define BASE_REAL_A 1.278 /* PS1 + PS2 at 108 V (budget16.py), under the 1.3 A allowance */

static double p_tank(uint32_t f)
{
    double w = 2 * PI * f, x = w * PAN.L - 1.0 / (w * PAN.C), i = PAN.v1 / hypot(PAN.R, x);
    return i * i * PAN.R;
}

typedef struct {
    double max_real_a, max_bound_a, min_margin_a; /* min over halves of in-force - (base + PS3) */
    double settled_bound_a;
    unsigned lead_halves; /* halves with the PS3 draw above the allowance in force */
} loop_result_t;

/* Settles at the inlet hold with the blower off (stopped), then commands `drive` (urgent or not)
 * and runs 6 s. gate=false applies the blower command at once while the allowance still rises
 * at rise_a_per_s (no allowance-first): the comparison that shows the gate matters. */
static loop_result_t run_step(float drive, bool urgent, bool gate)
{
    input_limits_cfg_t lim_cfg = input_limits_native21();
    tank_freq_cfg_t fc = tank_freq_default();
    tank_freq_t tf;
    tank_freq_reset(&tf, &fc);
    tank_freq_limits_t lim = {.ceiling_a = 28, .inlet_max_a = 13.5f, .peak_trip_a = tank_peak_trip_for(28),
                              .request_w = 1e6f};
    blower_aux_t s;
    blower_aux_init(&s, &C);
    float in_force = lim_cfg.aux_max_a, sched = lim_cfg.aux_max_a;
    bool on = false;
    float duty = 0;
    loop_result_t r = {.min_margin_a = 1e9};
    const unsigned halves_per_tick = 12; /* 100 ms blower tick, 8.33 ms halves */
    const unsigned settle = 1200, total = settle + 720;
    for (unsigned h = 0; h < total; h++) {
        uint32_t now_ms = (uint32_t)(h * 1000.0 / 120.0);
        if (h % halves_per_tick == 0) {
            bool step = h >= settle;
            blower_aux_in_t in = {.on = step, .duty = step ? duty_of(drive) : 0.0f, .urgent = step && urgent,
                                  .known = true, .tach_rpm = (on ? 2000.0f : 0.0f)};
            blower_aux_out_t o = blower_aux_step(&s, &C, &in, now_ms);
            sched = o.allowance_a;
            on = gate ? o.on : in.on;
            duty = gate ? o.duty : in.duty;
        }
        in_force = input_limits_aux_ramp(&lim_cfg, in_force, sched, 0.05f); /* n21 binding, per half */
        /* Plant, worst for the inlet: the blower draws its new (unmargined, max-anchored) power the
         * moment it is applied, with no spin-up. */
        double ps3 = on ? blower_aux_ps3_model_a(&C, blower_aux_vout_max_v(&C, duty)) : 0.0;
        double p = p_tank(tf.f_hz), i_ps = p / lim_cfg.eta_min / LINE_V;
        double bound = i_ps * (1 + lim_cfg.est_error) + in_force;
        double real = i_ps + BASE_REAL_A + ps3;
        if (h >= settle) {
            if (real > r.max_real_a) r.max_real_a = real;
            if (bound > r.max_bound_a) r.max_bound_a = bound;
            double margin = in_force - (C.base_a + ps3);
            if (margin < r.min_margin_a) r.min_margin_a = margin;
            if (margin < 0) r.lead_halves++;
        } else if (h == settle - 1) {
            r.settled_bound_a = bound;
        }
        double w = 2 * PI * tf.f_hz, x = w * PAN.L - 1.0 / (w * PAN.C);
        double i = PAN.v1 / hypot(PAN.R, x);
        tank_freq_obs_t ob = {.valid = true, .phase_valid = true, .fit_ok = true, .f_hz = tf.f_hz,
                              .f_fit_hz = (float)tf.f_hz, .phi_rad = (float)atan2(x, PAN.R),
                              .tank_rms_a = (float)i, .inlet_a = (float)bound, .peak_a = (float)(2.17 * i),
                              .p_inv_w = (float)p, .p_in_w = (float)(p / lim_cfg.eta_min)};
        (void)tank_freq_step(&tf, &fc, &lim, &ob);
    }
    return r;
}

static void test_closed_loop_step_up(void)
{
    /* Normal speed-ups (fan law, allowance first): off -> typical and off -> fan-law cap. */
    const float drives[] = {0.5f, FAN_DRIVE_CAP};
    for (unsigned k = 0; k < 2; k++) {
        loop_result_t r = run_step(drives[k], false, true);
        printf("  step-up off -> drive %.1f: settled bound %.2f A; max bound %.3f A, max real inlet %.3f A, "
               "min allowance margin %+.3f A\n", (double)drives[k], r.settled_bound_a, r.max_bound_a,
               r.max_real_a, r.min_margin_a);
        assert(r.settled_bound_a > 13.0 && r.settled_bound_a <= 13.5 * 1.02);
        assert(r.min_margin_a >= -1e-5);              /* the fan never draws above the allowance */
        assert(r.max_real_a <= 13.5);                  /* the total is never exceeded */
        assert(r.max_bound_a < 15.0);                  /* the adapter's inlet trip never fires */
        assert(r.max_bound_a <= 13.5 * (1 + 0.02) + 0.06); /* loop band + one half of ramp */
    }
    /* Fault path (urgent): thermal safety first, so the blower goes to full at once and the
     * allowance follows (urgent_a_per_s, then the binding's 0.05 A per half): the PS3 draw leads
     * the allowance for <= 25 halves (0.21 s) with this instant-draw plant (a real blower takes
     * ~1 s to spin up). The real inlet is then covered by the estimator's own margin (e_est x
     * I_ps ~ 1.1 A): at most one PS3 step above a bound held at the 13.5 A band edge. */
    loop_result_t r = run_step(1.0f, true, true);
    printf("  urgent step to full: max bound %.3f A, max real inlet %.3f A, PS3 above the allowance for "
           "%u halves (min margin %+.3f A)\n", r.max_bound_a, r.max_real_a, r.lead_halves, r.min_margin_a);
    assert(r.lead_halves <= 25 && r.max_bound_a < 15.0);
    assert(r.max_real_a <= 13.5 * 1.02 && r.max_real_a < 15.0);
    /* Without allowance-first the same normal step puts the fan above the allowance in force. */
    r = run_step(FAN_DRIVE_CAP, false, false);
    printf("  (no allowance-first, drive %.1f: min allowance margin %+.3f A)\n", (double)FAN_DRIVE_CAP,
           r.min_margin_a);
    assert(r.min_margin_a < -0.3);
    tests++;
}

/* ------------------------------------------------------------------ holds */
static void test_tank_hold(void)
{
    /* Power-stage hold = (13.5 - I_aux) / (1 + e_est); power available to the tank (inverter
     * fundamental, the estimator's p_inv) = hold x eta_min x V_line. Checked through the estimator
     * itself: a half drawing exactly the hold reports a 13.5 A bound. */
    input_limits_cfg_t l = input_limits_native21();
    const struct { const char *name; float aux; } st[] = {
        {"PS1+PS2 only (pre-stage-16 basis)", l.aux_min_a},
        {"blower off", blower_aux_level_a(&C, false, 0)},
        {"typical blower (drive 0.5)", level_drive(0.5f)},
        {"fan-law cap (drive 0.8)", level_drive(FAN_DRIVE_CAP)},
        {"full blower / unknown (static)", l.aux_max_a},
    };
    const float lines[] = {108.0f, 120.0f, 132.0f};
    printf("  tank hold (13.5 A regulated, e_est %.0f %%, eta_min %.2f):\n", 100.0 * l.est_error, (double)l.eta_min);
    float hold_full = 0, hold_typ = 0;
    for (unsigned k = 0; k < 5; k++) {
        float hold = (13.5f - st[k].aux) / (1 + l.est_error);
        printf("    %-36s I_aux %.3f A  hold %.2f A ", st[k].name, (double)st[k].aux, (double)hold);
        for (unsigned j = 0; j < 3; j++) {
            /* A flat half at V_line: p_inv = hold x eta x V. */
            input_sample_t smp[16];
            float p = hold * l.eta_min * lines[j];
            for (unsigned n = 0; n < 16; n++) smp[n] = (input_sample_t){lines[j], p / (0.900316316f * lines[j]), 1.0f, 0.0f};
            input_estimate_t e;
            assert(input_limits_half_cycle_aux(&l, smp, 16, lines[j], st[k].aux, &e));
            assert(NEAR(e.inlet_bound_a, 13.5, 2e-3) && NEAR(e.p_inv_w, p, 0.5));
            printf(" %3.0f V %5.0f W", (double)lines[j], (double)p);
        }
        printf("\n");
        if (k == 2) hold_typ = hold;
        if (k == 4) hold_full = hold;
    }
    float base_120 = (13.5f - l.aux_min_a) / 1.1f * 0.93f * 120.0f;
    assert(NEAR(base_120, 1237.7, 0.5)); /* 11.09 A (DECISIONS' 1239 W uses the rounded 11.1 A) */
    assert(NEAR(hold_full, 9.937, 0.002) && NEAR(hold_full * 0.93f * 120, 1109.0, 1.0));
    assert(NEAR(hold_typ, 10.428, 0.002) && NEAR(hold_typ * 0.93f * 120, 1163.8, 1.0));
    tests++;
}

/* Stage 16 C33: BLW_PG = 0 never lowers PS3's allowance. PS3's AC side can still draw with its
 * output failed (or BLW_PG can be wrong), so the schedule has no BLW_PG input at all: the glue
 * (thermal_io.c) runs it from the commanded drive with known = write ok && !stalled, exactly as
 * before C33. Here: a blower at a settled drive loses PS3 (tach 0, BLW_PG absent). Until the stall
 * the allowance holds the commanded level; at the stall ("PS3 absent") it goes to the worst case. */
static void test_ps3_absent_keeps_allowance(void)
{
    blower_ctrl_t bc;
    blower_ctrl_init(&bc);
    blower_aux_t s;
    blower_aux_init(&s, &C);
    uint16_t cnt = 0;
    uint32_t t = 0;
    blower_aux_out_t o = {0};
    blower_cmd_t cmd = {0};
    /* Settle: sink 90 C (fan on, below the 0.8 cap), PS3 present, blower turning. */
    for (unsigned n = 0; n < 200; n++, t += 100, cnt = (uint16_t)(cnt + 8)) {
        cmd = blower_ctrl_decide(&bc, 90.0f, 100.0f, false, 0.1f);
        blower_aux_in_t in = {.on = cmd.on, .duty = cmd.duty, .urgent = false,
                              .known = !bc.stall.stalled, .tach_rpm = bc.tach.rpm};
        o = blower_aux_step(&s, &C, &in, t);
        blower_ctrl_finish(&bc, &cmd, o.on, 90.0f, 100.0f, true, cnt, t, 2);
        blower_ctrl_supply(&bc, &cmd, BLOWER_SUPPLY_PRESENT, t);
    }
    float settled = o.allowance_a, worst = blower_aux_worst_a(&C);
    assert(cmd.on && settled < worst && settled >= blower_aux_level_a(&C, true, cmd.duty) - 1e-5f);
    /* PS3 lost: FG stops, BLW_PG absent. The allowance never falls below the settled level. */
    bool saw_diag = false;
    for (unsigned n = 0; n < 40; n++, t += 100) {
        cmd = blower_ctrl_decide(&bc, 90.0f, 100.0f, false, 0.1f);
        blower_aux_in_t in = {.on = cmd.on, .duty = cmd.duty, .urgent = false,
                              .known = !bc.stall.stalled, .tach_rpm = bc.tach.rpm};
        o = blower_aux_step(&s, &C, &in, t);
        assert(o.allowance_a >= settled - 1e-5f);
        blower_ctrl_finish(&bc, &cmd, o.on, 90.0f, 100.0f, true, cnt, t, 2);
        blower_ctrl_supply(&bc, &cmd, BLOWER_SUPPLY_ABSENT, t);
        saw_diag = saw_diag || cmd.diag == BLOWER_DIAG_PS3_ABSENT;
    }
    assert(saw_diag && bc.stall.stalled && o.allowance_a == worst);
    tests++;
}

int main(void)
{
    C = blower_aux_native21();
    test_config();
    test_model_sources();
    test_allowance_points();
    test_schedule();
    test_closed_loop_step_up();
    test_tank_hold();
    test_ps3_absent_keeps_allowance();
    printf("blower_aux: %u tests passed\n", tests);
    return 0;
}
