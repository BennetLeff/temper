#include "unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void test_fan_guard_init(void);
extern void test_normal_operation(void);
extern void test_rapid_rise_blocked(void);
extern void test_moderate_rise_restricted(void);
extern void test_equilibrium_degraded(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_fan_guard_init);
    RUN_TEST(test_normal_operation);
    RUN_TEST(test_rapid_rise_blocked);
    RUN_TEST(test_moderate_rise_restricted);
    RUN_TEST(test_equilibrium_degraded);
    return UnityEnd();
}
