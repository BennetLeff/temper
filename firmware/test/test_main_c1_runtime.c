/**
 * @file test_main_c1_runtime.c
 * @brief Runner for test_c1_runtime.c.
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_c1_runtime_tests(void);

void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UnityBegin("test_c1_runtime.c");
    printf("\n=== sensor-r3 C1 Runtime (state machine + pan_control) Tests ===\n\n");
    run_c1_runtime_tests();
    return UnityEnd();
}
