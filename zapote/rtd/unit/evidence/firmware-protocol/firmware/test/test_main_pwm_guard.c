#include "unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void test_validate_frequency_ok(void);
extern void test_validate_frequency_fail(void);
extern void test_self_test_pass(void);
extern void test_self_test_bad_freq(void);
extern void test_self_test_mismatch(void);
extern void test_self_test_bad_deadtime(void);
extern void test_integrity_check_measured_pass(void);
extern void test_integrity_check_measured_fail(void);
extern void test_integrity_check_corruption(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_validate_frequency_ok);
    RUN_TEST(test_validate_frequency_fail);
    RUN_TEST(test_self_test_pass);
    RUN_TEST(test_self_test_bad_freq);
    RUN_TEST(test_self_test_mismatch);
    RUN_TEST(test_self_test_bad_deadtime);
    RUN_TEST(test_integrity_check_measured_pass);
    RUN_TEST(test_integrity_check_measured_fail);
    RUN_TEST(test_integrity_check_corruption);
    return UnityEnd();
}
