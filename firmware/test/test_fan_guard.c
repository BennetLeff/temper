#include "unity.h"
#include "fan_guard.h"
#include <string.h>

// Mock time
static uint32_t mock_tick_ms = 0;

uint32_t hal_get_tick_ms(void) {
    return mock_tick_ms;
}

void setUp(void) {
    mock_tick_ms = 1000;
}

void tearDown(void) {}

void test_fan_guard_init(void) {
    fan_guard_t ctx;
    fan_guard_init(&ctx);
    TEST_ASSERT_EQUAL(1000, ctx.last_check_ms);
}

void test_normal_operation(void) {
    fan_guard_t ctx;
    fan_guard_init(&ctx);
    
    // Step 1 sec, temp rises 0.1C (normal)
    mock_tick_ms += 1000;
    fan_guard_status_t status = fan_guard_update(&ctx, 25.1f, 1000.0f, 25.0f, true);
    
    TEST_ASSERT_EQUAL(FAN_GUARD_OK, status);
}

void test_rapid_rise_blocked(void) {
    fan_guard_t ctx;
    fan_guard_init(&ctx);
    
    // Step 1 sec, temp rises 2.0C (very fast!)
    mock_tick_ms += 1000;
    // 2.0C/s > 0.5 * 2 = 1.0 -> BLOCKED
    fan_guard_status_t status = fan_guard_update(&ctx, 27.0f, 1000.0f, 25.0f, true);
    
    TEST_ASSERT_EQUAL(FAN_GUARD_ERR_BLOCKED, status);
}

void test_moderate_rise_restricted(void) {
    fan_guard_t ctx;
    fan_guard_init(&ctx);
    
    // Step 1 sec, temp rises 0.6C
    mock_tick_ms += 1000;
    // 0.6 > 0.5 but < 1.0 -> RESTRICTED
    fan_guard_status_t status = fan_guard_update(&ctx, 25.6f, 1000.0f, 25.0f, true);
    
    TEST_ASSERT_EQUAL(FAN_GUARD_WARN_RESTRICTED, status);
}

void test_equilibrium_degraded(void) {
    fan_guard_t ctx;
    fan_guard_init(&ctx);
    
    // Set previous state to high temp so rate calculation is low
    // 59.9 -> 60.0 over 6 seconds is very slow rate
    ctx.last_temp_c = 59.9f; 
    
    // Long run...
    mock_tick_ms += 6000; // > 5s wait
    
    // Power = 100W -> Loss ~5W -> Rise ~5C
    // Expected max = 25 + 5 + 20 = 50C
    // Actual = 60C -> Degraded
    fan_guard_status_t status = fan_guard_update(&ctx, 60.0f, 100.0f, 25.0f, true);
    
    TEST_ASSERT_EQUAL(FAN_GUARD_WARN_DEGRADED, status);
}
