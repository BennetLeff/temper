/**
 * @file test_main_c1_rim_ntc.c
 * @brief Runner for test_c1_rim_ntc.c (setUp/tearDown are defined there).
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_c1_rim_ntc_tests(void);

int main(void)
{
    UnityBegin("test_c1_rim_ntc.c");
    printf("\n=== sensor-r3 C1 Rim NTC (Semitec 104GT-2, CR-7) Tests ===\n\n");
    run_c1_rim_ntc_tests();
    return UnityEnd();
}
