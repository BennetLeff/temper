/**
 * @file test_pll_control.c
 * @brief Unit tests for PLL (Phase-Locked Loop) frequency tracking module
 * 
 * Tests the PLL control logic for ZVS (Zero Voltage Switching) tracking.
 * The PLL adjusts switching frequency to maintain optimal phase relationship
 * between PWM output and current zero-crossing.
 * 
 * Specifications (from design docs):
 * - Frequency range: 44-50 kHz (PLL_MIN_FREQ_HZ to PLL_MAX_FREQ_HZ).
 *   The floor was RAISED from 30 kHz to 42 kHz on 2026-07-29 (docs/evidence/
 *   2026-07-29-pll-floor-above-resonance.md): 30 kHz sat below the tank's
 *   loaded resonance, where a series-resonant bridge hard-switches; then
 *   from 42 kHz to 43 kHz later the same day (docs/evidence/2026-07-29-
 *   pll-floor-cap-tolerance.md) once the derivation was corrected to also
 *   worst-case the tank capacitor's own tolerance, not just the coil's;
 *   then from 43 kHz to 44 kHz later still the same day when PR #410
 *   re-sourced the tank capacitors (WIMA FKP 1 +/-5% -> CDE 942C16P1K-F
 *   +/-10%), raising that same tolerance further. It is derived by
 *   scripts/check_pll_range_consistency.py from elec/src/main.ato's
 *   declared L/C/coupling/tolerances, so tests below assert against the
 *   MACROS rather than against literals -- a literal here would silently
 *   stop testing the real bound the next time the derivation moves it.
 * - Target phase lag: ~1.5µs for ZVS operation
 * - Lock tolerance: ±0.5µs phase error
 * - Default frequency: 47 kHz (CORRECTED 2026-07-28, was 35 kHz -- see
 *   docs/evidence/2026-07-28-pll-defaults-and-range-gate.md)
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
    /* Calibrate the lock-detection resonant-frequency reference to the
     * operating point these tests drive the loop toward.
     *
     * KNOWN GAP (docs/evidence/2026-07-28-pll-defaults-and-range-gate.md):
     * at the shipped, UNCALIBRATED compile-time defaults
     * (PLL_DEFAULT_FREQ_HZ=47000, DEFAULT_RESONANT_FREQ=37580, the
     * corrected loaded resonance), the two sit 9.42kHz apart -- outside
     * FREQ_TOLERANCE_HZ's +-2kHz lock-confirmation window -- so
     * pll_is_locked() can never become true out of the box. There is no
     * non-test caller of pll_set_resonant_frequency() in this firmware
     * (confirmed by grep), so nothing recalibrates this in production
     * either; see test_pll_never_locks_at_uncalibrated_defaults() below,
     * which asserts that gap explicitly rather than hiding it.
     *
     * The tests in this file that exercise phase-lock CONFIRMATION
     * (as opposed to the frequency-deviation criterion, which is a
     * separate, already-flagged, human decision -- see pll_control.c's
     * DEFAULT_RESONANT_FREQ comment) calibrate resonant_freq to the
     * driven operating frequency here so they test the phase-tracking
     * mechanism they are named for, not the compile-time gap above.
     */
    pll_set_resonant_frequency((float)PLL_DEFAULT_FREQ_HZ);
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
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 47000.0f, freq);  /* Default is 47kHz (corrected 2026-07-28) */
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
 *
 * min_freq_hz here was 35000 until 2026-07-29. That is BELOW the tank's
 * loaded resonance (37.58kHz) -- a hard-switching frequency. It only ever
 * exercised config plumbing, but a test fixture is also an example, and
 * this one demonstrated a bridge-destroying value. Changed to 43000 (above
 * the derived floor) the same day, then to 44000 later still the same day
 * when PR #410 re-sourced the tank capacitors (WIMA FKP 1 +/-5% -> CDE
 * 942C16P1K-F +/-10%) and raised the derived floor to 43824Hz, so the
 * example remains one a reader could safely copy.
 */
