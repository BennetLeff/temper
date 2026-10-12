/* Thermal management: heatsink / coil / rim NTC conversion (Vishay and Semitec 104GT-2), the L3 trip
 * ladder (C32), the C29 input RC allowance, the 250 C pan cap, the R32 fan law and the L3 blower
 * (inverted PWM, tach, stall derate). Assertions are the oracle (built with -UNDEBUG). */
#include "thermal_mgmt.h"
#include "../config.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static unsigned tests;
#define TEST(fn) do { fn(); tests++; printf("PASS %s\n", #fn); } while (0)
#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))

/* ---------------------------------------------------------------- NTC conversion */
static void test_ntc_round_trip(void)
{
    const ntc_channel_t *ch[] = {&THERMAL_NTC_RIM, &THERMAL_NTC_COIL, &THERMAL_NTC_SINK};
    for (unsigned i = 0; i < 3; i++)
        for (float t = 0.0f; t <= 300.0f; t += 5.0f) {
            float mv = ntc_channel_mv_at(ch[i], t), back = -999.0f;
            if (t <= ch[i]->t_open_c || t >= ch[i]->t_short_c) continue;
            if (mv >= ch[i]->v_meas_max_mv) {
                assert(ntc_channel_temp_c(ch[i], mv, &back) == NTC_BELOW_RANGE);
                assert(back > t); /* the floor is an upper bound */
                continue;
            }
            assert(ntc_channel_temp_c(ch[i], mv, &back) == NTC_OK);
            assert(NEAR(back, t, 0.05));
        }
}

/* Vishay NTCLE100E3104 R-T table (doc 29049, rev. 07-May-2025, p. 12), the 100 k / 4190 K
 * +/- 1.5 % curve of the heatsink's NTCALUG01A104GA (unchanged at L3). */
static void test_vishay_curve_against_rt_table(void)
{
    static const struct { float t_c, r_kohm; } tab[] = {
        {-20, 1041}, {0, 340.9}, {25, 100.0}, {50, 34.31}, {85, 9.496}, {100, 5.835},
        {120, 3.206}, {140, 1.854}, {150, 1.434}};
    for (unsigned i = 0; i < sizeof tab / sizeof tab[0]; i++) {
        float r = ntc_channel_r_at(&THERMAL_NTC_SINK, tab[i].t_c) / 1000.0f;
        assert(fabs(r / tab[i].r_kohm - 1.0) < 0.002); /* table is printed to 4 digits */
        float t = -999.0f;
        float mv = 3304.0f * tab[i].r_kohm / (tab[i].r_kohm + 10.0f);
        if (mv < THERMAL_ADC_MEAS_MAX_MV) {
            assert(ntc_channel_temp_c(&THERMAL_NTC_SINK, mv, &t) == NTC_OK);
            assert(NEAR(t, tab[i].t_c, 0.1));
        }
    }
    /* Divider voltages at the ladder points (10.0 k pull-up, 3.304 V). */
    const float pts[] = {25.0f, 88.6f, 95.0f, 98.3f, 101.4f};
    for (unsigned i = 0; i < 5; i++) {
        float mv = ntc_channel_mv_at(&THERMAL_NTC_SINK, pts[i]), t = 0.0f;
        assert(ntc_channel_temp_c(&THERMAL_NTC_SINK, mv, &t) == NTC_OK && NEAR(t, pts[i], 0.01));
        printf("  sink node %6.1f C = %7.1f mV (tolerance +/- %.2f K)\n", pts[i], mv,
               ntc_channel_tol_k(&THERMAL_NTC_SINK, pts[i]));
    }
    /* Pinned conversion points: 25 C = 3004 mV, 95 C = 2 sig. figures of the R-T table. */
    assert(NEAR(ntc_channel_mv_at(&THERMAL_NTC_SINK, 25.0f), 3304.0 * 100.0 / 110.0, 0.5));
    /* Tolerance at the 95 C trip ~2 K (C32 check: 98.3 C >= 95 C + 2 K). */
    float tol95 = ntc_channel_tol_k(&THERMAL_NTC_SINK, 95.0f);
    assert(tol95 > 1.6f && tol95 <= 2.0f);
}

/* Semitec 104GT-2 (GT-2 data sheet 2023-08-01 p. 18: 100 k +/- 3 %, B25/85 4267 K +/- 2 %,
 * -50..+300 C): the coil (10.0 k pull-up) and the rim (1.00 k pull-up). */
