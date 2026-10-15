/**
 * @file test_c1_rim_ntc.c
 * @brief sensor-r3 C1 rim NTC driver (components/sensors/rim_ntc.c): table
 *        conversion, the ADC chain with the CR-7 attenuation rule, saturation,
 *        short / open / over-range / ADC faults, the filter, fault routing,
 *        and the board binding over the hal_adc mock.
 *
 * Expected temperatures come from the Semitec GT-2 datasheet R-T table
 * (104GT-2 column), copied here independently of rim_ntc_table.h.
 * The pan_control integration (cross-check, fault routing through the state
 * machine) is in test_c1_runtime.c.
 */

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "unity/unity.h"

#include "../components/hal/include/hal.h"
#include "../components/sensors/include/rim_ntc.h"

extern void mock_adc_reset(void);
extern void mock_adc_set_value(hal_adc_channel_t channel, uint16_t raw, float voltage_mv);
extern hal_adc_atten_t mock_adc_get_atten(hal_adc_channel_t channel);
extern bool mock_adc_is_calibrated(hal_adc_channel_t channel);

/* Datasheet points (degC, ohm): Semitec GT-2 R-T table, 104GT-2. */
static const float k_pts_c[] = {25.0f, 100.0f, 150.0f, 200.0f, 250.0f};
static const float k_pts_ohm[] = {100000.0f, 5556.0f, 1360.0f, 439.3f, 174.0f};
#define N_PTS (sizeof(k_pts_c) / sizeof(k_pts_c[0]))

/* ---- mock HAL ------------------------------------------------------------ */

typedef struct {
    double node_mv;          /* true node voltage */
    bool fail;
    bool rail_ok;
    float rail_mv;
    rim_atten_t last_atten;
    unsigned outlier_every;  /* every Nth read is 400 mV high (0: never) */
    unsigned reads;
    unsigned reads_by_atten[4];
} mock_rim_t;

static mock_rim_t s_m;

static float clip_mv(rim_atten_t a)
{
    return a == RIM_ATTEN_0 ? 950.0f : (a == RIM_ATTEN_2 ? 1700.0f : 3100.0f);
}

static bool m_read(void *ctx, rim_atten_t a, float *mv)
{
    mock_rim_t *m = (mock_rim_t *)ctx;
    m->reads++;
    m->reads_by_atten[a]++;
    m->last_atten = a;
    if (m->fail) {
        return false;
    }
    float v = (float)m->node_mv;
    if (m->outlier_every != 0u && (m->reads % m->outlier_every) == 0u) {
        v += 400.0f;
    }
    /* the ADC clips above its range; the IDF calibration returns whole mV */
    *mv = roundf(v < clip_mv(a) ? v : clip_mv(a));
    return true;
}

static bool m_rail(void *ctx, float *mv)
{
    mock_rim_t *m = (mock_rim_t *)ctx;
    if (!m->rail_ok) {
        return false;
    }
    *mv = m->rail_mv;
    return true;
}

static const rim_ntc_hal_t s_hal = {.read_node_mv = m_read, .read_v3v3_mv = m_rail, .ctx = &s_m};

static double node_for_ohm(double r, double vdd_mv)
{
    return vdd_mv * r / (r + 1000.0);
}

static rim_ntc_t s_r;

static void fresh(void)
{
    memset(&s_m, 0, sizeof(s_m));
    s_m.rail_ok = true;
    s_m.rail_mv = 3300.0f;
    rim_ntc_params_t p;
    rim_ntc_default_params(&p);
    TEST_ASSERT_TRUE(rim_ntc_init(&s_r, &p));
}

static rim_ntc_reading_t steps(unsigned n, float t_pt)
{
    rim_ntc_reading_t rd;
    memset(&rd, 0, sizeof(rd));
    for (unsigned i = 0; i < n; i++) {
        rim_ntc_step(&s_r, &s_hal, t_pt, &rd);
    }
    return rd;
}

void setUp(void) { fresh(); }
void tearDown(void) {}

/* ---- conversion ---------------------------------------------------------- */

