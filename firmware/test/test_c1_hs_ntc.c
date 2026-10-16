/**
 * @file test_c1_hs_ntc.c
 * @brief Heatsink NTC driver (components/sensors/hs_ntc.c): the Vishay
 *        material D table, the ADC chain with the CR-7 attenuation rule,
 *        ATTEN3 saturation and its upper bound, short / over-range / ADC
 *        faults, the interlock value read_heatsink_temperature() returns, the
 *        poll rate, the CR-8 divider gain, and the board binding over the
 *        hal_adc mock (ADC1_CH5).
 *
 * Expected values come from the Vishay NTCLE100E3 data sheet (doc 29049
 * p. 12, NTCLE100E3104 column), copied here independently of hs_ntc_table.h.
 * The rail-dependent numbers are hs-ntc.json's (hs_ntc.py).
 */

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "unity/unity.h"

#include "../components/temper_hal/include/hal.h"
#include "../components/sensors/include/hs_ntc.h"

extern void mock_adc_reset(void);
extern void mock_adc_set_value(hal_adc_channel_t channel, uint16_t raw, float voltage_mv);
extern hal_adc_atten_t mock_adc_get_atten(hal_adc_channel_t channel);
extern bool mock_adc_is_calibrated(hal_adc_channel_t channel);

/* Data-sheet points (degC, ohm): NTCLE100E3104, material D, 4190 K. */
static const float k_pts_c[] = {25.0f, 40.0f, 80.0f, 95.0f, 125.0f, 140.0f};
static const float k_pts_ohm[] = {100000.0f, 51750.0f, 11260.0f, 6837.0f, 2783.0f, 1854.0f};
#define N_PTS (sizeof(k_pts_c) / sizeof(k_pts_c[0]))

typedef struct {
    double node_mv;
    double gain;            /* pin / node */
    bool fail;
    bool rail_ok;
    float rail_mv;
    unsigned reads;
    unsigned reads_by_atten[4];
} mock_hs_t;

static mock_hs_t s_m;

static float clip_mv(rim_atten_t a)
{
    return a == RIM_ATTEN_0 ? 950.0f : (a == RIM_ATTEN_2 ? 1700.0f : 3100.0f);
}

static bool m_read(void *ctx, rim_atten_t a, float *mv)
{
    mock_hs_t *m = (mock_hs_t *)ctx;
    m->reads++;
    m->reads_by_atten[a]++;
    if (m->fail) {
        return false;
    }
    const float v = (float)(m->node_mv * m->gain);
    *mv = roundf(v < clip_mv(a) ? v : clip_mv(a));
    return true;
}

static bool m_rail(void *ctx, float *mv)
{
    mock_hs_t *m = (mock_hs_t *)ctx;
    if (!m->rail_ok) {
        return false;
    }
    *mv = m->rail_mv;
    return true;
}

static const hs_ntc_hal_t s_hal = {.read_pin_mv = m_read, .read_v3v3_mv = m_rail, .ctx = &s_m};

static double node_for_ohm(double r, double vdd_mv)
{
    return vdd_mv * r / (r + 10000.0);
}

static hs_ntc_t s_h;

static void fresh(void)
{
    memset(&s_m, 0, sizeof(s_m));
    s_m.gain = 1.0;
    s_m.rail_ok = true;
    s_m.rail_mv = 3300.0f;
    hs_ntc_params_t p;
    hs_ntc_default_params(&p);
    TEST_ASSERT_TRUE(hs_ntc_init(&s_h, &p));
}

static hs_ntc_reading_t steps(unsigned n)
{
    hs_ntc_reading_t rd;
    memset(&rd, 0, sizeof(rd));
    for (unsigned i = 0; i < n; i++) {
        hs_ntc_step(&s_h, &s_hal, &rd);
    }
    return rd;
}

void setUp(void) { fresh(); }
void tearDown(void) {}

static void test_table_conversion_matches_the_datasheet_points(void)
{
    for (unsigned i = 0; i < N_PTS; i++) {
        const float t = hs_ntc_r_to_c(k_pts_ohm[i]);
        const float r = hs_ntc_c_to_r(k_pts_c[i]);
        TEST_ASSERT_FLOAT_WITHIN(0.005f, k_pts_c[i], t);
        TEST_ASSERT_FLOAT_WITHIN(1e-4f * k_pts_ohm[i], k_pts_ohm[i], r);
    }
    TEST_ASSERT_TRUE(isnan(hs_ntc_r_to_c(1000.0f)));    /* hotter than 150 degC */
    TEST_ASSERT_TRUE(isnan(hs_ntc_r_to_c(4.0e6f)));     /* colder than -40 degC */
    TEST_ASSERT_TRUE(isnan(hs_ntc_c_to_r(151.0f)));
}

