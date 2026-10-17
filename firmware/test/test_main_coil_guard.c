#include "unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void test_coil_guard_init(void);
extern void test_normal_operation(void);
extern void test_inductance_drop_warn(void);
extern void test_inductance_drop_fault(void);
extern void test_overtemp(void);
extern void test_invalid_coil_reading_fails_safe(void);
extern void test_guard_and_fan_law_agree(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_coil_guard_init);
    RUN_TEST(test_normal_operation);
    RUN_TEST(test_inductance_drop_warn);
    RUN_TEST(test_inductance_drop_fault);
    RUN_TEST(test_overtemp);
    RUN_TEST(test_invalid_coil_reading_fails_safe);
    RUN_TEST(test_guard_and_fan_law_agree);
    return UnityEnd();
}
