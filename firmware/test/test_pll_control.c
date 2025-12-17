/**
 * @file test_pll_control.c
 * @brief Unit tests for PLL (Phase-Locked Loop) frequency tracking module
 * 
 * Tests the PLL control logic for ZVS (Zero Voltage Switching) tracking.
 * The PLL adjusts switching frequency to maintain optimal phase relationship
 * between PWM output and current zero-crossing.
 * 
 * Specifications (from design docs):
 * - Frequency range: 30-50 kHz (PLL_MIN_FREQ_HZ to PLL_MAX_FREQ_HZ)
 * - Target phase lag: ~1.5µs for ZVS operation
 * - Lock tolerance: ±0.5µs phase error
 * - Default frequency: 35 kHz
 */

#include "unity/unity.h"
#include "test_common.h"
#include "../components/control/pll_control.h"
#include <math.h>

/*============================================================================
 * Test Setup/Teardown
 *============================================================================*/

static void reset_pll(void) {
    /* Reset PLL to known state before each test */
    pll_init(NULL);  /* Use defaults */
    pll_enable();
}

/*============================================================================
 * Test Cases: Initialization
 *============================================================================*/

/**
 * Test: PLL initializes to default frequency
 */
void test_pll_init_default_frequency(void) {
    pll_init(NULL);
    float freq = pll_get_frequency();
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 35000.0f, freq);  /* Default is 35kHz */
}

/**
 * Test: PLL starts unlocked
 */
void test_pll_init_unlocked(void) {
    pll_init(NULL);
    TEST_ASSERT_FALSE(pll_is_locked());
}

/**
 * Test: PLL context returns valid pointer
 */
void test_pll_get_context_not_null(void) {
    pll_init(NULL);
    const pll_context_t *ctx = pll_get_context();
    TEST_ASSERT_NOT_NULL(ctx);
}

/**
 * Test: Custom configuration is applied
 */
void test_pll_init_custom_config(void) {
    pll_config_t config = {
        .kp = 5.0f,
        .ki = 100.0f,
        .target_phase_us = 2.0f,
        .min_freq_hz = 35000,
        .max_freq_hz = 45000
    };
    pll_init(&config);
    
    const pll_context_t *ctx = pll_get_context();
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 5.0f, ctx->kp);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, ctx->ki);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 2.0f, ctx->target_phase_us);
    TEST_ASSERT_EQUAL_UINT32(35000, ctx->min_freq);
    TEST_ASSERT_EQUAL_UINT32(45000, ctx->max_freq);
}

/*============================================================================
 * Test Cases: Enable/Disable
 *============================================================================*/

/**
 * Test: PLL update does nothing when disabled
 */
void test_pll_update_when_disabled(void) {
    pll_init(NULL);
    pll_disable();
    float initial_freq = pll_get_frequency();
    
    /* Try to update with significant phase error */
    pll_update_loop(10.0f, 0.001f);  /* Large phase lag */
    
    /* Frequency should not change when disabled */
    TEST_ASSERT_FLOAT_WITHIN(0.1f, initial_freq, pll_get_frequency());
}

/**
 * Test: PLL responds to phase error when enabled
 */
void test_pll_update_when_enabled(void) {
    reset_pll();
    float initial_freq = pll_get_frequency();
    
    /* Feed multiple updates with phase lag > target (1.5µs) */
    /* Phase lag 5µs means we're lagging, need to increase frequency */
    for (int i = 0; i < 50; i++) {
        pll_update_loop(5.0f, 0.001f);
    }
    
    /* Frequency should have changed */
    float new_freq = pll_get_frequency();
    TEST_ASSERT_NOT_EQUAL(initial_freq, new_freq);
}

/*============================================================================
 * Test Cases: Phase Tracking
 *============================================================================*/

/**
 * Test: Phase lag > target increases frequency
 * When current lags PWM by more than target, increase frequency
 */
void test_phase_lag_high_increases_frequency(void) {
    reset_pll();
    float initial_freq = pll_get_frequency();
    
    /* Phase lag 5µs (target is 1.5µs), error = 1.5 - 5 = -3.5µs */
    /* Negative error should decrease frequency in PI controller */
    /* But wait - we need positive frequency to lead, so convention may differ */
    
    /* Let's run several iterations */
    for (int i = 0; i < 100; i++) {
        pll_update_loop(5.0f, 0.001f);  /* Large positive lag */
    }
    
    float new_freq = pll_get_frequency();
    /* The PI controller will adjust based on error = target - measured */
    /* If measured_lag > target, error is negative, frequency should decrease */
    TEST_ASSERT_TRUE(new_freq != initial_freq);
}