static void test_table_conversion_matches_the_datasheet_points(void)
{
    for (unsigned i = 0; i < N_PTS; i++) {
        const float t = rim_ntc_r_to_c(k_pts_ohm[i]);
        const float r = rim_ntc_c_to_r(k_pts_c[i]);
        printf("  R->T %6.1f degC: %+.5f K;  T->R rel %+.2e\n", (double)k_pts_c[i], (double)(t - k_pts_c[i]),
               (double)((r - k_pts_ohm[i]) / k_pts_ohm[i]));
        TEST_ASSERT_FLOAT_WITHIN(0.005f, k_pts_c[i], t);
        TEST_ASSERT_FLOAT_WITHIN(1e-4f * k_pts_ohm[i], k_pts_ohm[i], r);
    }
    /* outside the table (-50..300 degC) */
    TEST_ASSERT_TRUE(isnan(rim_ntc_r_to_c(70.0f)));
    TEST_ASSERT_TRUE(isnan(rim_ntc_r_to_c(9.0e6f)));
    TEST_ASSERT_TRUE(isnan(rim_ntc_c_to_r(305.0f)));
}

/* Node voltage from the datasheet resistance, rounded to whole mV, through the
 * whole driver (attenuation choice, trimmed mean, ratio, table, filter). */
static void test_chain_accuracy_100_to_250C_and_the_cr7_attenuation(void)
{
    const rim_atten_t expect[] = {RIM_ATTEN_3, RIM_ATTEN_3, RIM_ATTEN_3, RIM_ATTEN_2, RIM_ATTEN_0};
    for (unsigned i = 1; i < N_PTS; i++) {
        for (int rail = 0; rail < 2; rail++) {
            fresh();
            const float vdd = rail ? 3242.0f : 3300.0f;   /* nominal, contract minimum */
            s_m.rail_mv = vdd;
            s_m.node_mv = node_for_ohm(k_pts_ohm[i], vdd);
            const rim_ntc_reading_t rd = steps(80u, NAN);
            printf("  chain %5.1f degC v3v3 %4.0f mV: node %7.2f mV atten %d  err %+.4f K\n", (double)k_pts_c[i],
                   (double)vdd, s_m.node_mv, (int)rd.atten, (double)(rd.t_c - k_pts_c[i]));
            TEST_ASSERT_EQUAL_INT(RIM_NTC_VALID, rd.state);
            TEST_ASSERT_FALSE(rd.rail_nominal);
            TEST_ASSERT_EQUAL_INT(expect[i], rd.atten);
            TEST_ASSERT_FLOAT_WITHIN(0.1f, k_pts_c[i], rd.t_c);
        }
    }
}

static void test_25C_is_saturated_with_an_upper_bound(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[0], 3300.0);   /* 3267 mV */
    const rim_ntc_reading_t rd = steps(3u, 25.0f);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_SATURATED, rd.state);
    TEST_ASSERT_EQUAL_INT(RIM_ATTEN_3, rd.atten);
    /* rim-ntc.json saturation_C_by_v3v3: 91.76 degC at 3.300 V */
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 91.76f, rd.t_c);
    TEST_ASSERT_TRUE(isnan(rd.t_raw_c));
}

static void test_no_rail_reading_uses_the_nominal_rail(void)
{
    s_m.rail_ok = false;
    s_m.node_mv = node_for_ohm(k_pts_ohm[3], 3300.0);
    rim_ntc_reading_t rd = steps(60u, NAN);
    TEST_ASSERT_TRUE(rd.rail_nominal);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 200.0f, rd.t_c);
    /* an implausible rail reading is ignored too */
    fresh();
    s_m.rail_mv = 2500.0f;
    s_m.node_mv = node_for_ohm(k_pts_ohm[3], 3300.0);
    rd = steps(60u, NAN);
    TEST_ASSERT_TRUE(rd.rail_nominal);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 200.0f, rd.t_c);
}

/* ---- attenuation --------------------------------------------------------- */

static void test_attenuation_hysteresis_and_clip_reread(void)
{
    s_m.node_mv = 1000.0;
    rim_ntc_reading_t rd = steps(2u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_ATTEN_2, rd.atten);
    s_m.node_mv = 790.0;                 /* below 800 but not below 770 */
    rd = steps(3u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_ATTEN_2, rd.atten);
    s_m.node_mv = 760.0;
    rd = steps(2u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_ATTEN_0, rd.atten);
    s_m.node_mv = 790.0;                 /* stays in ATTEN0 on the way up */
    rd = steps(2u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_ATTEN_0, rd.atten);
    /* A jump past ATTEN0's range is re-read one range up in the same period. */
    s_m.node_mv = 1200.0;
    rd = steps(1u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_ATTEN_2, rd.atten);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 1200.0f, rd.node_mv);
    s_m.node_mv = 2600.0;
    memset(s_m.reads_by_atten, 0, sizeof(s_m.reads_by_atten));
    rd = steps(1u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_ATTEN_3, rd.atten);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 2600.0f, rd.node_mv);
    TEST_ASSERT_EQUAL_UINT(8u, s_m.reads_by_atten[RIM_ATTEN_2]);
    TEST_ASSERT_EQUAL_UINT(8u, s_m.reads_by_atten[RIM_ATTEN_3]);
}