static void test_semitec_104gt2_conversion(void)
{
    static const struct { float t_c, r_ohm; } tab[] = {
        {0, 353700}, {25, 100000}, {100, 5556}, {140, 1758}, {150, 1360}, {160, 1064},
        {170, 841.4}, {180, 671.4}, {200, 439.3}, {250, 174.0}, {280, 107.9}};
    for (unsigned i = 0; i < sizeof tab / sizeof tab[0]; i++) {
        assert(fabs(ntc_channel_r_at(&THERMAL_NTC_COIL, tab[i].t_c) / tab[i].r_ohm - 1.0) < 1e-4);
        assert(fabs(ntc_channel_r_at(&THERMAL_NTC_RIM, tab[i].t_c) / tab[i].r_ohm - 1.0) < 1e-4);
    }
    /* The table honours its own B25/85 (4267 K): R85 = R25 exp(-B (1/298.15 - 1/358.15)). */
    double b2585 = log(100000.0 / ntc_channel_r_at(&THERMAL_NTC_COIL, 85.0f)) /
                   (1.0 / 298.15 - 1.0 / 358.15);
    assert(NEAR(b2585, 4267.0, 1.0));
    /* Between table points the model stays within 0.5 K of the B25/85 beta curve at 50-70 C
     * (the 30..100 C gap) - a smoothness check, since the true part lies between both. */
    ntc_channel_t beta = THERMAL_NTC_COIL;
    beta.table = NULL;
    for (float t = 40.0f; t <= 80.0f; t += 10.0f) {
        double dln = log(ntc_channel_r_at(&THERMAL_NTC_COIL, t) / ntc_channel_r_at(&beta, t));
        assert(fabs(dln) * (t + 273.15) * (t + 273.15) / 4267.0 < 0.6);
    }
    /* Coil conversion points (10.0 k pull-up, 3.304 V). */
    const struct { float t, mv; } coil[] = {
        {25.0f, 3003.6f}, {140.0f, 494.0f}, {150.0f, 395.5f}, {165.0f, 285.2f}, {175.7f, 227.3f}};
    for (unsigned i = 0; i < 5; i++) {
        float mv = ntc_channel_mv_at(&THERMAL_NTC_COIL, coil[i].t), t = 0.0f;
        printf("  coil node %6.1f C = %7.1f mV (tolerance +/- %.2f K)\n", coil[i].t, mv,
               ntc_channel_tol_k(&THERMAL_NTC_COIL, coil[i].t));
        assert(NEAR(mv, coil[i].mv, 0.2));
        assert(ntc_channel_temp_c(&THERMAL_NTC_COIL, mv, &t) == NTC_OK && NEAR(t, coil[i].t, 0.01));
    }
    /* Rim (C31): 0.489 V and 7.0 mV/K at 250 C; 200 C 1.008 V; 280 C 0.322 V. */
    float r250 = ntc_channel_mv_at(&THERMAL_NTC_RIM, 250.0f);
    float slope = (ntc_channel_mv_at(&THERMAL_NTC_RIM, 240.0f) - ntc_channel_mv_at(&THERMAL_NTC_RIM, 260.0f)) / 20.0f;
    printf("  rim node 250 C = %.1f mV, %.2f mV/K\n", r250, slope);
    assert(NEAR(r250, 489.0, 1.5) && NEAR(slope, 7.0, 0.1));
    assert(NEAR(ntc_channel_mv_at(&THERMAL_NTC_RIM, 200.0f), 1008.4, 1.5));
    assert(NEAR(ntc_channel_mv_at(&THERMAL_NTC_RIM, 280.0f), 321.8, 1.5));
    float t = 0.0f;
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, r250, &t) == NTC_OK && NEAR(t, 250.0, 0.01));
    /* Error bands from the sensor tolerances (R25 3 %, B 2 %). */
    float tol25 = ntc_channel_tol_k(&THERMAL_NTC_COIL, 25.0f);
    float tol165 = ntc_channel_tol_k(&THERMAL_NTC_COIL, 165.0f);
    float tol250 = ntc_channel_tol_k(&THERMAL_NTC_RIM, 250.0f);
    printf("  104GT-2 tolerance: 25 C %.2f K, 165 C %.2f K, 250 C %.2f K\n", tol25, tol165, tol250);
    assert(tol25 > 0.5f && tol25 < 0.8f);   /* R25 only: ln(1.03) / (B / T^2) */
    assert(tol165 > 4.5f && tol165 < 6.0f);
    assert(tol250 > 7.0f && tol250 < 9.5f);
    /* Self-heating (documented, not corrected): rim ~1.4 mW / ~2.3 K at 250 C (reads hot: the
     * 250 C cap comes in early, the safe side); coil ~0.08 mW at 170 C, negligible. */
    float sh_rim = ntc_channel_self_heat_k(&THERMAL_NTC_RIM, 250.0f);
    float sh_coil = ntc_channel_self_heat_k(&THERMAL_NTC_COIL, 170.0f);
    printf("  self-heating: rim 250 C %.2f K, coil 170 C %.3f K\n", sh_rim, sh_coil);
    assert(sh_rim > 2.0f && sh_rim < 2.7f);
    assert(sh_coil < 0.2f);
    float peak = 0.0f;
    for (float tt = 100.0f; tt <= 250.0f; tt += 1.0f) {
        float k = ntc_channel_self_heat_k(&THERMAL_NTC_RIM, tt);
        if (k > peak) peak = k;
    }
    assert(peak * 0.6f <= 3.0f); /* <= the 3 mW rating */
}

static void test_coil_sink_open_short_fail_safe(void)
{
    const ntc_channel_t *ch[] = {&THERMAL_NTC_COIL, &THERMAL_NTC_SINK};
    for (unsigned i = 0; i < 2; i++) {
        float t;
        assert(ntc_channel_temp_c(ch[i], 3304.0f, &t) == NTC_OPEN);
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], -20.5f), &t) == NTC_OPEN);
        /* Colder than the ADC resolves (~15 C): the range floor, never an error or "hot". */
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], -19.0f), &t) == NTC_BELOW_RANGE);
        assert(t > 10.0f && t < 20.0f && NEAR(t, ntc_channel_range_min_c(ch[i]), 1e-3));
        assert(ntc_channel_temp_c(ch[i], 0.0f, &t) == NTC_SHORT);
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], 201.0f), &t) == NTC_SHORT);
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], 190.0f), &t) == NTC_OK);
        assert(ntc_channel_temp_c(ch[i], NAN, &t) == NTC_BAD_ARG);
        /* The short class sits above the hardware trip's high corner on both channels. */
        assert(ch[i]->t_short_c > THERMAL_HW_COIL_TRIP_HIGH_C);
    }
    /* An open or shorted coil sensor gives no tank power and full fan (fail safe). */
    assert(coil_tank_cap_pct(NAN) == 0);
    fan_law_t f;
    fan_law_init(&f);
    fan_law_step(&f, 30.0f, NAN, 0.1f, false);
    assert(f.on && f.drive == 1.0f && f.tank_cap_pct == 0);
}

