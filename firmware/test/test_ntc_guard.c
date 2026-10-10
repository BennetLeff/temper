#include "unity.h"
#include "ntc_guard.h"
#include "hal_adc.h"
#include <math.h>
#include <string.h>

/* Ratiometric 12-bit counts for the fitted part (100 k NTCALUG01A104GA on 10.0 k): the node is
 * R/(R + 10 k) of v3v3. R from Vishay doc 29049 p. 12 (NTCLE100E3104, the 4190 K +/- 1.5 % curve). */
static uint16_t counts_for_r(float r_ohm) {
    return (uint16_t)lroundf(4095.0f * r_ohm / (r_ohm + 10000.0f));
}
#define RAW_25C  counts_for_r(100000.0f)
#define RAW_85C  counts_for_r(9496.0f)

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

void setUp(void) {
    hal_adc = &mock_adc_ops;
    mock_adc_val = RAW_25C;
    mock_tick_ms = 1000;
}

void tearDown(void) {}

void test_ntc_short_circuit(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    mock_adc_val = 50; // 40 mV: hotter than 200 C on this divider
    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_SHORT, ntc_guard_read_safe(&ctx, &temp));
}

void test_ntc_open_circuit(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    mock_adc_val = 4095; // node at v3v3: open (unplugged)
    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_OPEN, ntc_guard_read_safe(&ctx, &temp));
}

void test_valid_reading(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    mock_adc_val = RAW_25C;
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_read_safe(&ctx, &temp));
    // 100 k at 25 C on the 10 k pull-up (count rounding is ~0.06 K here)
    TEST_ASSERT_FLOAT_WITHIN(0.2f, 25.0f, temp);
    // The legacy 10 k / B3950 assumption read 2048 counts as 25 C; on this part it is ~85 C.
    mock_adc_val = 2048;
    mock_tick_ms += 100000;
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_read_safe(&ctx, &temp));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 83.4f, temp); // 10.0 k: between 80 C (11.26 k) and 85 C (9.496 k)
}

void test_rate_of_change_violation(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    // First read: 25C
    mock_adc_val = RAW_25C;
    ntc_guard_read_safe(&ctx, &temp);
    
    // Advance time 1 sec
    mock_tick_ms += 1000;
    
    // Jump to 85C -> 60C change in 1 sec > 10C/sec limit
    mock_adc_val = RAW_85C;
    
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

/* Conversion at the coordinator's check points, against the Vishay R-T table (doc 29049 p. 12):
 * 25 C 100.0 k, 100 C 5.835 k, 140 C 1.854 k, 150 C 1.434 k. The tolerance covers the 12-bit
 * count rounding (worst near 25 C, where the node sits at 91 % of v3v3). */
void test_conversion_points_fitted_part(void) {
    static const struct { float t_c, r_ohm, tol_k; } pts[] = {
        {25.0f, 100000.0f, 0.15f}, {100.0f, 5835.0f, 0.1f}, {140.0f, 1854.0f, 0.1f}, {150.0f, 1434.0f, 0.1f}};
    ntc_guard_t coil, sink;
    ntc_guard_init_part(&coil, 0, &THERMAL_NTC_COIL);
    ntc_guard_init_part(&sink, 1, &THERMAL_NTC_SINK);
    for (unsigned i = 0; i < sizeof pts / sizeof pts[0]; i++) {
        float t = -999.0f;
        TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_convert(&coil, counts_for_r(pts[i].r_ohm), &t));
        TEST_ASSERT_FLOAT_WITHIN(pts[i].tol_k, pts[i].t_c, t);
        TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_convert(&sink, counts_for_r(pts[i].r_ohm), &t));
        TEST_ASSERT_FLOAT_WITHIN(pts[i].tol_k, pts[i].t_c, t);
        /* Same answer as the fan law's converter: one model for every consumer. */
        float t2 = -999.0f;
        TEST_ASSERT_EQUAL(NTC_OK, ntc_channel_temp_c(&THERMAL_NTC_COIL,
            (float)counts_for_r(pts[i].r_ohm) * 3304.0f / 4095.0f, &t2));
        TEST_ASSERT_FLOAT_WITHIN(1e-4f, t2, t);
    }
}

/* Open and short fail safe: neither can pass as a plausible temperature, and an open sensor can
 * never read as "cool" (which would let the fan law switch the blower off). */
void test_open_and_short_fail_safe(void) {
    ntc_guard_t ctx;
    ntc_guard_init_part(&ctx, 0, &THERMAL_NTC_COIL);
    float t = 0.0f;
    /* Open: node at the rail, and anything colder than -20 C. */
    for (uint16_t raw = counts_for_r(1041000.0f) + 1u; raw <= 4095u; raw++)  /* -20 C: 1041 k */
        TEST_ASSERT_EQUAL(NTC_GUARD_ERR_OPEN, ntc_guard_convert(&ctx, raw, &t));
    /* Short: node at ground, and anything hotter than 200 C. */
    for (uint16_t raw = 0u; raw <= 170u; raw++)
        TEST_ASSERT_EQUAL(NTC_GUARD_ERR_SHORT, ntc_guard_convert(&ctx, raw, &t));
    /* A real coil over-temperature (165 C trip, 180 C) still converts: it is not mistaken for a
     * short, so the coil guard sees it. */
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_convert(&ctx, counts_for_r(ntc_channel_r_at(&THERMAL_NTC_COIL, 180.0f)), &t));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 180.0f, t);
    /* read_safe reports them and does not update the history. */
    mock_adc_val = 4095;
    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_OPEN, ntc_guard_read_safe(&ctx, &t));
    mock_adc_val = 0;
    TEST_ASSERT_EQUAL(NTC_GUARD_ERR_SHORT, ntc_guard_read_safe(&ctx, &t));
    TEST_ASSERT_FALSE(ctx.valid);
}
