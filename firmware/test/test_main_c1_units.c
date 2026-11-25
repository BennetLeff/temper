/**
 * @file test_main_c1_units.c
 * @brief Runner for test_c1_units.c.
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_c1_units_tests(void);

void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UnityBegin("test_c1_units.c");
    printf("\n=== sensor-r3 C1 Runaway Supervisor + RTD Conversion Tests ===\n\n");
    run_c1_units_tests();
    return UnityEnd();
}