/* ---- faults -------------------------------------------------------------- */

static int s_sink_calls;
static bool s_sink_short;
static bool s_sink_open;
static void sink(bool short_fault, bool open_fault, void *ctx)
{
    (void)ctx;
    s_sink_calls++;
    s_sink_short = short_fault;
    s_sink_open = open_fault;
}

static void reset_sink(void)
{
    s_sink_calls = 0;
    s_sink_short = s_sink_open = false;
}

static void test_short_latches_after_three_periods_and_reports_short(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    rim_ntc_reading_t rd = steps(20u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_VALID, rd.state);
    s_m.node_mv = 100.0;
    rd = steps(2u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_VALID, rd.state);      /* candidate: last reading held */
    TEST_ASSERT_FLOAT_WITHIN(0.2f, 150.0f, rd.t_c);
    rd = steps(1u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_FAULT, rd.state);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_DIAG_SHORT, rd.diag);
    TEST_ASSERT_TRUE(isnan(rd.t_c));
    /* latched: a good node does not clear it */
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    rd = steps(5u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_FAULT, rd.state);
    reset_sink();
    rim_ntc_report(&rd, sink, NULL);
    TEST_ASSERT_EQUAL_INT(1, s_sink_calls);
    TEST_ASSERT_TRUE(s_sink_short);
    TEST_ASSERT_FALSE(s_sink_open);
}

static void test_a_two_period_short_glitch_does_not_latch(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    (void)steps(20u, NAN);
    s_m.node_mv = 100.0;
    (void)steps(2u, NAN);
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    (void)steps(1u, NAN);
    s_m.node_mv = 100.0;
    const rim_ntc_reading_t rd = steps(2u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_VALID, rd.state);
    reset_sink();
    rim_ntc_report(&rd, sink, NULL);
    TEST_ASSERT_EQUAL_INT(0, s_sink_calls);
}

static void test_over_range_latches_as_a_short_class_fault(void)
{
    /* 295 degC: between the 290 degC limit and the 0.25 V short threshold */
    s_m.node_mv = node_for_ohm(rim_ntc_c_to_r(295.0f), 3300.0);
    TEST_ASSERT_TRUE(s_m.node_mv > 250.0);
    const rim_ntc_reading_t rd = steps(3u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_FAULT, rd.state);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_DIAG_OVER_RANGE, rd.diag);
    reset_sink();
    rim_ntc_report(&rd, sink, NULL);
    TEST_ASSERT_TRUE(s_sink_short);
    /* 285 degC is still a valid (hot) rim */
    fresh();
    s_m.node_mv = node_for_ohm(rim_ntc_c_to_r(285.0f), 3300.0);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_VALID, steps(30u, NAN).state);
}

static void test_open_latches_after_600s_saturated_with_a_hot_pt100(void)
{
    s_m.node_mv = 3300.0;                 /* open bead: full scale */
    rim_ntc_reading_t rd = steps(7000u, 140.0f);   /* Pt100 below 150: never */
    TEST_ASSERT_EQUAL_INT(RIM_NTC_SATURATED, rd.state);
    rd = steps(5999u, 160.0f);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_SATURATED, rd.state);
    /* one valid period restarts the count */
    s_m.node_mv = node_for_ohm(k_pts_ohm[1], 3300.0);
    (void)steps(1u, 160.0f);
    s_m.node_mv = 3300.0;
    rd = steps(5999u, 160.0f);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_SATURATED, rd.state);
    rd = steps(1u, 160.0f);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_FAULT, rd.state);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_DIAG_OPEN, rd.diag);
    reset_sink();
    rim_ntc_report(&rd, sink, NULL);
    TEST_ASSERT_TRUE(s_sink_open);
    TEST_ASSERT_FALSE(s_sink_short);
}

static void test_adc_failure_holds_then_latches_open(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[3], 3300.0);
    (void)steps(30u, NAN);
    s_m.fail = true;
    rim_ntc_reading_t rd = steps(9u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_VALID, rd.state);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 200.0f, rd.t_c);
    rd = steps(1u, NAN);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_FAULT, rd.state);
    TEST_ASSERT_EQUAL_INT(RIM_NTC_DIAG_ADC, rd.diag);
    reset_sink();
    rim_ntc_report(&rd, sink, NULL);
    TEST_ASSERT_TRUE(s_sink_open);
}