static void test_rim_parameterised(void)
{
    /* The macros are what the channel uses: 104GT-2 on 1.00 k (C31). */
    ntc_channel_t rim = THERMAL_NTC_RIM;
    assert(rim.r_pullup_ohm == RIM_NTC_R_PULLUP_OHM && rim.r25_ohm == RIM_NTC_R25_OHM &&
           rim.beta_k == RIM_NTC_BETA_K && rim.curve == NULL &&
           rim.table == &NTC_TABLE_SEMITEC_104GT2);
    assert(RIM_NTC_R_PULLUP_OHM == 1000.0f && RIM_NTC_R25_OHM == 100000.0f && RIM_NTC_BETA_K == 4267.0f);
    /* Thresholds follow R / B: a drop-in change needs no other edit. */
    float t;
    rim.table = NULL; /* beta model */
    assert(ntc_channel_temp_c(&rim, ntc_channel_mv_at(&rim, 250.0f), &t) == NTC_OK && NEAR(t, 250.0, 0.05));
    rim.beta_k = 3500.0f;
    assert(ntc_channel_temp_c(&rim, ntc_channel_mv_at(&rim, 250.0f), &t) == NTC_OK && NEAR(t, 250.0, 0.05));
    assert(ntc_channel_temp_c(&rim, ntc_channel_mv_at(&rim, 321.0f), &t) == NTC_SHORT);
}

static void test_rim_open_short_and_hot_end(void)
{
    float t;
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, 3304.0f, &t) == NTC_OPEN);
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, 1.0f, &t) == NTC_SHORT);
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, NAN, &t) == NTC_BAD_ARG);
    /* With 1.00 k on a 100 k part the node is within 3 mV of v3v3 at -20 C, far above the ADC's
     * 3.1 V: an unplugged J12 reads like a rim below ~73 C. Both are "no rim reading" (thermal_io:
     * no rim cap; the pan RTD still caps). The rim channel exists for the hot end. */
    float floor_c = ntc_channel_range_min_c(&THERMAL_NTC_RIM);
    printf("  rim resolves from %.1f C up\n", floor_c);
    assert(floor_c > 65.0f && floor_c < 80.0f);
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, 3290.0f, &t) == NTC_BELOW_RANGE);
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, ntc_channel_mv_at(&THERMAL_NTC_RIM, 25.0f), &t) == NTC_BELOW_RANGE);
    /* 240..300 C is well inside the range and away from the short class. */
    for (float tt = 240.0f; tt <= 300.0f; tt += 10.0f) {
        float mv = ntc_channel_mv_at(&THERMAL_NTC_RIM, tt);
        assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, mv, &t) == NTC_OK && NEAR(t, tt, 0.01));
        assert(mv > 200.0f); /* 300 C: ~245 mV, 5 mV/K */
    }
}

/* ---------------------------------------------------------------- trip ladder (C32) */
/* Thermal-sense comparator with a 10 k pull-up NTC node (INN) against a reference divider with
 * hysteresis to the output (INP); ratiometric, so v3v3 cancels. Hot when the node falls below. */
static float hw_trip_c(const ntc_channel_t *ch, double rfix, double top, double bot, double hyst, bool release)
{
    double par_bh = bot * hyst / (bot + hyst), par_th = top * hyst / (top + hyst);
    double k = release ? bot / (bot + par_th) : par_bh / (top + par_bh);
    double r = rfix * k / (1.0 - k);
    ntc_channel_t c = *ch;
    c.r_pullup_ohm = (float)rfix;
    c.v_meas_max_mv = 0.0f; /* the comparator has no ADC range */
    float t = NAN;
    assert(ntc_channel_temp_c(&c, (float)(c.v_ref_mv * r / (r + rfix)), &t) == NTC_OK);
    return t;
}

/* Resistor corners only (sensor nominal): the part of the band that separates the firmware
 * reading from the comparator, since both read the same NTC. */
static void hw_band(const ntc_channel_t *ch, const double v[4], const double tol[4], float *lo, float *hi)
{
    *lo = 1e9f;
    *hi = -1e9f;
    for (unsigned m = 0; m < 16; m++) {
        double x[4];
        for (unsigned j = 0; j < 4; j++) x[j] = v[j] * (1.0 + ((m >> j) & 1u ? tol[j] : -tol[j]));
        float t = hw_trip_c(ch, x[0], x[1], x[2], x[3], false);
        if (t < *lo) *lo = t;
        if (t > *hi) *hi = t;
    }
}

/* The ladder must be: fan-law point < firmware derate < firmware hard trip < hardware trip low
 * corner, for the heatsink and the coil. Reordering any rung fails here. */
