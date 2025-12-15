/**
 * @file test_main_pan_detection.c
 * @brief Test runner for pan detection tests
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test runner from test_pan_detection.c */
extern void run_pan_detection_tests(void);

void setUp(void) {
    /* Nothing to set up for pan detection logic tests */
}

void tearDown(void) {
    /* Nothing to tear down */
}

int main(void) {
    UnityBegin("test_pan_detection.c");
    
    printf("\n=== Pan Detection Tests ===\n\n");
    run_pan_detection_tests();
    
    return UnityEnd();
}
