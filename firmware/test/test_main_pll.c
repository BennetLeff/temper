/**
 * @file test_main_pll.c
 * @brief Test runner for PLL control tests
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test runner from test_pll_control.c */
extern void run_pll_control_tests(void);

void setUp(void) {
    /* Nothing to set up - tests handle their own setup */
}

void tearDown(void) {
    /* Nothing to tear down */
}

int main(void) {
    UnityBegin("test_pll_control.c");
    
    printf("\n=== PLL Control Tests ===\n\n");
    run_pll_control_tests();
    
    return UnityEnd();
}