static void test_trip_ladder_order(void)
{
    /* Heatsink: fan 88.6 < firmware trip 95 (config.yaml) < hardware 98.3 (low) / 101.4 nominal. */
    assert(FAN_SINK_SETPOINT_C < OVER_TEMP_THRESHOLD);
    assert(OVER_TEMP_THRESHOLD < THERMAL_HW_SINK_TRIP_LOW_C);
    assert(THERMAL_HW_SINK_TRIP_LOW_C < THERMAL_HW_SINK_TRIP_NOM_C &&
           THERMAL_HW_SINK_TRIP_NOM_C < THERMAL_HW_SINK_TRIP_HIGH_C);
    assert(OVER_TEMP_THRESHOLD == 95.0f && FAN_SINK_SETPOINT_C == 88.6f);
    /* C32 margin: the comparator's low corner clears the firmware trip plus the sensor tolerance. */
    assert(OVER_TEMP_THRESHOLD + ntc_channel_tol_k(&THERMAL_NTC_SINK, OVER_TEMP_THRESHOLD) <=
           THERMAL_HW_SINK_TRIP_LOW_C);
    /* Release: the comparator re-arms above the firmware's 70 C recovery point. */
    assert(70.0f < THERMAL_HW_SINK_REL_LOW_C && THERMAL_HW_SINK_REL_HIGH_C < THERMAL_HW_SINK_TRIP_LOW_C);

    /* Coil: fan 140 < derate 150..160 < firmware trip 165 < hardware 169.7 (low) / 175.7 nominal. */
    assert(FAN_COIL_SETPOINT_C < FAN_COIL_LIMIT_C);
    assert(FAN_COIL_LIMIT_C < FAN_COIL_LIMIT_C + FAN_COIL_LIMIT_BAND_K);
    assert(FAN_COIL_LIMIT_C + FAN_COIL_LIMIT_BAND_K < COIL_FW_TRIP_C);
    assert(COIL_FW_TRIP_C < THERMAL_HW_COIL_TRIP_LOW_C);
    assert(THERMAL_HW_COIL_TRIP_LOW_C < THERMAL_HW_COIL_TRIP_NOM_C &&
           THERMAL_HW_COIL_TRIP_NOM_C < THERMAL_HW_COIL_TRIP_HIGH_C);
    assert(FAN_COIL_SETPOINT_C == 140.0f && FAN_COIL_LIMIT_C == 150.0f && COIL_FW_TRIP_C == 165.0f);
    assert(COIL_FW_RECOVER_C < THERMAL_HW_COIL_REL_LOW_C);
    /* The coil trip is within the 104GT-2's 300 C rating and the heatsink's within the Vishay's
     * 150 C. */
    assert(THERMAL_HW_COIL_TRIP_HIGH_C < 300.0f && THERMAL_HW_SINK_TRIP_HIGH_C < 150.0f);
    /* The derate reaches zero before the firmware trip, so the trip only acts if the derate
     * failed. */
    assert(coil_tank_cap_pct(COIL_FW_TRIP_C - 0.1f) == 0);
}

/* The comparator thresholds recomputed from the fitted resistors (controller-layout controller.ato
 * overrides, C32) through the firmware's own sensor models: they reproduce controller_calcs.py
 * to within its model difference, and the firmware trip sits below the resistor-corner band. */
static void test_hardware_trip_points_from_resistors(void)
{
    const double hs[4] = {10e3, 11.5e3, 8.06e3, 34.8e3}, hs_tol[4] = {0.01, 0.01, 0.01, 0.01};
    const double co[4] = {10e3, 90.9e3, 7.06e3, 140e3}, co_tol[4] = {0.01, 0.001, 0.001, 0.001};
    float hs_c = hw_trip_c(&THERMAL_NTC_SINK, hs[0], hs[1], hs[2], hs[3], false);
    float hs_r = hw_trip_c(&THERMAL_NTC_SINK, hs[0], hs[1], hs[2], hs[3], true);
    float co_c = hw_trip_c(&THERMAL_NTC_COIL, co[0], co[1], co[2], co[3], false);
    float co_r = hw_trip_c(&THERMAL_NTC_COIL, co[0], co[1], co[2], co[3], true);
    float hs_lo, hs_hi, co_lo, co_hi;
    hw_band(&THERMAL_NTC_SINK, hs, hs_tol, &hs_lo, &hs_hi);
    hw_band(&THERMAL_NTC_COIL, co, co_tol, &co_lo, &co_hi);
    printf("  hardware trip: heatsink %.1f C (resistor band %.1f-%.1f, release %.1f), coil %.1f C "
           "(resistor band %.1f-%.1f, release %.1f)\n", hs_c, hs_lo, hs_hi, hs_r, co_c, co_lo, co_hi, co_r);
    /* Vishay curve vs the validator's beta model, 104GT-2 table interpolation in 1/T vs in T. */
    assert(NEAR(hs_c, THERMAL_HW_SINK_TRIP_NOM_C, 0.8) && NEAR(co_c, THERMAL_HW_COIL_TRIP_NOM_C, 0.6));
    assert(NEAR(hs_r, 85.6, 0.6) && NEAR(co_r, 152.4, 0.6));
    assert(OVER_TEMP_THRESHOLD < hs_lo && COIL_FW_TRIP_C < co_lo);
    assert(hs_lo - OVER_TEMP_THRESHOLD > 3.0f && co_lo - COIL_FW_TRIP_C > 8.0f);
}

