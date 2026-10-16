/**
 * @file test_main_c1_hs_ntc.c
 * @brief Runner for test_c1_hs_ntc.c (setUp/tearDown are defined there).
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_c1_hs_ntc_tests(void);

int main(void)
{
    UnityBegin("test_c1_hs_ntc.c");
    printf("\n=== sensor-r3 C1 Heatsink NTC (Vishay NTCALUG01A104GA, ADC1_CH5) Tests ===\n\n");
    run_c1_hs_ntc_tests();
    return UnityEnd();
}