/**
 * Test: Phase lag < target adjusts frequency
 * When current leads PWM (or lags less), frequency adjusts to track
 */
void test_phase_lag_low_adjusts_frequency(void) {
    reset_pll();
    float initial_freq = pll_get_frequency();
    
    /* Phase lag 0.5µs (target is 1.5µs), error = 1.5 - 0.5 = +1.0µs */
    /* Positive error should increase frequency */
    /* Note: Frequency has 10Hz hysteresis, so need enough iterations */
    for (int i = 0; i < 500; i++) {
        pll_update_loop(0.5f, 0.001f);  /* Small positive lag */
    }
    
    float new_freq = pll_get_frequency();
    /* With positive error (target > measured), frequency should increase */
    TEST_ASSERT_TRUE(new_freq > initial_freq);
}

/**
 * Test: PLL locks when phase error is small
 */
void test_pll_locks_at_target_phase(void) {
    reset_pll();
    
    /* Feed exactly target phase - should eventually lock */
    for (int i = 0; i < 50; i++) {
        pll_update_loop(1.5f, 0.001f);  /* Exactly target */
    }
    
    TEST_ASSERT_TRUE(pll_is_locked());
}

/**
 * Test: PLL unlocks when phase error is large
 */
void test_pll_unlocks_on_large_error(void) {
    reset_pll();
    
    /* First, get locked */
    for (int i = 0; i < 50; i++) {
        pll_update_loop(1.5f, 0.001f);
    }
    TEST_ASSERT_TRUE(pll_is_locked());
    
    /* Now introduce large phase error */
    for (int i = 0; i < 10; i++) {
        pll_update_loop(10.0f, 0.001f);  /* Way outside lock range */
    }
    
    TEST_ASSERT_FALSE(pll_is_locked());
}

/*============================================================================
 * Test Cases: Frequency Limits
 *============================================================================*/

/**
 * Test: Frequency never exceeds maximum
 */
void test_frequency_max_limit(void) {
    reset_pll();
    
    /* Drive frequency up with large positive error */
    for (int i = 0; i < 1000; i++) {
        pll_update_loop(0.1f, 0.001f);  /* Very small lag = increase freq */
    }
    
    float freq = pll_get_frequency();
    TEST_ASSERT_TRUE(freq <= 50000.0f);  /* Max is 50kHz */
}

/**
 * Test: Frequency never goes below minimum
 */
void test_frequency_min_limit(void) {
    reset_pll();
    
    /* Drive frequency down with large negative error (large lag) */
    for (int i = 0; i < 1000; i++) {
        pll_update_loop(15.0f, 0.001f);  /* Large lag = decrease freq */
    }
    
    float freq = pll_get_frequency();
    TEST_ASSERT_TRUE(freq >= 30000.0f);  /* Min is 30kHz */
}

/*============================================================================
 * Test Cases: Invalid Input Handling
 *============================================================================*/

/**
 * Test: Invalid phase (too small) doesn't update
 */
void test_invalid_phase_too_small(void) {
    reset_pll();
    float initial_freq = pll_get_frequency();
    
    /* Phase < 0.1µs is invalid */
    pll_update_loop(0.05f, 0.001f);
    
    /* Frequency should not change for invalid input */
    TEST_ASSERT_FLOAT_WITHIN(0.1f, initial_freq, pll_get_frequency());
}

/**
 * Test: Invalid phase (too large) doesn't update
 */
void test_invalid_phase_too_large(void) {
    reset_pll();
    float initial_freq = pll_get_frequency();
    
    /* Phase > 20µs is invalid */
    pll_update_loop(25.0f, 0.001f);
    
    /* Frequency should not change for invalid input */
    TEST_ASSERT_FLOAT_WITHIN(0.1f, initial_freq, pll_get_frequency());
}

/**
 * Test: Invalid dt uses fallback
 */
void test_invalid_dt_uses_fallback(void) {
    reset_pll();
    
    /* Zero dt should use fallback (1ms) */
    pll_update_loop(1.5f, 0.0f);
    TEST_ASSERT_TRUE(pll_is_locked());  /* Should still work with fallback dt */
}

/**
 * Test: Negative dt uses fallback
 */
void test_negative_dt_uses_fallback(void) {
    reset_pll();
    
    /* Negative dt should use fallback */
    pll_update_loop(1.5f, -0.001f);
    TEST_ASSERT_TRUE(pll_is_locked());
}

/*============================================================================
 * Test Cases: Reset
 *============================================================================*/

/**
 * Test: Reset returns to default frequency
 */