/* ---------------------------------------------------------------- input RC (C29) */
static void test_input_rc_allowance(void)
{
    float tau_hs = ntc_input_tau_s(&THERMAL_NTC_SINK), tau_co = ntc_input_tau_s(&THERMAL_NTC_COIL);
    float tau_rim = ntc_input_tau_s(&THERMAL_NTC_RIM);
    uint32_t settle = ntc_input_settle_ms(&THERMAL_NTC_COIL);
    printf("  input RC: tau HS/COIL %.2f ms, RIM %.2f ms; settle %u ms (RIM %u ms)\n", tau_hs * 1e3,
           tau_rim * 1e3, (unsigned)settle, (unsigned)ntc_input_settle_ms(&THERMAL_NTC_RIM));
    /* 10 k / 100 nF = 1.0 ms, 159 Hz (C29). */
    assert(NEAR(1.0 / (2.0 * M_PI * THERMAL_NTC_COIL.filt_r_ohm * THERMAL_NTC_COIL.filt_c_f), 159.2, 0.5));
    assert(tau_hs == tau_co && tau_hs > 3.0e-3f && tau_hs < 3.5e-3f);
    assert(tau_rim > 1.1e-3f && tau_rim < 1.3e-3f);
    /* Settling (12-bit) after power-up: the capacitors start at 0 V, which reads as SHORT. */
    assert(ntc_channel_temp_c(&THERMAL_NTC_COIL, 0.0f, &(float){0}) == NTC_SHORT);
    assert(settle >= (uint32_t)(tau_co * 8.3f * 1000.0f) && settle <= 30u);
    assert(!ntc_input_settled(&THERMAL_NTC_COIL, 0) && !ntc_input_settled(&THERMAL_NTC_COIL, settle - 1u));
    assert(ntc_input_settled(&THERMAL_NTC_COIL, settle));
    /* The firmware's thermal decisions run on 100 ms ticks (blower, monitor) and 10 ms ticks
     * (state machine); stall detection waits > 1 s. A full settle fits inside one 100 ms tick
     * and the RIM / thermal frame-age limit (20 ms) is longer than a filtered transition takes
     * to matter: the lag behind a ramp is tau x rate. */
    assert(settle < 100u && settle < BLOWER_STALL_TIME_MS);
    /* Fastest credible ramp: a coil with the blower lost, < 10 K/s; the sink, < 2 K/s. */
    assert(ntc_input_lag_k(&THERMAL_NTC_COIL, 10.0f) < 0.05f);
    assert(ntc_input_lag_k(&THERMAL_NTC_SINK, 2.0f) < 0.01f);
    /* The firmware reads through the extra 10 k / 100 nF; the comparator sees the node. Their
     * timing difference (~2 ms) is negligible next to the 3+ K between the rungs. */
    assert(ntc_input_lag_k(&THERMAL_NTC_SINK, 2.0f) < OVER_TEMP_THRESHOLD - FAN_SINK_SETPOINT_C);
    /* Anti-aliasing: each thermal channel is sampled at 80 kS/s / 9 slots (C12 + C27); the
     * 159 Hz corner is far below that channel's Nyquist frequency. */
    assert(159.2 < 80000.0 / 9.0 / 2.0 / 10.0);
}
static void test_pan_cap(void)
{
    pan_cap_t c = pan_cap_evaluate(200.0f, true, 120.0f, true);
    assert(c.cap_pct == 100 && !c.rtd_limiting && !c.rim_limiting && !c.rim_invalid);
    c = pan_cap_evaluate(245.0f, true, 120.0f, true);
    assert(c.cap_pct == 50 && c.rtd_limiting);
    c = pan_cap_evaluate(250.0f, true, 120.0f, true);
    assert(c.cap_pct == 0);
    c = pan_cap_evaluate(300.0f, true, 120.0f, true);
    assert(c.cap_pct == 0);
    /* Rim alone (independent, slower path; also glass protection). */
    c = pan_cap_evaluate(200.0f, true, 248.0f, true);
    assert(c.cap_pct == 20 && c.rim_limiting && !c.rtd_limiting);
    c = pan_cap_evaluate(200.0f, true, 251.0f, true);
    assert(c.cap_pct == 0);
    /* Lowest of the two wins. */
    c = pan_cap_evaluate(242.0f, true, 247.0f, true);
    assert(c.cap_pct == 30);
    /* Invalid RTD refuses heat; invalid rim is flagged but does not cap. */
    assert(pan_cap_evaluate(NAN, true, 25.0f, true).cap_pct == 0);
    assert(pan_cap_evaluate(100.0f, false, 25.0f, true).cap_pct == 0);
    c = pan_cap_evaluate(100.0f, true, NAN, false);
    assert(c.cap_pct == 100 && c.rim_invalid);
    /* Monotone: never rises with temperature. */
    uint8_t prev = 100;
    for (float t = 230.0f; t <= 260.0f; t += 0.25f) {
        uint8_t now = pan_cap_evaluate(t, true, 25.0f, true).cap_pct;
        assert(now <= prev);
        prev = now;
    }
}

static void test_fan_law_on_off_hysteresis(void)
{
    fan_law_t f;
    fan_law_init(&f);
    fan_law_step(&f, 30.0f, 30.0f, 0.1f, false);
    assert(!f.on && f.drive == 0.0f);
    fan_law_step(&f, 52.0f, 40.0f, 0.1f, false); /* above 50 but below 55: still off */
    assert(!f.on);
    fan_law_step(&f, 40.0f, 55.0f, 0.1f, false); /* coil reaches 55: on */
    assert(f.on);
    fan_law_step(&f, 51.0f, 45.0f, 0.1f, false); /* above 50: stays on */
    assert(f.on);
    fan_law_step(&f, 49.0f, 49.9f, 0.1f, false); /* both below 50: off */
    assert(!f.on && f.drive == 0.0f && f.sink.integ == 0.0f && f.coil.integ == 0.0f);
}

static void test_fan_law_max_of_loops_and_cap(void)
{
    fan_law_t f;
    fan_law_init(&f);
    /* Sink above its 88.6 C setpoint, coil below 140 C: the sink loop drives. */
    fan_law_step(&f, 98.6f, 100.0f, 0.1f, false);
    assert(f.on && f.drive > 0.0f && NEAR(f.drive, FAN_KP_PER_K * 10.0f + f.sink.integ, 1e-5));
    float sink_only = f.drive;
    /* Coil far above 140 C: max() takes the coil loop. */
    fan_law_step(&f, 98.6f, 145.0f, 0.1f, false);
    assert(f.drive >= sink_only);
    /* Hot everywhere for a long time: the 0.8 cap holds outside a fault, no wind-up above it. */
    for (int i = 0; i < 10000; i++) fan_law_step(&f, 130.0f, 149.0f, 0.1f, false);
    assert(NEAR(f.drive, FAN_DRIVE_CAP, 1e-6) && f.sink.integ <= FAN_DRIVE_CAP);
    assert(!f.coil_limit && f.tank_cap_pct == 100);
    /* Coil above 150 C at full fan: tank power derates (100 % at 150 C to 0 at 160 C). */
    fan_law_step(&f, 130.0f, 155.0f, 0.1f, false);
    assert(f.coil_limit && f.tank_cap_pct == 50);
    fan_law_step(&f, 130.0f, 161.0f, 0.1f, false);
    assert(f.coil_limit && f.tank_cap_pct == 0);
    /* Cooling back: the integrator unwinds and the drive falls. */
    for (int i = 0; i < 20000; i++) fan_law_step(&f, 60.0f, 60.0f, 0.1f, false);
    assert(f.on && f.drive == 0.0f);
}

