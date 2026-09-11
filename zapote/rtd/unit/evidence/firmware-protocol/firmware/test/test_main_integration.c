/**
 * @file test_main_integration.c
 * @brief Standalone test runner for integration tests
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_integration_tests(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_integration.c");
    
    printf("\n=== Integration Tests ===\n\n");
    run_integration_tests();
    
    return UnityEnd();
}
