/* Thermal management: rim / coil / sink NTC conversion, the 250 C pan cap, the R32 fan law and the
 * L3 blower stall hook. Assertions are the oracle (built with -UNDEBUG). */
#include "thermal_mgmt.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static unsigned tests;
#define TEST(fn) do { fn(); tests++; printf("PASS %s\n", #fn); } while (0)
#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))

static void test_ntc_round_trip(void)
{
    const ntc_channel_t *ch[] = {&THERMAL_NTC_RIM, &THERMAL_NTC_COIL, &THERMAL_NTC_SINK};
    for (unsigned i = 0; i < 3; i++)
        for (float t = 0.0f; t <= 250.0f; t += 10.0f) {
            float mv = ntc_channel_mv_at(ch[i], t), back = -999.0f;
            if (t <= ch[i]->t_open_c || t >= ch[i]->t_short_c) continue;
            assert(ntc_channel_temp_c(ch[i], mv, &back) == NTC_OK);
            assert(NEAR(back, t, 0.1)); /* Vishay: the two formulae agree to 0.015 C, -40..125 C */
        }
    /* 10 k on 10 k: half supply at 25 C. */
    float t = 0.0f;
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, 1652.0f, &t) == NTC_OK && NEAR(t, 25.0, 0.01));
}

/* Vishay NTCLE100E3104 R-T table (doc 29049, rev. 07-May-2025, p. 12), the 100 k / 4190 K
 * +/- 1.5 % curve used for the coil and sink NTCALUG01A104GA. */
static void test_vishay_curve_against_rt_table(void)
{
    static const struct { float t_c, r_kohm; } tab[] = {
        {-20, 1041}, {0, 340.9}, {25, 100.0}, {50, 34.31}, {85, 9.496}, {100, 5.835},
        {120, 3.206}, {140, 1.854}, {150, 1.434}};
    for (unsigned i = 0; i < sizeof tab / sizeof tab[0]; i++) {
        float r = ntc_channel_r_at(&THERMAL_NTC_COIL, tab[i].t_c) / 1000.0f;
        assert(fabs(r / tab[i].r_kohm - 1.0) < 0.002); /* table is printed to 4 digits */
        float t = -999.0f;
        float mv = 3304.0f * tab[i].r_kohm / (tab[i].r_kohm + 10.0f);
        if (tab[i].t_c > -20.0f) {
            assert(ntc_channel_temp_c(&THERMAL_NTC_COIL, mv, &t) == NTC_OK);
            assert(NEAR(t, tab[i].t_c, 0.1));
        }
    }
    /* Divider voltages at the check points (10.0 k pull-up, 3.304 V). */
    const float pts[] = {25.0f, 100.0f, 140.0f, 150.0f};
    for (unsigned i = 0; i < 4; i++) {
        float mv = ntc_channel_mv_at(&THERMAL_NTC_COIL, pts[i]), t = 0.0f;
        assert(ntc_channel_temp_c(&THERMAL_NTC_SINK, mv, &t) == NTC_OK && NEAR(t, pts[i], 0.01));
        printf("  coil/sink node %5.1f C = %7.1f mV\n", pts[i], mv);
    }
    /* The plain B model this replaces is 9.8 % high in R at 150 C (about 3.5 K). */
    ntc_channel_t beta = THERMAL_NTC_COIL;
    beta.curve = NULL;
    float r_beta = ntc_channel_r_at(&beta, 150.0f);
    assert(r_beta / 1434.0f > 1.09f);
}

static void test_coil_sink_open_short_fail_safe(void)
{
    const ntc_channel_t *ch[] = {&THERMAL_NTC_COIL, &THERMAL_NTC_SINK};
    for (unsigned i = 0; i < 2; i++) {
        float t;
        assert(ntc_channel_temp_c(ch[i], 3304.0f, &t) == NTC_OPEN);
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], -20.5f), &t) == NTC_OPEN);
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], -19.0f), &t) == NTC_OK);
        assert(ntc_channel_temp_c(ch[i], 0.0f, &t) == NTC_SHORT);
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], 201.0f), &t) == NTC_SHORT);
        assert(ntc_channel_temp_c(ch[i], ntc_channel_mv_at(ch[i], 190.0f), &t) == NTC_OK);
        assert(ntc_channel_temp_c(ch[i], NAN, &t) == NTC_BAD_ARG);
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
    /* Thresholds follow R / B: a drop-in pull-up or NTC change needs no other edit. */
    ntc_channel_t rim = THERMAL_NTC_RIM;
    assert(rim.r_pullup_ohm == RIM_NTC_R_PULLUP_OHM && rim.r25_ohm == RIM_NTC_R25_OHM &&
           rim.beta_k == RIM_NTC_BETA_K && rim.curve == NULL);
    rim.r_pullup_ohm = 1000.0f; /* e.g. a lower pull-up for resolution at 250 C */
    float t;
    float mv250 = ntc_channel_mv_at(&rim, 250.0f);
    assert(mv250 > ntc_channel_mv_at(&THERMAL_NTC_RIM, 250.0f) * 5.0f);
    assert(ntc_channel_temp_c(&rim, mv250, &t) == NTC_OK && NEAR(t, 250.0, 0.1));
    assert(ntc_channel_temp_c(&rim, ntc_channel_mv_at(&rim, -21.0f), &t) == NTC_OPEN);
    assert(ntc_channel_temp_c(&rim, ntc_channel_mv_at(&rim, 321.0f), &t) == NTC_SHORT);
    rim.beta_k = 3500.0f;
    assert(ntc_channel_temp_c(&rim, ntc_channel_mv_at(&rim, 250.0f), &t) == NTC_OK && NEAR(t, 250.0, 0.1));
}

