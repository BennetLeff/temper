/**
 * @file test_wdi_supervisor.c
 * @brief TPS3823 WDI heartbeat gated on control-loop progress (zapote C42)
 *
 * The supervisor is the only WDI writer. These tests drive wdi_sup_step() the
 * way the supervisor task does (one call per 100 ms period) and check:
 * - a live loop with fresh RTD conversions gets one WDI edge per period, so
 *   the heartbeat is <= 400 ms;
 * - a stalled loop stops the heartbeat, for good, even if the loop resumes;
 * - a live periodic caller (the "timer") with a dead loop never toggles;
 * - a stopped RTD converter, a slow loop and a late supervisor stop it too;
 * - before the first healthy step (power-up) nothing toggles.
 */

#include <stdint.h>
#include <stdbool.h>

#include "unity/unity.h"
#include "../components/safety/wdi_supervisor.h"

#define STEP_MS WDI_SUP_PERIOD_MS

typedef struct {
    wdi_sup_t sup;
    uint32_t now_ms;
    uint32_t loop_seq;
    uint32_t rtd_seq;
    bool rtd_valid;
    uint32_t edges;
    uint32_t last_edge_ms;
    uint32_t max_edge_gap_ms;
    bool level;
} rig_t;

static void rig_init(rig_t *r)
{
    const wdi_sup_params_t p = WDI_SUP_DEFAULT_PARAMS();
    TEST_ASSERT_TRUE(wdi_sup_init(&r->sup, &p));
    r->now_ms = 1000u;
    r->loop_seq = 0u;
    r->rtd_seq = 0u;
    r->rtd_valid = false;
    r->edges = 0u;
    r->last_edge_ms = 0u;
    r->max_edge_gap_ms = 0u;
    r->level = false;
}

/* One supervisor period. loop_ticks control iterations happened in it;
 * rtd_convs conversions completed. Returns true if WDI got an edge. */
static bool rig_period(rig_t *r, uint32_t loop_ticks, uint32_t rtd_convs)
{
    r->now_ms += STEP_MS;
    r->loop_seq += loop_ticks;
    if (rtd_convs > 0u) {
        r->rtd_valid = true;
        r->rtd_seq += rtd_convs;
    }
    bool level = false;
    const bool edge = wdi_sup_step(&r->sup, r->now_ms, r->loop_seq, r->rtd_valid, r->rtd_seq,
                                   &level);
    if (edge) {
        TEST_ASSERT_TRUE(level != r->level);   /* every write is an edge */
        r->level = level;
        if (r->edges > 0u && r->now_ms - r->last_edge_ms > r->max_edge_gap_ms) {
            r->max_edge_gap_ms = r->now_ms - r->last_edge_ms;
        }
        r->last_edge_ms = r->now_ms;
        r->edges++;
    }
    return edge;
}

/* Healthy: 10 loop iterations and 5 conversions (20 ms) per 100 ms. */
static void rig_healthy(rig_t *r, int periods)
{
    for (int i = 0; i < periods; i++) {
        (void)rig_period(r, 10u, 5u);
    }
}

void test_wdi_defaults_meet_c42(void)
{
    const wdi_sup_params_t p = WDI_SUP_DEFAULT_PARAMS();
    TEST_ASSERT_TRUE(p.heartbeat_ms <= 400u);
    TEST_ASSERT_TRUE(WDI_SUP_PERIOD_MS <= p.heartbeat_ms);
    /* TPS3823 minimum timeout 0.9 s: worst case the heartbeat stops one
     * max_rtd_age after the last conversion plus one step. */
    TEST_ASSERT_TRUE(p.max_rtd_age_ms + WDI_SUP_PERIOD_MS < 900u);
}

void test_wdi_healthy_loop_toggles_every_period(void)
{
    rig_t r;
    rig_init(&r);
    rig_healthy(&r, 50);   /* 5 s */
    /* The first step only sets baselines. */
    TEST_ASSERT_EQUAL_UINT32(49u, r.edges);
    TEST_ASSERT_TRUE(r.max_edge_gap_ms <= WDI_HEARTBEAT_MAX_MS);
    TEST_ASSERT_EQUAL_UINT32(STEP_MS, r.max_edge_gap_ms);
    TEST_ASSERT_EQUAL(WDI_SUP_RUNNING, wdi_sup_state(&r.sup));
}

