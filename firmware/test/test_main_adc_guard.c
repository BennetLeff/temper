#include "unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void test_adc_guard_init(void);
extern void test_range_check_low(void);
extern void test_range_check_high(void);
extern void test_range_check_valid(void);
extern void test_stuck_value_detection(void);
extern void test_varying_signal_ok(void);
extern void test_watchdog_timeout(void);
extern void test_watchdog_refresh(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_adc_guard_init);
    RUN_TEST(test_range_check_low);
    RUN_TEST(test_range_check_high);
    RUN_TEST(test_range_check_valid);
    RUN_TEST(test_stuck_value_detection);
    RUN_TEST(test_varying_signal_ok);
    RUN_TEST(test_watchdog_timeout);
    RUN_TEST(test_watchdog_refresh);
    return UnityEnd();
}