/* The trip and release points through the whole driver at the nominal and
 * the low rail (measured), with the CR-7 attenuation the node calls for. */
static void test_chain_accuracy_at_the_trip_points(void)
{
    const rim_atten_t expect[] = {RIM_ATTEN_3, RIM_ATTEN_3, RIM_ATTEN_3, RIM_ATTEN_2, RIM_ATTEN_0, RIM_ATTEN_0};
    for (unsigned i = 1; i < N_PTS; i++) {
        for (int rail = 0; rail < 2; rail++) {
            fresh();
            const float vdd = rail ? 3242.0f : 3300.0f;
            s_m.rail_mv = vdd;
            s_m.node_mv = node_for_ohm(k_pts_ohm[i], vdd);
            const hs_ntc_reading_t rd = steps(80u);
            printf("  chain %5.1f degC v3v3 %4.0f: node %7.1f mV atten %d err %+.4f K\n", (double)k_pts_c[i],
                   (double)vdd, s_m.node_mv, (int)rd.atten, (double)(rd.t_c - k_pts_c[i]));
            TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);
            TEST_ASSERT_EQUAL_INT(expect[i], rd.atten);
            TEST_ASSERT_FLOAT_WITHIN(0.1f, k_pts_c[i], rd.t_c);
            TEST_ASSERT_FLOAT_WITHIN(0.1f, k_pts_c[i], hs_ntc_interlock_c(&rd));
        }
    }
}

/* Room temperature is above ATTEN3's 2900 mV top: SATURATED, an upper bound. */
static void test_room_temperature_is_saturated_with_an_upper_bound(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[0], 3300.0);   /* 3000 mV */
    hs_ntc_reading_t rd = steps(3u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_SATURATED, rd.state);
    TEST_ASSERT_FALSE(rd.rail_nominal);
    /* hs-ntc.json saturation_C_by_v3v3: 32.17 degC at 3.300 V */
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 32.17f, rd.t_c);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 32.17f, hs_ntc_interlock_c(&rd));
    /* No rail reading: the bound at the rail's contract maximum, 35.72 degC */
    fresh();
    s_m.rail_ok = false;
    s_m.node_mv = node_for_ohm(k_pts_ohm[0], 3300.0);
    rd = steps(3u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_SATURATED, rd.state);
    TEST_ASSERT_TRUE(rd.rail_nominal);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 35.72f, rd.t_c);
    /* 40 degC is in range without a rail reading (3300 mV assumed) */
    fresh();
    s_m.rail_ok = false;
    s_m.node_mv = node_for_ohm(k_pts_ohm[1], 3300.0);
    rd = steps(30u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 40.0f, rd.t_c);
    /* An open sensor (node at the rail) is indistinguishable from cold. */
    fresh();
    s_m.node_mv = 3300.0;
    TEST_ASSERT_EQUAL_INT(HS_NTC_SATURATED, steps(5u).state);
}

static void test_short_latches_after_three_periods_and_reads_infinite(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    hs_ntc_reading_t rd = steps(20u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);
    s_m.node_mv = 100.0;
    rd = steps(2u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);     /* candidate: last reading held */
    TEST_ASSERT_FLOAT_WITHIN(0.2f, 80.0f, hs_ntc_interlock_c(&rd));
    rd = steps(1u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_FAULT, rd.state);
    TEST_ASSERT_EQUAL_INT(HS_NTC_DIAG_SHORT, rd.diag);
    TEST_ASSERT_TRUE(isinf(hs_ntc_interlock_c(&rd)) && hs_ntc_interlock_c(&rd) > 0.0f);
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);  /* latched until init */
    TEST_ASSERT_EQUAL_INT(HS_NTC_FAULT, steps(5u).state);
}

static void test_over_range_above_the_table_latches(void)
{
    s_m.node_mv = node_for_ohm(1300.0, 3300.0);          /* ~155 degC, 380 mV: above 250 mV */
    TEST_ASSERT_TRUE(s_m.node_mv > 250.0);
    const hs_ntc_reading_t rd = steps(3u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_FAULT, rd.state);
    TEST_ASSERT_EQUAL_INT(HS_NTC_DIAG_OVER_RANGE, rd.diag);
    TEST_ASSERT_TRUE(isinf(hs_ntc_interlock_c(&rd)));
    fresh();
    s_m.node_mv = node_for_ohm(k_pts_ohm[5], 3300.0);   /* 140 degC is still a reading */
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, steps(30u).state);
}

