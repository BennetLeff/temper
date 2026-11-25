/**
 * @file test_main_pan_temp_loop.c
 * @brief Runner for the sensor-r3 C1 loop tests (guard, plant gain, PID, authority).
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_pan_temp_loop_tests(void);

void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UnityBegin("test_pan_temp_loop.c");
    printf("\n=== sensor-r3 Pan Temperature Loop Tests ===\n\n");
    run_pan_temp_loop_tests();
    return UnityEnd();
}
