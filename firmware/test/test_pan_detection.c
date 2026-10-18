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
#include "../components/control/pll_control.h"

/* pan_detect.c host hook: a listener in place of the CT_ZC capture. */
extern void pan_detect_host_set_listen(pan_detect_listen_fn listen);

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
 * Test Cases: the detection pulse is a burst start (zapote C39)
 *
 * pan_detect_run_ops() with recording mock ops: it pulses only from idle
 * gates, only after programming a frequency at or above the last known
 * resonance (pll_burst_start_frequency()), and not at all when that rule
 * refuses. detect_pan_presence() reports no pan without the board's ops.
 *============================================================================*/

static struct {
    bool idle;
    bool set_ok;
    bool pulse_ok;
    uint32_t edges;
    int calls;            /* order counter */
    int idle_at, set_at, pulse_at, listen_at;
    float f_set;
    uint32_t width;
} m;

static bool m_idle(void) { m.idle_at = ++m.calls; return m.idle; }
static bool m_set(float f) { m.set_at = ++m.calls; m.f_set = f; return m.set_ok; }
static bool m_pulse(uint32_t w) { m.pulse_at = ++m.calls; m.width = w; return m.pulse_ok; }
static uint32_t m_listen(uint32_t window_ms) { (void)window_ms; m.listen_at = ++m.calls; return m.edges; }

static const pan_detect_pulse_ops_t M_OPS = {
    .gates_idle = m_idle,
    .set_frequency_hz = m_set,
    .pulse = m_pulse,
};

static void m_reset(float f_res_hz) {
    m.idle = true;
    m.set_ok = true;
    m.pulse_ok = true;
    m.edges = 5;
    m.calls = 0;
    m.idle_at = m.set_at = m.pulse_at = m.listen_at = 0;
    m.f_set = 0.0f;
    m.width = 0;
    pll_init(NULL);
    pll_set_resonant_frequency(f_res_hz);
    pan_detect_set_pulse_ops(NULL);
    pan_detect_host_set_listen(NULL);
}

void test_pulse_starts_at_or_above_resonance(void) {
    const float resonances[] = {37580.0f, 45000.0f, 46500.0f, 48000.0f, 49000.0f};
    for (unsigned i = 0; i < sizeof(resonances) / sizeof(resonances[0]); i++) {
        m_reset(resonances[i]);
        TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, pan_detect_run_ops(&M_OPS, m_listen, NULL));
        TEST_ASSERT_TRUE(m.f_set >= resonances[i] * (1.0f + PLL_BURST_START_MARGIN));
        TEST_ASSERT_TRUE(m.f_set >= (float)PLL_DEFAULT_FREQ_HZ);
        TEST_ASSERT_TRUE(m.f_set <= (float)PLL_MAX_FREQ_HZ);
        /* idle checked, then frequency programmed, then pulse, then listen */
        TEST_ASSERT_TRUE(m.idle_at < m.set_at);
        TEST_ASSERT_TRUE(m.set_at < m.pulse_at);
        TEST_ASSERT_TRUE(m.pulse_at < m.listen_at);
    }
}

void test_pulse_default_resonance_starts_at_default(void) {
    m_reset(37580.0f);   /* the declared loaded resonance */
    (void)pan_detect_run_ops(&M_OPS, m_listen, NULL);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, (float)PLL_DEFAULT_FREQ_HZ, m.f_set);
    TEST_ASSERT_EQUAL_UINT32(20u, m.width);
}

void test_pulse_refused_when_no_inductive_start_in_range(void) {
    /* 1.02 x 49.5 kHz = 50.49 kHz > PLL_MAX_FREQ_HZ: nowhere to start. */
    m_reset(49500.0f);
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, pan_detect_run_ops(&M_OPS, m_listen, NULL));
    TEST_ASSERT_EQUAL_INT(0, m.set_at);
    TEST_ASSERT_EQUAL_INT(0, m.pulse_at);
    m_reset(37580.0f);
}

