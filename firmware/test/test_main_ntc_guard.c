#include "unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void test_ntc_short_circuit(void);
extern void test_ntc_open_circuit(void);
extern void test_valid_reading(void);
extern void test_cold_sensor_is_not_open(void);
extern void test_heatsink_trip_temperature_scale(void);
extern void test_above_sensor_rating_is_out_of_range(void);
extern void test_rate_of_change_violation(void);
extern void test_cross_check_fail(void);
extern void test_cross_check_pass(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_ntc_short_circuit);
    RUN_TEST(test_ntc_open_circuit);
    RUN_TEST(test_valid_reading);
    RUN_TEST(test_cold_sensor_is_not_open);
    RUN_TEST(test_heatsink_trip_temperature_scale);
    RUN_TEST(test_above_sensor_rating_is_out_of_range);
    RUN_TEST(test_rate_of_change_violation);
    RUN_TEST(test_cross_check_fail);
    RUN_TEST(test_cross_check_pass);
    return UnityEnd();
}
