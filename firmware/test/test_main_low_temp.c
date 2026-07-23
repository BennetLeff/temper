#include "unity/unity.h"

extern void run_low_temp_control_tests(void);

/* The shared test runner supplies these fixtures for test_runner.  This
 * standalone executable needs its own Unity symbols. */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin(__FILE__);
    run_low_temp_control_tests();
    return UnityEnd();
}
