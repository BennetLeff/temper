/* C51 food-probe RTD (J9, U50): conversion and unplug classification. Oracle: the controller's own
 * controller_calcs.py rtd_food() code ratios (branch controller-c51), which model the 1 M sense pull-up
 * from BIAS into the top of the Pt1000. Assertions are the oracle (built with -UNDEBUG). */
#include "rtd_food.h"
#include "max31865.h"
#include "rtd_convert.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))

static uint16_t code_of(double ratio) { return (uint16_t)lround(ratio * 32768.0); }

/* rtd_food() rows: temperature, code ratio, loading error if uncorrected (K). */
static const struct { double t, ratio, uncorrected_k; } ROWS[] = {
    {0.0, 0.23356, 1.10022}, {60.0, 0.28784, 1.38041}, {100.0, 0.32349, 1.57027},
    {200.0, 0.41073, 2.05635}, {300.0, 0.49526, 2.56}};

static void test_corrected_reading_matches_the_controller_model(void)
{
    rtd_food_params_t p;
    rtd_food_default_params(&p);
    for (unsigned i = 0; i < sizeof ROWS / sizeof ROWS[0]; i++) {
        /* exact ratio, not the rounded code: the oracle is to 5 digits */
        float t = rtd_food_ohm_to_c(&p, rtd_food_ratio_to_ohm(&p, ROWS[i].ratio));
        float raw = rtd_convert_ohm_to_c((float)(ROWS[i].ratio * p.r_ref_ohm), p.r0_ohm);
        printf("  food %5.1f C: corrected %.3f, uncorrected %.3f (+%.2f K)\n", ROWS[i].t, t, raw, raw - t);
        assert(NEAR(t, ROWS[i].t, 0.02));
        assert(NEAR(raw - t, ROWS[i].uncorrected_k, 0.02)); /* the correction is the controller's loading term */
    }
}

static void test_ice_point_offset_is_subtracted(void)
{
    rtd_food_params_t p;
    rtd_food_default_params(&p);
    p.ice_offset_k = 0.4f;
    float t = rtd_food_ohm_to_c(&p, rtd_food_ratio_to_ohm(&p, ROWS[0].ratio));
    assert(NEAR(t, -0.4, 0.02));
}

static void test_window_and_threshold_words(void)
{
    /* Window (rtd_food_unplug): code ratio 0.20-0.55. Its docstring's "about 380 C" is wrong: 0.55 is
     * 366.5 C corrected (369 C uncorrected). What matters is that it brackets the probe's use, -20..300 C,
     * with room for the open-lead drift to cross it. */
    rtd_food_params_t p;
    rtd_food_default_params(&p);
    float lo = rtd_food_ohm_to_c(&p, rtd_food_ratio_to_ohm(&p, RTD_FOOD_WINDOW_LOW_RATIO));
    float hi = rtd_food_ohm_to_c(&p, rtd_food_ratio_to_ohm(&p, RTD_FOOD_WINDOW_HIGH_RATIO));
    printf("  window %.1f .. %.1f C\n", lo, hi);
    assert(lo < -30.0f && lo > -40.0f && hi > 350.0f && hi < 370.0f);
    /* Threshold registers hold the 15-bit code in bits 15..1 (as the RTD data register). */
    assert(RTD_FOOD_HIGH_THRESHOLD_WORD == (uint16_t)(code_of(0.55) << 1));
    assert(RTD_FOOD_LOW_THRESHOLD_WORD == (uint16_t)(code_of(0.20) << 1));
}

static void test_classification(void)
{
    uint16_t mid = code_of(ROWS[1].ratio);
    assert(rtd_food_classify(mid, 0) == RTD_FOOD_OK);
    /* A full unplug opens FORCE+: the reference current stops and the code carries nothing; D5 says so. */
    assert(rtd_food_classify(mid, MAX31865_FAULT_REFIN_HIGH) == RTD_FOOD_UNPLUGGED);
    assert(rtd_food_classify(0, MAX31865_FAULT_REFIN_HIGH) == RTD_FOOD_UNPLUGGED);
    /* One open sense lead drifts out of the window (72-124 ms). */
    assert(rtd_food_classify(code_of(0.19), 0) == RTD_FOOD_OPEN_LEAD);
    assert(rtd_food_classify(code_of(0.56), 0) == RTD_FOOD_OPEN_LEAD);
    assert(rtd_food_classify(code_of(0.20), 0) == RTD_FOOD_OK);
    assert(rtd_food_classify(code_of(0.55), 0) == RTD_FOOD_OK);
    /* The threshold bits alone are the window, already classified by the code. Any other input fault is
     * the input circuit, not the temperature. */
    assert(rtd_food_classify(mid, MAX31865_FAULT_REFIN_LOW) == RTD_FOOD_INPUT_FAULT);
    assert(rtd_food_classify(mid, MAX31865_FAULT_RTDIN_LOW) == RTD_FOOD_INPUT_FAULT);
    assert(rtd_food_classify(mid, MAX31865_FAULT_HIGH_THRESHOLD) == RTD_FOOD_OK);
    /* Only an OK reading is a temperature. */
    rtd_food_params_t p;
    rtd_food_default_params(&p);
    float t = 0.0f;
    assert(rtd_food_read(&p, mid, 0, &t) == RTD_FOOD_OK && NEAR(t, 60.0, 0.05));
    assert(rtd_food_read(&p, mid, MAX31865_FAULT_REFIN_HIGH, &t) == RTD_FOOD_UNPLUGGED && isnan(t));
}

int main(void)
{
    test_corrected_reading_matches_the_controller_model();
    test_ice_point_offset_is_subtracted();
    test_window_and_threshold_words();
    test_classification();
    printf("rtd_food: all passed\n");
    return 0;
}
