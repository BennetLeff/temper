#include "unity.h"
#include "coil_guard.h"
#include <math.h>
#include "thermal_mgmt.h"

void setUp(void) {}
void tearDown(void) {}

void test_coil_guard_init(void) {
    coil_guard_t ctx;
    coil_guard_init(&ctx);
    TEST_ASSERT_FALSE(ctx.baseline_valid);
}

void test_normal_operation(void) {
    coil_guard_t ctx;
    coil_guard_init(&ctx);
    coil_guard_set_baseline(&ctx, 35000.0f);
    
    // Slight drift (35.5kHz) -> OK
    TEST_ASSERT_EQUAL(COIL_GUARD_OK, coil_guard_update(&ctx, 35500.0f, 50.0f));
}

void test_inductance_drop_warn(void) {
    coil_guard_t ctx;
    coil_guard_init(&ctx);
    coil_guard_set_baseline(&ctx, 35000.0f);
    
    // Warn threshold: 10% L drop
    // L_new = 0.9 * L_old
    // f_new = f_old / sqrt(0.9) = 1.054 * f_old
    // 35000 * 1.054 = 36890 Hz
    
    TEST_ASSERT_EQUAL(COIL_GUARD_WARN_INDUCTANCE_LOW, 
        coil_guard_update(&ctx, 37000.0f, 50.0f));
}

void test_inductance_drop_fault(void) {
    coil_guard_t ctx;
    coil_guard_init(&ctx);
    coil_guard_set_baseline(&ctx, 35000.0f);
    
    // Fault threshold: 20% L drop
    // L_new = 0.8 * L_old
    // f_new = f_old / sqrt(0.8) = 1.118 * f_old
    // 35000 * 1.118 = 39130 Hz
    
    TEST_ASSERT_EQUAL(COIL_GUARD_ERR_SHORTED, 
        coil_guard_update(&ctx, 40000.0f, 50.0f));
}

void test_overtemp(void) {
    coil_guard_t ctx;
    coil_guard_init(&ctx);
    
    /* 130 C is inside the fan's coil loop range (setpoint 140 C), not a fault any more. */
    TEST_ASSERT_EQUAL(COIL_GUARD_OK, coil_guard_update(&ctx, 35000.0f, 130.0f));
    TEST_ASSERT_EQUAL(COIL_GUARD_OK, coil_guard_update(&ctx, 35000.0f, 150.0f));
    TEST_ASSERT_EQUAL(COIL_GUARD_WARN_DERATING, coil_guard_update(&ctx, 35000.0f, 155.0f));
    TEST_ASSERT_EQUAL(COIL_GUARD_WARN_DERATING, coil_guard_update(&ctx, 35000.0f, 164.9f));
    TEST_ASSERT_EQUAL(COIL_GUARD_ERR_OVERTEMP, coil_guard_update(&ctx, 35000.0f, 165.0f));
    TEST_ASSERT_EQUAL(COIL_GUARD_ERR_OVERTEMP, coil_guard_update(&ctx, 35000.0f, 190.0f));
}

/* An invalid coil reading (open / short / NaN) is a fault, never "no sensor". */
void test_invalid_coil_reading_fails_safe(void) {
    coil_guard_t ctx;
    coil_guard_init(&ctx);
    TEST_ASSERT_EQUAL(COIL_GUARD_ERR_SENSOR, coil_guard_update(&ctx, 35000.0f, NAN));
    TEST_ASSERT_EQUAL(COIL_GUARD_ERR_SENSOR, coil_guard_update(&ctx, 35000.0f, -999.0f));
    TEST_ASSERT_EQUAL(COIL_GUARD_ERR_SENSOR, coil_guard_update(&ctx, 35000.0f, -21.0f));
    TEST_ASSERT_EQUAL(0, coil_tank_cap_pct(NAN));
    TEST_ASSERT_EQUAL_FLOAT(THERMAL_NTC_COIL.t_open_c, COIL_TEMP_VALID_MIN_C);
}

/* The guard and the thermal_mgmt loops cannot contradict each other:
 *  - order: coil loop setpoint < derate start < derate end < hard trip < sensor "short" class;
 *  - at every temperature the fan law and the guard read the same derate (one function);
 *  - wherever the guard trips, the derate already asks for zero tank power, and wherever the
 *    derate still allows power, the guard does not trip;
 *  - at the coil loop's setpoint there is neither a derate nor a guard warning. */
void test_guard_and_fan_law_agree(void) {
    TEST_ASSERT_TRUE(COIL_SETPOINT_C < COIL_DERATE_C);
    TEST_ASSERT_TRUE(COIL_DERATE_C < COIL_DERATE_END_C);
    TEST_ASSERT_TRUE(COIL_DERATE_END_C < COIL_MAX_TEMP_C);
    TEST_ASSERT_TRUE(COIL_MAX_TEMP_C < THERMAL_NTC_COIL.t_short_c);
    TEST_ASSERT_EQUAL_FLOAT(140.0f, COIL_SETPOINT_C);
    TEST_ASSERT_EQUAL_FLOAT(150.0f, COIL_DERATE_C);
    TEST_ASSERT_EQUAL_FLOAT(165.0f, COIL_MAX_TEMP_C);

    coil_guard_t g;
    coil_guard_init(&g);
    for (int i = 0; i <= 2000; i++) {
        float t = (float)i * 0.1f; /* 0 .. 200 C */
        fan_law_t f;
        fan_law_init(&f);
        fan_law_step(&f, 60.0f, t, 0.1f, false);
        uint8_t cap = coil_tank_cap_pct(t);
        TEST_ASSERT_EQUAL_UINT8(cap, f.tank_cap_pct);
        TEST_ASSERT_EQUAL(cap < 100u, f.coil_limit);
        coil_guard_status_t st = coil_guard_update(&g, 35000.0f, t);
        if (st == COIL_GUARD_ERR_OVERTEMP) TEST_ASSERT_EQUAL_UINT8(0, cap);
        if (cap > 0u) TEST_ASSERT_NOT_EQUAL(COIL_GUARD_ERR_OVERTEMP, st);
        if (st == COIL_GUARD_OK) TEST_ASSERT_EQUAL_UINT8(100, cap);
        if (st == COIL_GUARD_WARN_DERATING) TEST_ASSERT_TRUE(cap < 100u);
        /* In a fault the fan law runs full speed and the same derate still applies. */
        fan_law_step(&f, 60.0f, t, 0.1f, true);
        TEST_ASSERT_EQUAL_UINT8(cap, f.tank_cap_pct);
    }
    /* Steady at the coil loop setpoint: fan drives, no derate, no warning. */
    fan_law_t f;
    fan_law_init(&f);
    for (int i = 0; i < 100; i++) fan_law_step(&f, 60.0f, COIL_SETPOINT_C + 0.5f, 0.1f, false);
    TEST_ASSERT_TRUE(f.on && f.drive > 0.0f && f.tank_cap_pct == 100u);
    TEST_ASSERT_EQUAL(COIL_GUARD_OK, coil_guard_update(&g, 35000.0f, COIL_SETPOINT_C + 0.5f));
}
