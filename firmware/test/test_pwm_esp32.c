#include "unity.h"
#include "hal_pwm.h"
#include "sdk_stub.h"
#include <math.h>
#include <stdio.h>
extern const hal_pwm_ops_t hal_pwm_esp32_ops;
#define PWM hal_pwm_esp32_ops
static hal_pwm_config_t config;
void setUp(void){PWM.deinit(0);sdk_reset();config=(hal_pwm_config_t){.frequency_hz=38000,.duty_percent=50,.dead_time_ns=307,.pin_high=4,.pin_low=5,.complementary=true};}
void tearDown(void){sdk_fail_at(0);PWM.deinit(0);}
static void off(void){TEST_ASSERT_EQUAL(0,sdk_pin(4,0));TEST_ASSERT_EQUAL(0,sdk_pin(5,0));}
void programmed_ticks_and_waveform(void){
 hal_pwm_state_t s;
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(0,&config));off();
 TEST_ASSERT_EQUAL(0,sdk_glitches());
 TEST_ASSERT_EQUAL(HAL_OK,PWM.get_state(0,&s));
 TEST_ASSERT_TRUE(s.configured);TEST_ASSERT_EQUAL(24,s.dead_time_ticks);TEST_ASSERT_EQUAL(300,s.dead_time_ns);
 TEST_ASSERT_EQUAL(24,sdk_rise());TEST_ASSERT_EQUAL(24,sdk_fall());TEST_ASSERT_EQUAL(0,sdk_conflicts());
 TEST_ASSERT_EQUAL(HAL_OK,PWM.start(0));
 for(unsigned t=0;t<sdk_period();t++){
  int h=sdk_pin(4,t),l=sdk_pin(5,t);
  TEST_ASSERT_FALSE(h&&l);
  TEST_ASSERT_EQUAL(t>=24 && t<sdk_compare(),h);
  TEST_ASSERT_EQUAL(t>=sdk_compare()+24,l);
 }
 TEST_ASSERT_EQUAL(HAL_ERROR_BUSY,PWM.set_dead_time(0,500));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.stop(0));off();
 TEST_ASSERT_EQUAL(HAL_OK,PWM.set_dead_time(0,313));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.get_state(0,&s));TEST_ASSERT_EQUAL(25,s.dead_time_ticks);TEST_ASSERT_EQUAL(312,s.dead_time_ns);
 TEST_ASSERT_EQUAL(0,sdk_conflicts());off();
}
void every_init_failure_is_off(void){
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(0,&config));int count=sdk_calls();TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(0));
 printf("Failure injection: %d initialization API calls\n",count);
 for(int n=1;n<=count;n++){
  sdk_reset();sdk_fail_at(n);
  TEST_ASSERT_EQUAL(HAL_ERROR,PWM.init(0,&config));off();
  hal_pwm_state_t s={.configured=true};
  TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.get_state(0,&s));TEST_ASSERT_FALSE(s.configured);
  TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.start(0));
  sdk_fail_at(0);TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(0));
 }
}
void partial_delay_update_invalidates(void){
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(0,&config));sdk_fail_at(sdk_calls()+2);
 TEST_ASSERT_EQUAL(HAL_ERROR,PWM.set_dead_time(0,500));off();
 hal_pwm_state_t s;TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.get_state(0,&s));
 TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.start(0));
}
void start_and_stop_failures_are_off(void){
 for(int n=1;n<=4;n++){
  sdk_reset();TEST_ASSERT_EQUAL(HAL_OK,PWM.init(0,&config));sdk_fail_at(sdk_calls()+n);
  TEST_ASSERT_EQUAL(HAL_ERROR,PWM.start(0));off();sdk_fail_at(0);TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(0));
 }
 sdk_reset();TEST_ASSERT_EQUAL(HAL_OK,PWM.init(0,&config));TEST_ASSERT_EQUAL(HAL_OK,PWM.start(0));
 sdk_fail_at(sdk_calls()+1);TEST_ASSERT_EQUAL(HAL_ERROR,PWM.emergency_stop());off();
}
void invalid_inputs_and_period_failure(void){
 config.frequency_hz=0;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(0,&config));
 config.frequency_hz=38000;config.duty_percent=NAN;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(0,&config));
 config.duty_percent=50;config.dead_time_ns=0;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(0,&config));
 config.dead_time_ns=1001;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(0,&config));
 config.dead_time_ns=500;TEST_ASSERT_EQUAL(HAL_OK,PWM.init(0,&config));
 TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.set_duty(0,0));
 sdk_fail_at(sdk_calls()+2);TEST_ASSERT_EQUAL(HAL_ERROR,PWM.set_frequency(0,40000));off();
}
int main(void){UnityBegin(__FILE__);RUN_TEST(programmed_ticks_and_waveform);RUN_TEST(every_init_failure_is_off);RUN_TEST(partial_delay_update_invalidates);RUN_TEST(start_and_stop_failures_are_off);RUN_TEST(invalid_inputs_and_period_failure);return UnityEnd();}
