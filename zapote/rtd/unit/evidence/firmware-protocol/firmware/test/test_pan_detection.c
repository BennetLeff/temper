/**
 * @file test_pan_detection.c
 * @brief Unit tests for pan detection module
 * 
 * Tests the pan detection logic, specifically the analyze_edges() function
 * which determines pan presence based on resonant tank decay characteristics.
 * 
 * Pan detection thresholds (from RESONANT_TANK_DESIGN.md):
 * - Valid ferrous pan: Few decay cycles (heavy magnetic damping)
 * - No pan: Many decay cycles (high Q-factor, free ringing)
 * - Non-ferrous/fault: Very few or zero cycles (over-damped)
 */

#include "unity/unity.h"
#include "test_common.h"
#include "../components/control/pan_detect.h"

/* Test thresholds from implementation */
#define DECAY_THRESHOLD_PAN   8   /* Below this = pan present */
#define DECAY_THRESHOLD_OPEN  15  /* Above this = no pan */

/*============================================================================
 * Test Cases: Edge Analysis Logic
 *============================================================================*/

/**
 * Test: Zero edges indicates sensor fault
 * When the ZCD sensor returns no edges, something is wrong
 */
void test_analyze_edges_zero_is_error(void) {
    pan_result_t result = analyze_edges(0);
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, result);
}

/**
 * Test: Very few edges indicates non-ferrous material
 * 1-2 edges means heavy damping (aluminum, copper, or short circuit)
 */
void test_analyze_edges_one_edge_is_non_ferrous(void) {
    pan_result_t result = analyze_edges(1);
    TEST_ASSERT_EQUAL(PAN_DETECT_NON_FERROUS, result);
}

void test_analyze_edges_two_edges_is_non_ferrous(void) {
    pan_result_t result = analyze_edges(2);
    TEST_ASSERT_EQUAL(PAN_DETECT_NON_FERROUS, result);
}

/**
 * Test: 3-7 edges indicates ferrous pan (good for induction)
 * Moderate damping from ferrous material coupling
 */
void test_analyze_edges_three_is_ferrous(void) {
    pan_result_t result = analyze_edges(3);
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, result);
}

void test_analyze_edges_five_is_ferrous(void) {
    pan_result_t result = analyze_edges(5);
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, result);
}

void test_analyze_edges_seven_is_ferrous(void) {
    pan_result_t result = analyze_edges(7);
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, result);
}

/**
 * Test: At threshold boundary (8 edges)
 * At exactly threshold_pan, should still be no pan (>= threshold = no pan)
 */
void test_analyze_edges_at_threshold_is_no_pan(void) {
    pan_result_t result = analyze_edges(DECAY_THRESHOLD_PAN);
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, result);
}

/**
 * Test: High edge count indicates no pan
 * Free ringing tank circuit with high Q-factor
 */
void test_analyze_edges_ten_is_no_pan(void) {
    pan_result_t result = analyze_edges(10);
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, result);
}

void test_analyze_edges_twenty_is_no_pan(void) {
    pan_result_t result = analyze_edges(20);
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, result);
}

void test_analyze_edges_high_count_is_no_pan(void) {
    pan_result_t result = analyze_edges(100);
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, result);
}

/*============================================================================
 * Test Cases: Boundary Conditions
 *============================================================================*/

/**
 * Test: Boundary at non-ferrous/ferrous transition (2->3)
 */
void test_boundary_non_ferrous_to_ferrous(void) {
    TEST_ASSERT_EQUAL(PAN_DETECT_NON_FERROUS, analyze_edges(2));
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, analyze_edges(3));
}

/**
 * Test: Boundary at ferrous/no-pan transition (7->8)
 */
void test_boundary_ferrous_to_no_pan(void) {
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, analyze_edges(7));
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, analyze_edges(8));
}

/*============================================================================
 * Test Cases: Result Code Verification
 *============================================================================*/

/**
 * Test: All result codes are distinct
 */