static void test_fan_law_fault_full_speed(void)
{
    fan_law_t f;
    fan_law_init(&f);
    fan_law_step(&f, 30.0f, 30.0f, 0.1f, true);
    assert(f.on && f.drive == 1.0f);
    fan_law_init(&f);
    fan_law_step(&f, NAN, 30.0f, 0.1f, false); /* invalid sensor = fault */
    assert(f.on && f.drive == 1.0f);
    fan_law_step(&f, 30.0f, 155.0f, 0.1f, true);
    assert(f.coil_limit && f.tank_cap_pct == 50);
}

/* ---------------------------------------------------------------- blower (C28) */
static void test_blower_stall(void)
{
    blower_stall_t s;
    blower_stall_init(&s);
    /* Healthy tach: no derate. */
    assert(blower_stall_update(&s, true, 1800.0f, 0, 70.0f, 100.0f) == 100);
    /* Tach lost while driven: nothing for 1 s, then the derate at once. */
    assert(blower_stall_update(&s, true, 0.0f, 1000, 70.0f, 100.0f) == 100);
    assert(blower_stall_update(&s, true, 0.0f, 2000, 70.0f, 100.0f) == 100); /* exactly 1 s */
    assert(blower_stall_update(&s, true, 0.0f, 2001, 70.0f, 100.0f) == BLOWER_STALL_POWER_CAP_PCT);
    assert(s.stalled);
    /* Sink or coil keeps rising: stop. */
    assert(blower_stall_update(&s, true, 0.0f, 3000, 71.0f, 101.0f) == BLOWER_STALL_POWER_CAP_PCT);
    assert(blower_stall_update(&s, true, 0.0f, 4000, 72.5f, 101.0f) == 0);
    assert(blower_stall_update(&s, true, NAN, 4100, 70.0f, 100.0f) == 0); /* NaN tach is no tach */
    /* Tach back: the derate lifts. */
    assert(blower_stall_update(&s, true, 1800.0f, 5000, 72.5f, 101.0f) == 100 && !s.stalled);
    /* Blower switched off by the fan law is not a stall. */
    for (uint32_t t = 6000; t < 10000; t += 100) assert(blower_stall_update(&s, false, 0.0f, t, 40.0f, 40.0f) == 100);
    /* Timer wrap is harmless (unsigned difference). */
    blower_stall_init(&s);
    assert(blower_stall_update(&s, true, 0.0f, 0xFFFFFF00u, 70.0f, 100.0f) == 100);
    assert(blower_stall_update(&s, true, 0.0f, 0x00000400u, 70.0f, 100.0f) == BLOWER_STALL_POWER_CAP_PCT);
}

/* Buck output vs GPIO46 duty (C28: 140 k / 11.5 k FB divider, 56.2 k + 12.1 k injection, VFB
 * 0.788-0.812 V, v3v3 3.242-3.367 V high level, 0.1 % / 1 % resistors). */
static double blower_vout(double vctl, double vfb, double rt, double rb, double ri)
{
    return vfb + rt * (vfb / rb - (vctl - vfb) / ri);
}
static void blower_vout_band(double duty, bool pin_floating, double *lo, double *hi)
{
    *lo = 1e9;
    *hi = -1e9;
    for (unsigned m = 0; m < 64; m++) {
        double vfb = (m & 1u) ? 0.812 : 0.788, vh = (m & 2u) ? 3.367 : 3.242;
        double rt = 140e3 * ((m & 4u) ? 1.001 : 0.999), rb = 11.5e3 * ((m & 8u) ? 1.001 : 0.999);
        double ri = 68.3e3 * ((m & 16u) ? 1.01 : 0.99);
        if (pin_floating) ri += 100e3 * ((m & 32u) ? 1.01 : 0.99); /* strap pull-down to 0 V */
        double v = blower_vout(pin_floating ? 0.0 : duty * vh, vfb, rt, rb, ri);
        if (v < *lo) *lo = v;
        if (v > *hi) *hi = v;
    }
}

