#include "unity.h"
#include "profiles.h"
#include <string.h>

void setUp(void) {}
void tearDown(void) {}

void test_profile_init(void) {
    profile_status_t status;
    profile_init_status(&status);
    
    TEST_ASSERT_NULL(status.active_profile);
    TEST_ASSERT_FALSE(status.active);
    TEST_ASSERT_FALSE(status.completed);
}

void test_profile_start(void) {
    profile_status_t status;
    profile_init_status(&status);
    
    const cooking_profile_t *simmer = profile_get_simmer();
    profile_start(&status, simmer, 1000);
    
    TEST_ASSERT_EQUAL(simmer, status.active_profile);
    TEST_ASSERT_TRUE(status.active);
    TEST_ASSERT_EQUAL(0, status.current_stage_idx);
    TEST_ASSERT_EQUAL(1000, status.stage_start_time_ms);
}

void test_profile_transition_time(void) {
    profile_status_t status;
    profile_init_status(&status);
    
    // Sear & Hold has 2 stages
    // Stage 0: 230C, 120000ms
    // Stage 1: 65C, 0ms (hold)
    const cooking_profile_t *sear = profile_get_sear_and_hold();
    profile_start(&status, sear, 1000);
    
    // 1. Before timeout
    bool changed = profile_update(&status, 25.0f, 1000 + 60000);
    TEST_ASSERT_FALSE(changed);
    TEST_ASSERT_EQUAL(0, status.current_stage_idx);
    
    // 2. After timeout
    changed = profile_update(&status, 230.0f, 1000 + 120001);
    TEST_ASSERT_TRUE(changed);
    TEST_ASSERT_EQUAL(1, status.current_stage_idx);
    TEST_ASSERT_EQUAL(1000 + 120001, status.stage_start_time_ms);
    
    // 3. Final stage (hold indefinitely)
    changed = profile_update(&status, 65.0f, 1000 + 200000);
    TEST_ASSERT_FALSE(changed);
    TEST_ASSERT_EQUAL(1, status.current_stage_idx);
}

void test_profile_completion(void) {
    cooking_profile_t custom = {
        .name = "Quick",
        .num_stages = 1,
        .stages = {
            { .target_temp = 100.0f, .intensity = 5, .duration_ms = 1000, .use_probe = false }
        }
    };
    
    profile_status_t status;
    profile_init_status(&status);
    profile_start(&status, &custom, 0);
    
    // Update after timeout
    bool changed = profile_update(&status, 100.0f, 1001);
    TEST_ASSERT_TRUE(changed);
    TEST_ASSERT_TRUE(status.completed);
    TEST_ASSERT_FALSE(status.active);
}

void test_profile_settings(void) {
    const cooking_profile_t *sear = profile_get_sear_and_hold();
    profile_status_t status;
    profile_init_status(&status);
    profile_start(&status, sear, 0);
    
    float temp;
    uint8_t intensity;
    bool probe;
    
    profile_get_current_settings(&status, &temp, &intensity, &probe);
    TEST_ASSERT_EQUAL_FLOAT(230.0f, temp);
    TEST_ASSERT_EQUAL(10, intensity);
    TEST_ASSERT_FALSE(probe);
}