void test_result_codes_are_distinct(void) {
    TEST_ASSERT_NOT_EQUAL(PAN_DETECT_NONE, PAN_DETECT_FERROUS);
    TEST_ASSERT_NOT_EQUAL(PAN_DETECT_NONE, PAN_DETECT_NON_FERROUS);
    TEST_ASSERT_NOT_EQUAL(PAN_DETECT_NONE, PAN_DETECT_ERROR);
    TEST_ASSERT_NOT_EQUAL(PAN_DETECT_FERROUS, PAN_DETECT_NON_FERROUS);
    TEST_ASSERT_NOT_EQUAL(PAN_DETECT_FERROUS, PAN_DETECT_ERROR);
    TEST_ASSERT_NOT_EQUAL(PAN_DETECT_NON_FERROUS, PAN_DETECT_ERROR);
}

/*============================================================================
 * Test Cases: Typical Operating Scenarios
 *============================================================================*/

/**
 * Test: Cast iron pan (very high damping)
 * Cast iron pans typically cause 3-5 cycles before decay
 */
void test_typical_cast_iron_pan(void) {
    pan_result_t result = analyze_edges(4);
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, result);
}

/**
 * Test: Stainless steel pan (moderate damping)
 * Stainless steel with magnetic base causes 5-7 cycles
 */
void test_typical_stainless_steel_pan(void) {
    pan_result_t result = analyze_edges(6);
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, result);
}

/**
 * Test: Empty coil (no load)
 * No pan causes many oscillation cycles
 */
void test_typical_empty_coil(void) {
    pan_result_t result = analyze_edges(25);
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, result);
}

/**
 * Test: Aluminum pot (non-ferrous, rejected)
 * Aluminum causes extreme damping but wrong frequency response
 */
void test_typical_aluminum_pot(void) {
    pan_result_t result = analyze_edges(1);
    TEST_ASSERT_EQUAL(PAN_DETECT_NON_FERROUS, result);
}

/**
 * Test: Small metal object (key, spoon)
 * Small objects may cause intermediate damping - treated as no suitable pan
 */
void test_small_metal_object(void) {
    /* Small objects typically cause 10-12 cycles */
    pan_result_t result = analyze_edges(11);
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, result);
}

/**
 * Test: Low-power validation (50W operation)
 * Ensures thresholds are appropriate for low-energy detection pulses.
 */
void test_low_power_validation_ferrous(void) {
    /* At low power, we still expect the same decay physics */
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, analyze_edges(5));
}

void test_low_power_validation_empty(void) {
    /* Open tank should still ring freely regardless of power level */
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, analyze_edges(20));
}

/*============================================================================
 * Test Runner
 *============================================================================*/

void run_pan_detection_tests(void) {
    RUN_TEST(test_analyze_edges_zero_is_error);
    RUN_TEST(test_analyze_edges_one_edge_is_non_ferrous);
    RUN_TEST(test_analyze_edges_two_edges_is_non_ferrous);
    RUN_TEST(test_analyze_edges_three_is_ferrous);
    RUN_TEST(test_analyze_edges_five_is_ferrous);
    RUN_TEST(test_analyze_edges_seven_is_ferrous);
    RUN_TEST(test_analyze_edges_at_threshold_is_no_pan);
    RUN_TEST(test_analyze_edges_ten_is_no_pan);
    RUN_TEST(test_analyze_edges_twenty_is_no_pan);
    RUN_TEST(test_analyze_edges_high_count_is_no_pan);
    RUN_TEST(test_boundary_non_ferrous_to_ferrous);
    RUN_TEST(test_boundary_ferrous_to_no_pan);
    RUN_TEST(test_result_codes_are_distinct);
    RUN_TEST(test_typical_cast_iron_pan);
    RUN_TEST(test_typical_stainless_steel_pan);
    RUN_TEST(test_typical_empty_coil);
    RUN_TEST(test_typical_aluminum_pot);
    RUN_TEST(test_small_metal_object);
    RUN_TEST(test_low_power_validation_ferrous);
    RUN_TEST(test_low_power_validation_empty);
}
