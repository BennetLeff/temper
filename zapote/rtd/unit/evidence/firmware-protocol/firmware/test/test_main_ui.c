#include "unity.h"

extern void setUp(void);
extern void tearDown(void);
extern void test_ui_init(void);
extern void test_ui_led_state_indication(void);
extern void test_ui_led_fault_indication(void);
extern void test_ui_temperature_adjustment(void);
extern void test_ui_settings_transition(void);
extern void test_ui_menu_cycling(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_ui_init);
    RUN_TEST(test_ui_led_state_indication);
    RUN_TEST(test_ui_led_fault_indication);
    RUN_TEST(test_ui_temperature_adjustment);
    RUN_TEST(test_ui_settings_transition);
    RUN_TEST(test_ui_menu_cycling);
    return UnityEnd();
}
