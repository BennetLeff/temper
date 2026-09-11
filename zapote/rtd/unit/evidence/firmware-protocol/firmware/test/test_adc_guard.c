#include "unity.h"
#include "adc_guard.h"
#include "hal_adc.h"
#include <string.h>

// Mocks
static uint16_t mock_adc_val = 0;
static hal_status_t mock_adc_read_return = HAL_OK;
static uint32_t mock_tick_ms = 0;

// Global ADC ops pointer (required by HAL)
const hal_adc_ops_t *hal_adc = NULL;

#define HAL_ADC_CHANNEL_0 0

hal_status_t mock_read_raw(hal_adc_channel_t channel, uint16_t *value) {
    *value = mock_adc_val;
    return mock_adc_read_return;
}

// Mock HAL interface
static const hal_adc_ops_t mock_adc_ops = {
    .read_raw = mock_read_raw,
    // Other ops not used
};

// Implement external dependency
uint32_t hal_get_tick_ms(void) {
    return mock_tick_ms;
}

void setUp(void) {
    hal_adc = &mock_adc_ops;
    mock_adc_val = 2048; // Valid mid-range
    mock_adc_read_return = HAL_OK;
    mock_tick_ms = 1000;
}

void tearDown(void) {
}

void test_adc_guard_init(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    
    TEST_ASSERT_EQUAL(HAL_ADC_CHANNEL_0, ctx.channel);
    TEST_ASSERT_TRUE(ctx.active);
    TEST_ASSERT_EQUAL(1000, ctx.last_update_ms);
}

void test_range_check_low(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    
    mock_adc_val = 50; // Below MIN (100)
    uint16_t val;
    adc_guard_status_t status = adc_guard_read_safe(&ctx, &val);
    
    TEST_ASSERT_EQUAL(ADC_GUARD_ERR_RANGE_LOW, status);
}

void test_range_check_high(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    
    mock_adc_val = 4000; // Above MAX (3950)
    uint16_t val;
    adc_guard_status_t status = adc_guard_read_safe(&ctx, &val);
    
    TEST_ASSERT_EQUAL(ADC_GUARD_ERR_RANGE_HIGH, status);
}

void test_range_check_valid(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    
    mock_adc_val = 2048;
    uint16_t val;
    adc_guard_status_t status = adc_guard_read_safe(&ctx, &val);
    
    TEST_ASSERT_EQUAL(ADC_GUARD_OK, status);
    TEST_ASSERT_EQUAL(2048, val);
}

void test_stuck_value_detection(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    uint16_t val;
    
    // Fill buffer with identical values
    mock_adc_val = 2000;
    for (int i = 0; i < ADC_STUCK_BUFFER_SIZE; i++) {
        adc_guard_read_safe(&ctx, &val);
    }
    
    // Next read should trigger stuck detection (variance = 0)
    adc_guard_status_t status = adc_guard_read_safe(&ctx, &val);
    TEST_ASSERT_EQUAL(ADC_GUARD_ERR_STUCK, status);
}

void test_varying_signal_ok(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    uint16_t val;
    
    // Fill buffer with varying values (triangle wave)
    for (int i = 0; i < ADC_STUCK_BUFFER_SIZE; i++) {
        mock_adc_val = 2000 + (i * 10); // Sufficient variance
        adc_guard_read_safe(&ctx, &val);
    }
    
    adc_guard_status_t status = adc_guard_read_safe(&ctx, &val);
    TEST_ASSERT_EQUAL(ADC_GUARD_OK, status);
}

void test_watchdog_timeout(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    
    // Initial state OK
    TEST_ASSERT_EQUAL(ADC_GUARD_OK, adc_guard_check_stale(&ctx));
    
    // Advance time beyond limit (500ms)
    mock_tick_ms += 600;
    
    TEST_ASSERT_EQUAL(ADC_GUARD_ERR_STALE, adc_guard_check_stale(&ctx));
}

void test_watchdog_refresh(void) {
    adc_guard_channel_t ctx;
    adc_guard_init(&ctx, HAL_ADC_CHANNEL_0);
    uint16_t val;
    
    // Advance time a bit
    mock_tick_ms += 400;
    TEST_ASSERT_EQUAL(ADC_GUARD_OK, adc_guard_check_stale(&ctx));
    
    // Read updates timestamp
    adc_guard_read_safe(&ctx, &val);
    
    // Advance more (would be 800 total, but reset at 400)
    mock_tick_ms += 400;
    
    TEST_ASSERT_EQUAL(ADC_GUARD_OK, adc_guard_check_stale(&ctx));
}
