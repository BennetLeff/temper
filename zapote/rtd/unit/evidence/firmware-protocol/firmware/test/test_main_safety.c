/**
 * @file test_main_safety.c
 * @brief Standalone test runner for safety module
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_safety_tests(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_safety.c");
    
    printf("\n=== Safety Module Tests ===\n\n");
    run_safety_tests();
    
    return UnityEnd();
}