static void test_blower_pwm_inverted_and_fail_safe(void)
{
    /* Inverted: more drive = less duty; full drive = duty 0 = full speed. */
    assert(blower_pwm_duty_from_drive(1.0f) == 0.0f);
    assert(blower_pwm_duty_from_drive(0.0f) == BLOWER_PWM_DUTY_MAX);
    float prev = 2.0f;
    for (float d = 0.0f; d <= 1.0f; d += 0.05f) {
        float duty = blower_pwm_duty_from_drive(d);
        assert(duty < prev && duty >= 0.0f && duty <= BLOWER_PWM_DUTY_MAX);
        prev = duty;
    }
    /* Out of range or invalid: full speed. */
    assert(blower_pwm_duty_from_drive(2.0f) == 0.0f);
    assert(blower_pwm_duty_from_drive(NAN) == 0.0f);
    assert(blower_pwm_duty_from_drive(INFINITY) == 0.0f);
    assert(blower_pwm_duty_from_drive(-1.0f) == BLOWER_PWM_DUTY_MAX);
    /* LEDC counts at 10 bits: 0 -> 0 (pin low), the cap -> 870 of 1024; NaN -> 0. */
    assert(blower_ledc_counts(0.0f, 10) == 0u && blower_ledc_counts(NAN, 10) == 0u);
    assert(blower_ledc_counts(BLOWER_PWM_DUTY_MAX, 10) == 870u && blower_ledc_counts(1.0f, 10) == 1024u);
    /* Supply voltage over the corners: duty 0 = 11.96-12.40 V; the duty cap keeps the slowest
     * speed above the blower's 5.5 V floor; reset / brown-out (pin an input, 100 k pull-down)
     * still runs it near full speed. */
    double lo, hi, rlo, rhi, flo, fhi;
    blower_vout_band(0.0, false, &flo, &fhi);
    blower_vout_band(BLOWER_PWM_DUTY_MAX, false, &lo, &hi);
    blower_vout_band(0.0, true, &rlo, &rhi);
    printf("  blower: duty 0 %.2f-%.2f V, duty %.2f %.2f-%.2f V, reset %.2f-%.2f V\n", flo, fhi,
           (double)BLOWER_PWM_DUTY_MAX, lo, hi, rlo, rhi);
    assert(flo >= 11.9 && fhi <= 13.2);
    assert(lo >= 6.0 && hi < flo);
    double l100, h100;
    blower_vout_band(1.0, false, &l100, &h100);
    assert(l100 < 5.5); /* why the cap exists: 100 % duty is below the floor at a corner */
    assert(rlo >= 11.0 && rlo > hi);

    /* Controller defaults: no readings (NaN), or any fault -> on, duty 0. */
    blower_ctrl_t c;
    blower_ctrl_init(&c);
    blower_cmd_t o = blower_ctrl_step(&c, NAN, NAN, false, true, 0, 0, 0.1f, BLOWER_TACH_PULSES_PER_REV);
    assert(o.on && o.duty == 0.0f && o.power_cap_pct == 0);
    blower_ctrl_init(&c);
    o = blower_ctrl_step(&c, 30.0f, 30.0f, true, true, 0, 0, 0.1f, BLOWER_TACH_PULSES_PER_REV);
    assert(o.on && o.duty == 0.0f);
    /* Cold and no fault: the fan law switches it off, and the duty is still 0 so a failed
     * FAN_OFF write leaves it at full speed rather than slow. */
    blower_ctrl_init(&c);
    o = blower_ctrl_step(&c, 30.0f, 30.0f, false, true, 0, 0, 0.1f, BLOWER_TACH_PULSES_PER_REV);
    assert(!o.on && o.duty == 0.0f && o.power_cap_pct == 100);
}

static void test_blower_tach(void)
{
    assert(BLOWER_TACH_PULSES_PER_REV >= 1); /* config.yaml */
    blower_tach_t t;
    blower_tach_init(&t);
    assert(isnan(blower_tach_update(&t, true, 100, 0, 2)));     /* primes */
    assert(isnan(blower_tach_update(&t, true, 110, 100, 2)));   /* window open */
    /* 20 pulses in 250 ms at 2 pulses/rev = 2400 rpm. */
    assert(NEAR(blower_tach_update(&t, true, 120, 250, 2), 2400.0, 0.01));
    /* 16-bit wrap. */
    blower_tach_init(&t);
    (void)blower_tach_update(&t, true, 65530, 0, 2);
    assert(NEAR(blower_tach_update(&t, true, 4, 250, 2), 10.0 * 60000.0 / (250.0 * 2.0), 0.01));
    /* Pulses per revolution scales the result. */
    blower_tach_init(&t);
    (void)blower_tach_update(&t, true, 0, 0, 4);
    assert(NEAR(blower_tach_update(&t, true, 20, 250, 4), 1200.0, 0.01));
    /* A failed count read: no speed (NaN), which the stall detector treats as no tach. */
    assert(isnan(blower_tach_update(&t, false, 0, 500, 4)));
    assert(isnan(blower_tach_update(&t, true, 0, 0, 0)));
}

/* A stopped / locked blower, an unplugged one or an open FG wire: 0 pulses -> 0 rpm -> derate
 * after > 1 s, then stop (and is_fan_running() false) if the sink or coil keeps rising. */
static void test_tach_zero_derates(void)
{
    for (int unplugged = 0; unplugged < 2; unplugged++) {
        blower_ctrl_t c;
        blower_ctrl_init(&c);
        blower_cmd_t o = {0};
        uint32_t now = 0;
        for (; now <= 1000; now += 100) {
            o = blower_ctrl_step(&c, 90.0f, 120.0f, false, !unplugged, 0, now, 0.1f,
                                 BLOWER_TACH_PULSES_PER_REV);
            assert(o.on && o.power_cap_pct == 100);
        }
        if (!unplugged) assert(o.rpm == 0.0f);
        for (; now <= 1300; now += 100)
            o = blower_ctrl_step(&c, 90.0f, 120.0f, false, !unplugged, 0, now, 0.1f,
                                 BLOWER_TACH_PULSES_PER_REV);
        assert(o.power_cap_pct == BLOWER_STALL_POWER_CAP_PCT && !o.blower_failed);
        o = blower_ctrl_step(&c, 92.5f, 120.0f, false, !unplugged, 0, now, 0.1f,
                             BLOWER_TACH_PULSES_PER_REV);
        assert(o.power_cap_pct == 0 && o.blower_failed);
    }
    /* Spinning: 2400 rpm at 2 pulses/rev = 80 Hz FG: no derate. */
    blower_ctrl_t c;
    blower_ctrl_init(&c);
    blower_cmd_t o = {0};
    uint16_t cnt = 0;
    for (uint32_t now = 0; now <= 5000; now += 100, cnt = (uint16_t)(cnt + 8))
        o = blower_ctrl_step(&c, 90.0f, 120.0f, false, true, cnt, now, 0.1f, 2);
    assert(NEAR(o.rpm, 2400.0, 1.0) && o.power_cap_pct == 100 && !o.blower_failed);
    /* The stall threshold is above the quantum of one tach window (1 pulse / 250 ms). */
    assert(BLOWER_STALL_RPM > 60000.0f / (BLOWER_TACH_WINDOW_MS * BLOWER_TACH_PULSES_PER_REV));
}

