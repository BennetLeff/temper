#include "unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void test_probe_init_defaults(void);
extern void test_probe_detects_air_on_rapid_rise(void);
extern void test_probe_detects_food_on_slow_rise(void);
extern void test_probe_fallback_logic(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_probe_init_defaults);
    RUN_TEST(test_probe_detects_air_on_rapid_rise);
    RUN_TEST(test_probe_detects_food_on_slow_rise);
    RUN_TEST(test_probe_fallback_logic);
    return UnityEnd();
}