/* Evidence only (not a pass/fail on the design): the thermal-sense block's hardware hot trips,
 * from its resistor values (controller-layout thermal_block.ato: 10 k pull-up; HS ref 9.09 k /
 * 11.5 k with 34.8 k hysteresis; coil ref 20 k / 8.06 k with 42.2 k; TLV3201 output low before
 * the trip), through the same R-T model. Reported because they sit below R32's fan-law setpoints. */
static void test_hardware_trip_points_recorded(void)
{
    double hs_lo = 1.0 / (1.0 / 11.5 + 1.0 / 34.8), coil_lo = 1.0 / (1.0 / 8.06 + 1.0 / 42.2);
    float hs_mv = (float)(3304.0 * hs_lo / (9.09 + hs_lo));
    float coil_mv = (float)(3304.0 * coil_lo / (20.0 + coil_lo));
    float hs_c = 0.0f, coil_c = 0.0f;
    assert(ntc_channel_temp_c(&THERMAL_NTC_SINK, hs_mv, &hs_c) == NTC_OK);
    assert(ntc_channel_temp_c(&THERMAL_NTC_COIL, coil_mv, &coil_c) == NTC_OK);
    printf("  hardware hot trip: heatsink %.1f C (fan sink setpoint %.1f C), coil %.1f C "
           "(fan coil setpoint %.1f C, derate %.1f C)\n",
           hs_c, FAN_SINK_SETPOINT_C, coil_c, FAN_COIL_SETPOINT_C, FAN_COIL_LIMIT_C);
    assert(hs_c > 80.0f && hs_c < 90.0f && coil_c > 110.0f && coil_c < 125.0f);
}

static void test_rim_open_short_and_hot_end(void)
{
    float t;
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, 3290.0f, &t) == NTC_OPEN);   /* unplugged J12 */
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, 1.0f, &t) == NTC_SHORT);
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, NAN, &t) == NTC_BAD_ARG);
    /* The 250 C cap must stay distinguishable from a short: the node at 250 C is above the short
     * threshold, and reads back as hot. This also records how small the hot end is (see report). */
    float mv250 = ntc_channel_mv_at(&THERMAL_NTC_RIM, 250.0f);
    float mv240 = ntc_channel_mv_at(&THERMAL_NTC_RIM, 240.0f);
    printf("  rim node: 240 C = %.2f mV, 250 C = %.2f mV, slope %.3f mV/K\n", mv240, mv250,
           (mv240 - mv250) / 10.0f);
    assert(mv250 > ntc_channel_mv_at(&THERMAL_NTC_RIM, THERMAL_NTC_RIM.t_short_c));
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, mv250, &t) == NTC_OK && NEAR(t, 250.0, 0.1));
    /* Coil at its 150 C limit is far from both rails. */
    float coil150 = ntc_channel_mv_at(&THERMAL_NTC_COIL, 150.0f);
    assert(coil150 > 200.0f && coil150 < 1000.0f);
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

static void test_blower_stall(void)
{
    blower_stall_t s;
    blower_stall_init(&s);
    /* Healthy tach: no derate. */
    assert(blower_stall_update(&s, true, 60.0f, 0, 70.0f, 100.0f) == 100);
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
    assert(blower_stall_update(&s, true, 60.0f, 5000, 72.5f, 101.0f) == 100 && !s.stalled);
    /* Blower switched off by the fan law is not a stall. */
    for (uint32_t t = 6000; t < 10000; t += 100) assert(blower_stall_update(&s, false, 0.0f, t, 40.0f, 40.0f) == 100);
    /* Timer wrap is harmless (unsigned difference). */
    blower_stall_init(&s);
    assert(blower_stall_update(&s, true, 0.0f, 0xFFFFFF00u, 70.0f, 100.0f) == 100);
    assert(blower_stall_update(&s, true, 0.0f, 0x00000400u, 70.0f, 100.0f) == BLOWER_STALL_POWER_CAP_PCT);
}

static void test_blower_duty_stub(void)
{
    /* GPIO46 duty 0 = full speed (the strap pull-down default): drive 1 -> duty 0. */
    assert(blower_pwm_duty_from_drive(1.0f) == 0.0f);
    assert(blower_pwm_duty_from_drive(0.0f) == 1.0f);
    assert(blower_pwm_duty_from_drive(2.0f) == 0.0f);
    assert(blower_pwm_duty_from_drive(NAN) == 0.0f);
}

int main(void)
{
    TEST(test_ntc_round_trip);
    TEST(test_vishay_curve_against_rt_table);
    TEST(test_coil_sink_open_short_fail_safe);
    TEST(test_rim_parameterised);
    TEST(test_hardware_trip_points_recorded);
    TEST(test_rim_open_short_and_hot_end);
    TEST(test_pan_cap);
    TEST(test_fan_law_on_off_hysteresis);
    TEST(test_fan_law_max_of_loops_and_cap);
    TEST(test_fan_law_fault_full_speed);
    TEST(test_blower_stall);
    TEST(test_blower_duty_stub);
    printf("thermal management: %u tests passed\n", tests);
    return 0;
}
