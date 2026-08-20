#include "unity.h"
#include "ntc_guard.h"
#include "hal_adc.h"
#include <string.h>

// Mocks
static uint16_t mock_adc_val = 0;
static uint32_t mock_tick_ms = 0;

// Re-use mock from test_adc_guard.c style
hal_status_t mock_read_raw_ntc(hal_adc_channel_t channel, uint16_t *value) {
    (void)channel;
    *value = mock_adc_val;
    return HAL_OK;
}

static const hal_adc_ops_t mock_adc_ops = {
    .read_raw = mock_read_raw_ntc
};

const hal_adc_ops_t *hal_adc = NULL;

uint32_t hal_get_tick_ms(void) {
    return mock_tick_ms;
}

/* ADC codes for the three V_sense points the schematic states for the NTC
 * divider (elec/src/modules.ato:2487-2489), at 12-bit full scale over 3.3 V:
 * adc = round(4095 * V_sense / 3.3). The part is NTCALUG01A104GA,
 * R25 = 100k, B25/85 = 4190 (modules.ato:2459-2469).
 *
 * These are the anchors for the conversion. Do NOT "fix" a failure here by
 * moving the expected temperatures -- they come from the schematic. A failure
 * means NTC_R25/NTC_B in ntc_guard.c no longer match the fitted part. */
#define ADC_AT_25C  3723   /* V_sense 3.000 V */
#define ADC_AT_85C  1994   /* V_sense 1.607 V -- the THM-01 trip point */
#define ADC_AT_120C 1027   /* V_sense 0.828 V */

void setUp(void) {
    hal_adc = &mock_adc_ops;
    mock_adc_val = ADC_AT_25C;
    mock_tick_ms = 1000;
}

void tearDown(void) {}

void test_ntc_short_circuit(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    mock_adc_val = 50; // < NTC_ADC_MIN (100)
    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_SHORT, ntc_guard_read_safe(&ctx, &temp));
}

void test_ntc_open_circuit(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    mock_adc_val = 4000; // > NTC_ADC_MAX (3900)
    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_OPEN, ntc_guard_read_safe(&ctx, &temp));
}

void test_valid_reading(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;

    mock_adc_val = ADC_AT_25C;
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_read_safe(&ctx, &temp));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 25.0f, temp);
}

/* Regression pin for the constants defect: with the previous 10k/B3950
 * constants this ADC code converted to ~26.2 C -- a ~59 C under-read at the
 * one point on the curve where the reading gates a thermal protection trip.
 * OVER_TEMP_THRESHOLD is 80 C, so the old conversion left the software
 * over-temperature trip permanently unarmed. */
void test_conversion_at_85c_trip_point(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;

    mock_adc_val = ADC_AT_85C;
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_read_safe(&ctx, &temp));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 85.0f, temp);

    /* Independent of the tolerance above, and the property that actually
     * matters: the 85 C trip point must read hot enough to arm the 80 C
     * software over-temperature trip. The old constants gave ~26.2 C here. */
    TEST_ASSERT_TRUE(temp > 80.0f);
}

void test_conversion_at_120c(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;

    mock_adc_val = ADC_AT_120C;
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_read_safe(&ctx, &temp));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 120.0f, temp);
}

/* The conversion must be monotonically decreasing in ADC code (higher code =
 * more volts = larger R_ntc = colder), across the three anchors. */
void test_conversion_is_monotonic(void) {
    ntc_guard_t ctx;
    float t25, t85, t120;

    ntc_guard_init(&ctx, 0);
    mock_adc_val = ADC_AT_25C;
    ntc_guard_read_safe(&ctx, &t25);

    ntc_guard_init(&ctx, 0);
    mock_adc_val = ADC_AT_85C;
    ntc_guard_read_safe(&ctx, &t85);

    ntc_guard_init(&ctx, 0);
    mock_adc_val = ADC_AT_120C;
    ntc_guard_read_safe(&ctx, &t120);

    TEST_ASSERT_TRUE(t25 < t85);
    TEST_ASSERT_TRUE(t85 < t120);
}

void test_rate_of_change_violation(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    // First read: 25C
    mock_adc_val = ADC_AT_25C;
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_read_safe(&ctx, &temp));

    // Advance time 1 sec
    mock_tick_ms += 1000;

    // Jump to the 85C trip point -> 60C change in 1 sec > 10C/sec limit.
    // Both endpoints are inside NTC_TEMP_MIN_C..MAX_C, so the range check
    // cannot pre-empt the rate check and mask a regression here.
    mock_adc_val = ADC_AT_85C;

    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_RATE, ntc_guard_read_safe(&ctx, &temp));
}

void test_cross_check_fail(void) {
    // Heatsink cooler than ambient while heating -> Impossible
    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_PLAUSIBILITY, 
        ntc_guard_cross_check(20.0f, 30.0f, true));
}

void test_cross_check_pass(void) {
    // Heatsink hotter than ambient -> OK
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, 
        ntc_guard_cross_check(40.0f, 25.0f, true));
        
    // Heatsink cooler than ambient while OFF -> OK (thermal lag/evap)
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, 
        ntc_guard_cross_check(20.0f, 30.0f, false));
}
