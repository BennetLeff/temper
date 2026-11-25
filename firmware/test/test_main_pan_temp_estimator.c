/**
 * @file test_main_pan_temp_estimator.c
 * @brief Runner for the sensor-r3 pan-temperature estimator tests.
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_pan_temp_estimator_tests(void);

void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UnityBegin("test_pan_temp_estimator.c");
    printf("\n=== sensor-r3 Pan Temperature Estimator Tests ===\n\n");
    run_pan_temp_estimator_tests();
    return UnityEnd();
}
