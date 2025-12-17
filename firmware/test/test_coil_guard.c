#include "unity.h"
#include "coil_guard.h"
#include <math.h>

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
    
    TEST_ASSERT_EQUAL(COIL_GUARD_ERR_OVERTEMP, 
        coil_guard_update(&ctx, 35000.0f, 130.0f));
}
