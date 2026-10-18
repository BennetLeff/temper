/**
 * @file test_main_c1_rtd_service.c
 * @brief Runner for test_c1_rtd_service.c.
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_c1_rtd_service_tests(void);

int main(void)
{
    UnityBegin("test_c1_rtd_service.c");
    printf("\n=== sensor-r3 C1 MAX31865 Service Tests ===\n\n");
    run_c1_rtd_service_tests();
    return UnityEnd();
}