void test_wdi_no_heartbeat_before_first_rtd_conversion(void)
{
    rig_t r;
    rig_init(&r);
    for (int i = 0; i < 20; i++) {
        TEST_ASSERT_FALSE(rig_period(&r, 10u, 0u));   /* MAX31865 fault cycle */
    }
    TEST_ASSERT_EQUAL(WDI_SUP_ARMING, wdi_sup_state(&r.sup));
    /* The first conversion arms it. */
    TEST_ASSERT_TRUE(rig_period(&r, 10u, 1u));
    TEST_ASSERT_EQUAL(WDI_SUP_RUNNING, wdi_sup_state(&r.sup));
}

void test_wdi_stalled_loop_stops_heartbeat_for_good(void)
{
    rig_t r;
    rig_init(&r);
    rig_healthy(&r, 10);
    const uint32_t before = r.edges;
    /* The control loop hangs; the RTD converter (its own hardware) keeps
     * converting, which the supervisor sees only through the loop, so give
     * it fresh conversions anyway to isolate the loop check. */
    TEST_ASSERT_FALSE(rig_period(&r, 0u, 5u));
    TEST_ASSERT_EQUAL(WDI_SUP_STOPPED, wdi_sup_state(&r.sup));
    TEST_ASSERT_EQUAL(WDI_STOP_LOOP_STALLED, wdi_sup_stop_reason(&r.sup));
    /* The loop recovers before the TPS3823 times out: still no heartbeat. */
    rig_healthy(&r, 30);
    TEST_ASSERT_EQUAL_UINT32(before, r.edges);
    TEST_ASSERT_EQUAL(WDI_SUP_STOPPED, wdi_sup_state(&r.sup));
}

void test_wdi_live_timer_dead_loop_never_toggles(void)
{
    /* The supervisor keeps being called on time (a live timer or task) but
     * the control loop never advances, from power-up on. */
    rig_t r;
    rig_init(&r);
    for (int i = 0; i < 100; i++) {
        TEST_ASSERT_FALSE(rig_period(&r, 0u, 5u));
    }
    TEST_ASSERT_EQUAL_UINT32(0u, r.edges);

    /* The same after a healthy start: once dead, nothing more. */
    rig_init(&r);
    rig_healthy(&r, 5);
    const uint32_t before = r.edges;
    for (int i = 0; i < 100; i++) {
        TEST_ASSERT_FALSE(rig_period(&r, 0u, 5u));
    }
    TEST_ASSERT_EQUAL_UINT32(before, r.edges);
}

void test_wdi_slow_loop_stops_heartbeat(void)
{
    rig_t r;
    rig_init(&r);
    rig_healthy(&r, 5);
    TEST_ASSERT_FALSE(rig_period(&r, 4u, 5u));   /* 4 of the expected 10 */
    TEST_ASSERT_EQUAL(WDI_STOP_LOOP_STALLED, wdi_sup_stop_reason(&r.sup));
}

void test_wdi_minimum_advance_keeps_heartbeat(void)
{
    rig_t r;
    rig_init(&r);
    rig_healthy(&r, 2);
    TEST_ASSERT_TRUE(rig_period(&r, 5u, 5u));    /* exactly min_loop_advance */
    TEST_ASSERT_EQUAL(WDI_SUP_RUNNING, wdi_sup_state(&r.sup));
}

void test_wdi_stale_rtd_stops_heartbeat(void)
{
    rig_t r;
    rig_init(&r);
    rig_healthy(&r, 5);
    /* No new conversion for 300 ms: still within max_rtd_age_ms. */
    TEST_ASSERT_TRUE(rig_period(&r, 10u, 0u));
    TEST_ASSERT_TRUE(rig_period(&r, 10u, 0u));
    TEST_ASSERT_TRUE(rig_period(&r, 10u, 0u));
    /* 400 ms: stale. */
    TEST_ASSERT_FALSE(rig_period(&r, 10u, 0u));
    TEST_ASSERT_EQUAL(WDI_STOP_RTD_STALE, wdi_sup_stop_reason(&r.sup));
    rig_healthy(&r, 10);
    TEST_ASSERT_EQUAL(WDI_SUP_STOPPED, wdi_sup_state(&r.sup));
}