void test_pulse_refused_when_gates_not_idle(void) {
    m_reset(37580.0f);
    m.idle = false;
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, pan_detect_run_ops(&M_OPS, m_listen, NULL));
    TEST_ASSERT_EQUAL_INT(0, m.set_at);
    TEST_ASSERT_EQUAL_INT(0, m.pulse_at);
}

void test_pulse_refused_when_frequency_not_programmed(void) {
    m_reset(37580.0f);
    m.set_ok = false;
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, pan_detect_run_ops(&M_OPS, m_listen, NULL));
    TEST_ASSERT_EQUAL_INT(0, m.pulse_at);
}

void test_pulse_missing_ops_is_error(void) {
    m_reset(37580.0f);
    pan_detect_pulse_ops_t partial = M_OPS;
    partial.gates_idle = NULL;
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, pan_detect_run_ops(NULL, m_listen, NULL));
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, pan_detect_run_ops(&partial, m_listen, NULL));
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, pan_detect_run_ops(&M_OPS, NULL, NULL));
    TEST_ASSERT_EQUAL_INT(0, m.pulse_at);
}

void test_pulse_classifies_ring_down(void) {
    m_reset(37580.0f);
    m.edges = 20;
    TEST_ASSERT_EQUAL(PAN_DETECT_NONE, pan_detect_run_ops(&M_OPS, m_listen, NULL));
    m.edges = 0;
    TEST_ASSERT_EQUAL(PAN_DETECT_ERROR, pan_detect_run_ops(&M_OPS, m_listen, NULL));
    m.edges = 4;
    TEST_ASSERT_EQUAL(PAN_DETECT_FERROUS, pan_detect_run_ops(&M_OPS, m_listen, NULL));
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 250.0f, get_pan_impedance());
}

void test_detect_pan_presence_fail_safe(void) {
    m_reset(37580.0f);
    /* The target today: CT_ZC capture but no native-21 pulse ops. */
    pan_detect_host_set_listen(m_listen);
    TEST_ASSERT_EQUAL(PAN_ABSENT, detect_pan_presence());
    TEST_ASSERT_EQUAL_INT(0, m.calls);
    /* Pulse ops but no capture. */
    pan_detect_host_set_listen(NULL);
    pan_detect_set_pulse_ops(&M_OPS);
    TEST_ASSERT_EQUAL(PAN_ABSENT, detect_pan_presence());
    TEST_ASSERT_EQUAL_INT(0, m.calls);
    /* Both: a ferrous ring-down is a pan; anything else is not. */
    pan_detect_host_set_listen(m_listen);
    TEST_ASSERT_EQUAL(PAN_PRESENT, detect_pan_presence());
    m.edges = 20;
    TEST_ASSERT_EQUAL(PAN_ABSENT, detect_pan_presence());
    m.edges = 5;
    m.idle = false;
    TEST_ASSERT_EQUAL(PAN_ABSENT, detect_pan_presence());
    pan_detect_set_pulse_ops(NULL);
    pan_detect_host_set_listen(NULL);
}

void test_pan_detect_init_without_capture_fails(void) {
    TEST_ASSERT_NOT_EQUAL(ESP_OK, pan_detect_init(NULL, NULL));
}

/*============================================================================
 * Test Runner
 *============================================================================*/

void run_pan_detection_tests(void) {
    RUN_TEST(test_pulse_starts_at_or_above_resonance);
    RUN_TEST(test_pulse_default_resonance_starts_at_default);
    RUN_TEST(test_pulse_refused_when_no_inductive_start_in_range);
    RUN_TEST(test_pulse_refused_when_gates_not_idle);
    RUN_TEST(test_pulse_refused_when_frequency_not_programmed);
    RUN_TEST(test_pulse_missing_ops_is_error);
    RUN_TEST(test_pulse_classifies_ring_down);
    RUN_TEST(test_detect_pan_presence_fail_safe);
    RUN_TEST(test_pan_detect_init_without_capture_fails);
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
