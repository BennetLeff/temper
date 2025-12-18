#include "unity.h"

extern void test_profile_init(void);
extern void test_profile_start(void);
extern void test_profile_transition_time(void);
extern void test_profile_completion(void);
extern void test_profile_settings(void);

int main(void) {
    UnityBegin(__FILE__);
    RUN_TEST(test_profile_init);
    RUN_TEST(test_profile_start);
    RUN_TEST(test_profile_transition_time);
    RUN_TEST(test_profile_completion);
    RUN_TEST(test_profile_settings);
    return UnityEnd();
}
