/**
 * @file test_main_wdi_supervisor.c
 * @brief Test runner for test_wdi_supervisor.c
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_wdi_supervisor_tests(void);
extern void wdi_supervisor_test_setup(void);

void setUp(void) {
    wdi_supervisor_test_setup();
}

void tearDown(void) {
}

int main(void) {
    UnityBegin("test_wdi_supervisor.c");
    printf("\n=== wdi_supervisor tests ===\n\n");
    run_wdi_supervisor_tests();
    return UnityEnd();
}