static void test_adc_failure_reads_infinite_then_latches(void)
{
    /* No reading yet: +INF, as the former stub. */
    s_m.fail = true;
    hs_ntc_reading_t rd = steps(1u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_NO_DATA, rd.state);
    TEST_ASSERT_TRUE(isinf(hs_ntc_interlock_c(&rd)));
    fresh();
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    (void)steps(30u);
    s_m.fail = true;
    rd = steps(9u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);
    rd = steps(1u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_FAULT, rd.state);
    TEST_ASSERT_EQUAL_INT(HS_NTC_DIAG_ADC, rd.diag);
    TEST_ASSERT_TRUE(isinf(hs_ntc_interlock_c(&rd)));
}

static void test_filter_time_constant_is_one_second(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[1], 3300.0);
    (void)steps(50u);
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    const hs_ntc_reading_t rd = steps(10u);
    const float frac = (rd.t_c - 40.0f) / 40.0f;
    TEST_ASSERT_TRUE(frac > 0.55f && frac < 0.70f);
}

static void test_poll_runs_one_period_per_100ms(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    hs_ntc_reading_t rd;
    hs_ntc_poll(&s_h, &s_hal, 1000u, &rd);
    const unsigned r1 = s_m.reads;
    TEST_ASSERT_TRUE(r1 >= 8u);
    for (uint32_t t = 1010u; t < 1100u; t += 10u) {
        hs_ntc_poll(&s_h, &s_hal, t, &rd);
    }
    TEST_ASSERT_EQUAL_UINT(r1, s_m.reads);
    hs_ntc_poll(&s_h, &s_hal, 1100u, &rd);
    TEST_ASSERT_TRUE(s_m.reads > r1);
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);
}

/* CR-8 (DECISIONS D-HSNTC): a divider after the buffer brings room
 * temperature into range; the driver divides the pin voltage by the gain. */
static void test_divider_gain_brings_room_temperature_into_range(void)
{
    hs_ntc_params_t p;
    hs_ntc_default_params(&p);
    p.adc_gain = 0.85f;
    TEST_ASSERT_TRUE(hs_ntc_init(&s_h, &p));
    s_m.gain = 0.85;
    s_m.node_mv = node_for_ohm(k_pts_ohm[0], 3300.0);
    const hs_ntc_reading_t rd = steps(30u);
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);
    TEST_ASSERT_FLOAT_WITHIN(0.15f, 25.0f, rd.t_c);
    p.adc_gain = 1.2f;
    TEST_ASSERT_FALSE(hs_ntc_init(&s_h, &p));
}

static void test_board_binding_reads_adc1_ch5_only(void)
{
    hal_deinit();
    TEST_ASSERT_EQUAL(HAL_OK, hal_init_mock());
    mock_adc_reset();
    const hs_ntc_hal_t *bh = hs_ntc_board_hal();
    TEST_ASSERT_NOT_NULL(bh);
    mock_adc_set_value(5, 0u, 1340.0f);            /* 95 degC node */
    mock_adc_set_value(8, 0u, 100.0f);             /* the rim channel: must not be read */
    hs_ntc_reading_t rd;
    hs_ntc_step(&s_h, bh, &rd);
    TEST_ASSERT_EQUAL_INT(HAL_ADC_ATTEN_11dB, mock_adc_get_atten(5));
    TEST_ASSERT_TRUE(mock_adc_is_calibrated(5));
    TEST_ASSERT_FALSE(mock_adc_is_calibrated(8));
    hs_ntc_step(&s_h, bh, &rd);
    TEST_ASSERT_EQUAL_INT(HAL_ADC_ATTEN_6dB, mock_adc_get_atten(5));   /* ATTEN2 below 1.55 V */
    TEST_ASSERT_EQUAL_INT(HS_NTC_VALID, rd.state);
    TEST_ASSERT_TRUE(rd.rail_nominal);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 95.0f, rd.t_c);
    (void)hal_deinit();
}

void run_c1_hs_ntc_tests(void)
{
    RUN_TEST(test_table_conversion_matches_the_datasheet_points);
    RUN_TEST(test_chain_accuracy_at_the_trip_points);
    RUN_TEST(test_room_temperature_is_saturated_with_an_upper_bound);
    RUN_TEST(test_short_latches_after_three_periods_and_reads_infinite);
    RUN_TEST(test_over_range_above_the_table_latches);
    RUN_TEST(test_adc_failure_reads_infinite_then_latches);
    RUN_TEST(test_filter_time_constant_is_one_second);
    RUN_TEST(test_poll_runs_one_period_per_100ms);
    RUN_TEST(test_divider_gain_brings_room_temperature_into_range);
    RUN_TEST(test_board_binding_reads_adc1_ch5_only);
}