/* The controller's tank cap is the lower of the coil derate and the stall derate. */
static void test_blower_ctrl_coil_cap(void)
{
    blower_ctrl_t c;
    blower_ctrl_init(&c);
    uint16_t cnt = 0;
    blower_cmd_t o = {0};
    for (uint32_t now = 0; now <= 1000; now += 100, cnt = (uint16_t)(cnt + 8))
        o = blower_ctrl_step(&c, 90.0f, 155.0f, false, true, cnt, now, 0.1f, 2);
    assert(o.power_cap_pct == 50 && o.on && o.duty < BLOWER_PWM_DUTY_MAX);
}

/* ---------------------------------------------------------------- sensor plausibility */
static void test_rim_plausibility(void)
{
    thermal_plaus_t p;
    thermal_plaus_init(&p);
    uint32_t t = 0;
    /* Rim cold/open, pan 160 C: 30 s is not enough, > 30 s latches. */
    for (; t <= RIM_PLAUS_TIME_MS; t += 100) thermal_plaus_update(&p, t, true, 160.0f, true, 60.0f, 80);
    assert(!p.rim_fault && p.rim_ms == RIM_PLAUS_TIME_MS);
    thermal_plaus_update(&p, t, true, 160.0f, true, 60.0f, 80);
    assert(p.rim_fault && !p.coil_fault);
    /* Latched: a good rim later does not clear it. */
    thermal_plaus_update(&p, t + 100, false, 160.0f, true, 60.0f, 80);
    assert(p.rim_fault);
    /* Interruptions restart the 30 s: pan at 150 C (not above), RTD invalid, rim reading. */
    const struct { bool rim; float pan; bool rtd; } brk[] = {{true, 150.0f, true}, {true, 200.0f, false},
                                                            {false, 200.0f, true}};
    for (unsigned k = 0; k < 3; k++) {
        thermal_plaus_init(&p);
        for (t = 0; t < 20000; t += 100) thermal_plaus_update(&p, t, true, 200.0f, true, 60.0f, 80);
        thermal_plaus_update(&p, t, brk[k].rim, brk[k].pan, brk[k].rtd, 60.0f, 80);
        for (t += 100; t < 45000; t += 100) thermal_plaus_update(&p, t, true, 200.0f, true, 60.0f, 80);
        assert(!p.rim_fault);
    }
    /* A long gap between calls (not heating) counts at most THERMAL_PLAUS_MAX_STEP_MS. */
    thermal_plaus_init(&p);
    thermal_plaus_update(&p, 0, true, 200.0f, true, 60.0f, 80);
    thermal_plaus_update(&p, 60000, true, 200.0f, true, 60.0f, 80);
    assert(!p.rim_fault && p.rim_ms == THERMAL_PLAUS_MAX_STEP_MS);
}

static void test_coil_plausibility(void)
{
    thermal_plaus_t p;
    thermal_plaus_init(&p);
    uint32_t t = 0;
    /* Coil at 15 C (the ADC floor: cold or open) at 80 % power: > 5 min latches. */
    for (; t <= COIL_PLAUS_TIME_MS; t += 100) thermal_plaus_update(&p, t, false, 100.0f, true, 15.0f, 80);
    assert(!p.coil_fault);
    thermal_plaus_update(&p, t, false, 100.0f, true, 15.0f, 80);
    assert(p.coil_fault && !p.rim_fault);
    thermal_plaus_update(&p, t + 100, false, 100.0f, true, 90.0f, 80);
    assert(p.coil_fault); /* latched */
    /* Time at <= 50 % power does not count, but does not clear either (cumulative). */
    thermal_plaus_init(&p);
    for (t = 0; t < 200000; t += 100) thermal_plaus_update(&p, t, false, 100.0f, true, 15.0f, 80);
    for (; t < 800000; t += 100) thermal_plaus_update(&p, t, false, 100.0f, true, 15.0f, COIL_PLAUS_POWER_PCT);
    assert(!p.coil_fault && p.coil_ms == 199900u); /* first call primes (dt 0) */
    for (; t < 902000; t += 100) thermal_plaus_update(&p, t, false, 100.0f, true, 15.0f, 51);
    assert(p.coil_fault);
    /* A reading at or above 25 C restarts it; NaN (the interlock's case) is ignored. */
    thermal_plaus_init(&p);
    for (t = 0; t < 250000; t += 100) thermal_plaus_update(&p, t, false, 100.0f, true, 20.0f, 100);
    thermal_plaus_update(&p, t, false, 100.0f, true, COIL_PLAUS_COLD_C, 100);
    assert(p.coil_ms == 0u);
    for (t += 100; t < 500000; t += 100) thermal_plaus_update(&p, t, false, 100.0f, true, NAN, 100);
    assert(!p.coil_fault && p.coil_ms == 0u);
    /* The clamp the fault applies is the shipping commissioned ceiling. */
    assert(COIL_SENSOR_FAULT_TANK_MAX_A <= 22.0f);
}

int main(void)
{
    TEST(test_ntc_round_trip);
    TEST(test_vishay_curve_against_rt_table);
    TEST(test_semitec_104gt2_conversion);
    TEST(test_coil_sink_open_short_fail_safe);
    TEST(test_rim_parameterised);
    TEST(test_rim_open_short_and_hot_end);
    TEST(test_trip_ladder_order);
    TEST(test_hardware_trip_points_from_resistors);
    TEST(test_input_rc_allowance);
    TEST(test_pan_cap);
    TEST(test_fan_law_on_off_hysteresis);
    TEST(test_fan_law_max_of_loops_and_cap);
    TEST(test_fan_law_fault_full_speed);
    TEST(test_blower_stall);
    TEST(test_blower_pwm_inverted_and_fail_safe);
    TEST(test_blower_tach);
    TEST(test_tach_zero_derates);
    TEST(test_blower_ctrl_coil_cap);
    TEST(test_rim_plausibility);
    TEST(test_coil_plausibility);
    printf("thermal management: %u tests passed\n", tests);
    return 0;
}
