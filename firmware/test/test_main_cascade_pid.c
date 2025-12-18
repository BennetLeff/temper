/**
 * @file test_main_cascade_pid.c
 * @brief Standalone test runner for cascade PID controller
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_cascade_pid_tests(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_cascade_pid.c");
    
    printf("\n=== Cascade PID Controller Tests ===\n\n");
    run_cascade_pid_tests();
    
    return UnityEnd();
}