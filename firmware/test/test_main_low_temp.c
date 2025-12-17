/**
 * @file test_main_low_temp.c
 * @brief Standalone test runner for low-temperature control
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_low_temp_control_tests(void);

int main(void) {
    UnityBegin("test_low_temp_control.c");
    
    printf("\n=== Low Temperature Control Tests ===\n\n");
    run_low_temp_control_tests();
    
    return UnityEnd();
}
