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

void setUp(void) {
    hal_adc = &mock_adc_ops;
    mock_adc_val = 2048; // ~25C
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
    
    mock_adc_val = 2048;
    TEST_ASSERT_EQUAL(NTC_GUARD_OK, ntc_guard_read_safe(&ctx, &temp));
    // Check approximate temp at 2048 (R_ntc = R_pullup) -> 25C
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 25.0f, temp);
}

void test_rate_of_change_violation(void) {
    ntc_guard_t ctx;
    ntc_guard_init(&ctx, 0);
    float temp;
    
    // First read: 25C
    mock_adc_val = 2048;
    ntc_guard_read_safe(&ctx, &temp);
    
    // Advance time 1 sec
    mock_tick_ms += 1000;
    
    // Jump to 85C (ADC ~435) -> 60C change in 1 sec > 10C/sec limit
    mock_adc_val = 435;
    
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