void test_pll_init_custom_config(void) {
    pll_config_t config = {
        .kp = 5.0f,
        .ki = 100.0f,
        .target_phase_us = 2.0f,
        .min_freq_hz = 44000,
        .max_freq_hz = 46000
    };
    pll_init(&config);

    const pll_context_t *ctx = pll_get_context();
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 5.0f, ctx->kp);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, ctx->ki);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 2.0f, ctx->target_phase_us);
    TEST_ASSERT_EQUAL_UINT32(44000, ctx->min_freq);
    TEST_ASSERT_EQUAL_UINT32(46000, ctx->max_freq);
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

/**
 * Test: at the shipped, UNCALIBRATED compile-time defaults (no
 * pll_set_resonant_frequency() call -- the production reality, since grep
 * finds no non-test caller of that function anywhere in this firmware),
 * the PLL can NEVER confirm lock, even at perfect target-phase tracking.
 *
 * This is a KNOWN, OPEN gap surfaced by the 2026-07-28 PLL_DEFAULT_FREQ_HZ
 * correction (35000 -> 47000, docs/evidence/2026-07-28-pll-defaults-and-
 * range-gate.md) combined with the DEFAULT_RESONANT_FREQ correction
 * (35800 -> 37580, the loaded resonance) in pll_control.c: the corrected
 * default operating point sits 9.42kHz above resonant_freq, outside
 * FREQ_TOLERANCE_HZ's +-2kHz lock-confirmation window. This test asserts
 * the CURRENT (broken) behavior on purpose -- so CI documents it as a
 * tracked, visible limitation rather than a silent surprise -- and is
 * NOT a green-washing of the underlying problem. Fixing it is a
 * control-loop decision for a human (widen FREQ_TOLERANCE_HZ to allow
 * for the intentional above-resonance operating offset, change the lock
 * criterion to rely on phase error alone, or wire a real resonance
 * calibration call), deliberately NOT made here, matching this task's
 * instruction not to silently retune safety-adjacent constants to make
 * a check pass.
 */
void test_pll_never_locks_at_uncalibrated_defaults(void) {
    pll_init(NULL);  /* Defaults only */
    pll_enable();

    /* pll_ctx.resonant_freq is a file-static global that pll_init()/
     * pll_reset() never touch (neither resets it -- itself part of this
     * gap), so an earlier test's reset_pll() calibration call leaks into
     * this one unless explicitly undone. There is no public "restore
     * compile-time default" API (matching the finding that nothing in
     * production ever recalibrates this field either), so this
     * reproduces the true uncalibrated value by name: 37580.0f must
     * match pll_control.c's DEFAULT_RESONANT_FREQ exactly -- if that
     * constant changes, update this literal too. */
    pll_set_resonant_frequency(37580.0f);

    /* Feed exactly target phase for far longer than LOCK_CYCLES_REQUIRED
     * (10) would need if the frequency-deviation criterion were met. */
    for (int i = 0; i < 50; i++) {
        pll_update_loop(1.5f, 0.001f);
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
    TEST_ASSERT_TRUE(freq <= (float)PLL_MAX_FREQ_HZ);  /* see min-limit test's note */
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
    /* Asserted against the MACRO, not a literal 30000.0f. The literal was
     * a silent weakening waiting to happen: when the floor moved 30k ->
     * 42k on 2026-07-29 the old assertion still "passed" while no longer
     * testing the clamp at all. The clamp is a ZVS safety bound -- below
     * PLL_MIN_FREQ_HZ the tank is capacitive and the bridge hard-switches
     * -- so this must track whatever the derived floor currently is. */
    TEST_ASSERT_TRUE(freq >= (float)PLL_MIN_FREQ_HZ);
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
    
    /* Zero dt should use fallback (1ms).  Lock confirmation intentionally
     * requires ten consecutive good cycles, so exercise the full contract. */
    for (int i = 0; i < 10; i++) {
        pll_update_loop(1.5f, 0.0f);
    }
    TEST_ASSERT_TRUE(pll_is_locked());
}

/**
 * Test: Negative dt uses fallback
 */
void test_negative_dt_uses_fallback(void) {
    reset_pll();
    
    /* Negative dt should use fallback; lock confirmation still needs ten
     * consecutive valid cycles. */
    for (int i = 0; i < 10; i++) {
        pll_update_loop(1.5f, -0.001f);
    }
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
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 47000.0f, freq);  /* Back to default (corrected 2026-07-28) */
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
    RUN_TEST(test_pll_never_locks_at_uncalibrated_defaults);

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
