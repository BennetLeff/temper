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
            if (mv <= ch[i]->v_short_mv || mv >= ch[i]->v_open_mv) continue;
            assert(ntc_channel_temp_c(ch[i], mv, &back) == NTC_OK);
            assert(NEAR(back, t, 0.05));
        }
    /* 10 k on 10 k: half supply at 25 C. */
    float t = 0.0f;
    assert(ntc_channel_temp_c(&THERMAL_NTC_RIM, 1652.0f, &t) == NTC_OK && NEAR(t, 25.0, 0.01));
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
    assert(mv250 > THERMAL_NTC_RIM.v_short_mv);
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