/* ---- filter --------------------------------------------------------------- */

static void test_filter_time_constant_is_one_second(void)
{
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    (void)steps(50u, NAN);
    s_m.node_mv = node_for_ohm(k_pts_ohm[3], 3300.0);
    rim_ntc_reading_t rd = steps(10u, NAN);              /* 1 s */
    const float frac = (rd.t_c - 150.0f) / 50.0f;
    printf("  filter: %.3f of a 50 K step after 1 s\n", (double)frac);
    TEST_ASSERT_TRUE(frac > 0.55f && frac < 0.70f);       /* 1 - (1/1.1)^10 = 0.614 */
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 200.0f, rd.t_raw_c);
    rd = steps(60u, NAN);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 200.0f, rd.t_c);
}

static void test_trimmed_mean_rejects_one_outlier_sample(void)
{
    /* one sample in each period of 8 reads 400 mV high (about 20 K): it is
     * dropped as the maximum; a plain mean would be 50 mV (2.5 K) off */
    s_m.node_mv = node_for_ohm(k_pts_ohm[2], 3300.0);
    s_m.outlier_every = 8u;
    rim_ntc_params_t p;
    rim_ntc_default_params(&p);
    p.filter_tau_s = 0.0f;
    TEST_ASSERT_TRUE(rim_ntc_init(&s_r, &p));
    const rim_ntc_reading_t rd = steps(3u, NAN);
    TEST_ASSERT_EQUAL_UINT(24u, s_m.reads);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 150.0f, rd.t_c);
}

/* ---- board binding over the hal_adc mock --------------------------------- */

static void test_board_binding_reads_adc1_ch8_and_switches_attenuation(void)
{
    hal_deinit();
    TEST_ASSERT_EQUAL(HAL_OK, hal_init_mock());
    mock_adc_reset();
    const rim_ntc_hal_t *bh = rim_ntc_board_hal();
    TEST_ASSERT_NOT_NULL(bh);
    mock_adc_set_value(8, 0u, 1007.0f);           /* 200 degC node */
    rim_ntc_reading_t rd;
    rim_ntc_step(&s_r, bh, NAN, &rd);
    TEST_ASSERT_EQUAL_INT(HAL_ADC_ATTEN_11dB, mock_adc_get_atten(8));   /* first read: ATTEN3 */
    TEST_ASSERT_TRUE(mock_adc_is_calibrated(8));
    rim_ntc_step(&s_r, bh, NAN, &rd);
    TEST_ASSERT_EQUAL_INT(HAL_ADC_ATTEN_6dB, mock_adc_get_atten(8));    /* CR-7: ATTEN2 below 1.55 V */
    TEST_ASSERT_EQUAL_INT(RIM_NTC_VALID, rd.state);
    TEST_ASSERT_TRUE(rd.rail_nominal);            /* no MCP3202 driver yet */
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 200.0f, rd.t_c);
    mock_adc_set_value(8, 0u, 489.0f);            /* 250 degC node */
    for (int i = 0; i < 80; i++) {
        rim_ntc_step(&s_r, bh, NAN, &rd);
    }
    TEST_ASSERT_EQUAL_INT(HAL_ADC_ATTEN_0dB, mock_adc_get_atten(8));
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 250.0f, rd.t_c);
    (void)hal_deinit();
}

void run_c1_rim_ntc_tests(void)
{
    RUN_TEST(test_table_conversion_matches_the_datasheet_points);
    RUN_TEST(test_chain_accuracy_100_to_250C_and_the_cr7_attenuation);
    RUN_TEST(test_25C_is_saturated_with_an_upper_bound);
    RUN_TEST(test_no_rail_reading_uses_the_nominal_rail);
    RUN_TEST(test_attenuation_hysteresis_and_clip_reread);
    RUN_TEST(test_short_latches_after_three_periods_and_reports_short);
    RUN_TEST(test_a_two_period_short_glitch_does_not_latch);
    RUN_TEST(test_over_range_latches_as_a_short_class_fault);
    RUN_TEST(test_open_latches_after_600s_saturated_with_a_hot_pt100);
    RUN_TEST(test_adc_failure_holds_then_latches_open);
    RUN_TEST(test_filter_time_constant_is_one_second);
    RUN_TEST(test_trimmed_mean_rejects_one_outlier_sample);
    RUN_TEST(test_board_binding_reads_adc1_ch8_and_switches_attenuation);
}
