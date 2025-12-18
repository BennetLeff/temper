#include "unity/unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void run_low_temp_control_tests(void);

int main(void) {
    UnityBegin(__FILE__);
    run_low_temp_control_tests();
    return UnityEnd();
}