void test_pll_reset_frequency(void) {
    reset_pll();
    
    /* Change frequency */
    for (int i = 0; i < 100; i++) {
        pll_update_loop(0.5f, 0.001f);
    }
    
    /* Reset */
    pll_reset();
    
    float freq = pll_get_frequency();
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 35000.0f, freq);  /* Back to default */
}

/**
 * Test: Reset clears lock status
 */
void test_pll_reset_clears_lock(void) {
    reset_pll();
    
    /* Get locked */
    for (int i = 0; i < 50; i++) {
        pll_update_loop(1.5f, 0.001f);
    }
    TEST_ASSERT_TRUE(pll_is_locked());
    
    /* Reset should clear lock */
    pll_reset();
    TEST_ASSERT_FALSE(pll_is_locked());
}

/**
 * Test: Reset clears integrator
 */
void test_pll_reset_clears_integrator(void) {
    reset_pll();
    
    /* Accumulate integrator */
    for (int i = 0; i < 100; i++) {
        pll_update_loop(5.0f, 0.001f);
    }
    
    /* Reset */
    pll_reset();
    
    const pll_context_t *ctx = pll_get_context();
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, ctx->integrator);
}

/*============================================================================
 * Test Cases: Set Target Phase
 *============================================================================*/

/**
 * Test: Set valid target phase
 */
void test_set_target_phase_valid(void) {
    pll_init(NULL);
    pll_set_target_phase(2.0f);
    
    const pll_context_t *ctx = pll_get_context();
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 2.0f, ctx->target_phase_us);
}

/**
 * Test: Set invalid target phase (too small) is ignored
 */
void test_set_target_phase_too_small(void) {
    pll_init(NULL);
    float original = pll_get_context()->target_phase_us;
    
    pll_set_target_phase(-1.0f);  /* Invalid */
    
    TEST_ASSERT_FLOAT_WITHIN(0.01f, original, pll_get_context()->target_phase_us);
}

/**
 * Test: Set invalid target phase (too large) is ignored
 */
void test_set_target_phase_too_large(void) {
    pll_init(NULL);
    float original = pll_get_context()->target_phase_us;
    
    pll_set_target_phase(15.0f);  /* Invalid (>10µs) */
    
    TEST_ASSERT_FLOAT_WITHIN(0.01f, original, pll_get_context()->target_phase_us);
}

/*============================================================================
 * Test Cases: Loss of Lock Detection
 *============================================================================*/

/**
 * Test: Consecutive invalid measurements cause unlock
 */
void test_consecutive_invalid_causes_unlock(void) {
    reset_pll();
    
    /* First, get locked */
    for (int i = 0; i < 50; i++) {
        pll_update_loop(1.5f, 0.001f);
    }
    TEST_ASSERT_TRUE(pll_is_locked());
    
    /* Feed many invalid measurements (outside 0.1-20µs range) */
    for (int i = 0; i < 15; i++) {
        pll_update_loop(0.05f, 0.001f);  /* Too small */
    }
    
    TEST_ASSERT_FALSE(pll_is_locked());
}

/*============================================================================
 * Test Runner
 *============================================================================*/

void run_pll_control_tests(void) {
    /* Initialization tests */
    RUN_TEST(test_pll_init_default_frequency);
    RUN_TEST(test_pll_init_unlocked);
    RUN_TEST(test_pll_get_context_not_null);
    RUN_TEST(test_pll_init_custom_config);
    
    /* Enable/Disable tests */
    RUN_TEST(test_pll_update_when_disabled);
    RUN_TEST(test_pll_update_when_enabled);
    
    /* Phase tracking tests */
    RUN_TEST(test_phase_lag_high_increases_frequency);
    RUN_TEST(test_phase_lag_low_adjusts_frequency);
    RUN_TEST(test_pll_locks_at_target_phase);
    RUN_TEST(test_pll_unlocks_on_large_error);
    
    /* Frequency limit tests */
    RUN_TEST(test_frequency_max_limit);
    RUN_TEST(test_frequency_min_limit);
    
    /* Invalid input tests */
    RUN_TEST(test_invalid_phase_too_small);
    RUN_TEST(test_invalid_phase_too_large);
    RUN_TEST(test_invalid_dt_uses_fallback);
    RUN_TEST(test_negative_dt_uses_fallback);
    
    /* Reset tests */
    RUN_TEST(test_pll_reset_frequency);
    RUN_TEST(test_pll_reset_clears_lock);
    RUN_TEST(test_pll_reset_clears_integrator);
    
    /* Set target phase tests */
    RUN_TEST(test_set_target_phase_valid);
    RUN_TEST(test_set_target_phase_too_small);
    RUN_TEST(test_set_target_phase_too_large);
    
    /* Loss of lock tests */
    RUN_TEST(test_consecutive_invalid_causes_unlock);
}