void test_wdi_rtd_invalid_counts_as_stale(void)
{
    rig_t r;
    rig_init(&r);
    rig_healthy(&r, 5);
    r.rtd_valid = false;   /* the service lost its sample (stopped) */
    for (int i = 0; i < 3; i++) {
        (void)rig_period(&r, 10u, 0u);
    }
    TEST_ASSERT_FALSE(rig_period(&r, 10u, 0u));
    TEST_ASSERT_EQUAL(WDI_SUP_STOPPED, wdi_sup_state(&r.sup));
}

void test_wdi_late_supervisor_stops_heartbeat(void)
{
    rig_t r;
    rig_init(&r);
    rig_healthy(&r, 5);
    r.now_ms += WDI_HEARTBEAT_MAX_MS;   /* this step comes 500 ms after the last */
    TEST_ASSERT_FALSE(rig_period(&r, 50u, 25u));
    TEST_ASSERT_EQUAL(WDI_STOP_SUPERVISOR_LATE, wdi_sup_stop_reason(&r.sup));
}

void test_wdi_sequence_wraparound(void)
{
    rig_t r;
    rig_init(&r);
    r.loop_seq = UINT32_MAX - 15u;
    r.rtd_seq = UINT32_MAX - 7u;
    rig_healthy(&r, 10);
    TEST_ASSERT_EQUAL_UINT32(9u, r.edges);
    TEST_ASSERT_EQUAL(WDI_SUP_RUNNING, wdi_sup_state(&r.sup));
}

void test_wdi_rejects_heartbeat_over_400ms(void)
{
    wdi_sup_t s;
    wdi_sup_params_t p = WDI_SUP_DEFAULT_PARAMS();
    p.heartbeat_ms = 401u;
    TEST_ASSERT_FALSE(wdi_sup_init(&s, &p));
    bool level = false;
    for (uint32_t i = 0; i < 20u; i++) {
        TEST_ASSERT_FALSE(wdi_sup_step(&s, 100u * i, 10u * i, true, i, &level));
    }
    p = (wdi_sup_params_t)WDI_SUP_DEFAULT_PARAMS();
    p.heartbeat_ms = 0u;
    TEST_ASSERT_FALSE(wdi_sup_init(&s, &p));
    TEST_ASSERT_FALSE(wdi_sup_init(&s, NULL));
}

void test_wdi_progress_handoff(void)
{
    uint32_t seq0, seq1, rtd;
    bool valid;
    wdi_progress_read(&seq0, &valid, &rtd);
    wdi_progress_publish(true, 1234u);
    wdi_progress_read(&seq1, &valid, &rtd);
    TEST_ASSERT_EQUAL_UINT32(seq0 + 1u, seq1);
    TEST_ASSERT_TRUE(valid);
    TEST_ASSERT_EQUAL_UINT32(1234u, rtd);
    wdi_progress_publish(false, 0u);
    wdi_progress_read(&seq1, &valid, &rtd);
    TEST_ASSERT_EQUAL_UINT32(seq0 + 2u, seq1);
    TEST_ASSERT_FALSE(valid);
}

void run_wdi_supervisor_tests(void)
{
    RUN_TEST(test_wdi_defaults_meet_c42);
    RUN_TEST(test_wdi_healthy_loop_toggles_every_period);
    RUN_TEST(test_wdi_no_heartbeat_before_first_rtd_conversion);
    RUN_TEST(test_wdi_stalled_loop_stops_heartbeat_for_good);
    RUN_TEST(test_wdi_live_timer_dead_loop_never_toggles);
    RUN_TEST(test_wdi_slow_loop_stops_heartbeat);
    RUN_TEST(test_wdi_minimum_advance_keeps_heartbeat);
    RUN_TEST(test_wdi_stale_rtd_stops_heartbeat);
    RUN_TEST(test_wdi_rtd_invalid_counts_as_stale);
    RUN_TEST(test_wdi_late_supervisor_stops_heartbeat);
    RUN_TEST(test_wdi_sequence_wraparound);
    RUN_TEST(test_wdi_rejects_heartbeat_over_400ms);
    RUN_TEST(test_wdi_progress_handoff);
}

void wdi_supervisor_test_setup(void)
{
}
