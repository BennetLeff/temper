#include "unity.h"
#include "hal_pwm.h"
#include "sdk_stub.h"
#include "driver/gpio.h"
#include <math.h>
#include <stdio.h>
extern const hal_pwm_ops_t hal_pwm_esp32_ops;
#define PWM hal_pwm_esp32_ops
static hal_pwm_config_t config;
void setUp(void){PWM.deinit(HAL_PWM_CHANNEL_FAN);sdk_reset();config=(hal_pwm_config_t){.frequency_hz=38000,.duty_percent=50,.dead_time_ns=307,.pin_high=4,.pin_low=5,.complementary=true};}
void tearDown(void){sdk_fail_api(NULL);sdk_fail_at(0);PWM.deinit(HAL_PWM_CHANNEL_FAN);}
static void off(void){TEST_ASSERT_EQUAL(0,sdk_pin(4,0));TEST_ASSERT_EQUAL(0,sdk_pin(5,0));}
void programmed_ticks_and_waveform(void){
 hal_pwm_state_t s;
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));off();
 TEST_ASSERT_EQUAL(0,sdk_glitches());
 TEST_ASSERT_EQUAL(HAL_OK,PWM.get_state(HAL_PWM_CHANNEL_FAN,&s));
 TEST_ASSERT_TRUE(s.configured);TEST_ASSERT_EQUAL(24,s.dead_time_ticks);TEST_ASSERT_EQUAL(300,s.dead_time_ns);
 TEST_ASSERT_EQUAL(24,sdk_rise());TEST_ASSERT_EQUAL(24,sdk_fall());TEST_ASSERT_EQUAL(0,sdk_conflicts());
 TEST_ASSERT_EQUAL(HAL_OK,PWM.start(HAL_PWM_CHANNEL_FAN));
 for(unsigned t=0;t<sdk_period();t++){
  int h=sdk_pin(4,t),l=sdk_pin(5,t);
  TEST_ASSERT_FALSE(h&&l);
  TEST_ASSERT_EQUAL(t>=24 && t<sdk_compare(),h);
  TEST_ASSERT_EQUAL(t>=sdk_compare()+24,l);
 }
 TEST_ASSERT_EQUAL(HAL_ERROR_BUSY,PWM.set_dead_time(HAL_PWM_CHANNEL_FAN,500));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.stop(HAL_PWM_CHANNEL_FAN));off();
 TEST_ASSERT_EQUAL(HAL_OK,PWM.set_dead_time(HAL_PWM_CHANNEL_FAN,313));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.get_state(HAL_PWM_CHANNEL_FAN,&s));TEST_ASSERT_EQUAL(25,s.dead_time_ticks);TEST_ASSERT_EQUAL(312,s.dead_time_ns);
 TEST_ASSERT_EQUAL(0,sdk_conflicts());off();
}
static int safe_pin(int p){
 return sdk_mode(p)==GPIO_MODE_OUTPUT && !sdk_pullup(p) && sdk_pulldown(p) &&
     !sdk_routed(p) && !sdk_held(p) && sdk_pin(p,0)==0;
}
static int safe_gpio(void){return safe_pin(4) && safe_pin(5);}
static void gpio_off(void){TEST_ASSERT_TRUE(safe_gpio());}
void gate_channel_remains_rejected(void){
 TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.init(HAL_PWM_CHANNEL_GATE,&config));
 TEST_ASSERT_EQUAL(0,sdk_calls());
}
void successful_deinit_reasserts_gpio_after_generator_reset(void){
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.start(HAL_PWM_CHANNEL_FAN));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));gpio_off();
}
void every_init_failure_is_off(void){

 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));int count=sdk_calls();TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));
 printf("Failure injection: %d initialization API calls\n",count);
 int unsafe=0, disabled=0;
 for(int n=1;n<=count;n++){
  sdk_reset();sdk_fail_at(n);
  TEST_ASSERT_EQUAL(HAL_ERROR,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
  if(!safe_gpio()) unsafe++;
  if(sdk_mode(4)!=GPIO_MODE_OUTPUT || sdk_mode(5)!=GPIO_MODE_OUTPUT) disabled++;
  printf("init failure=%d mode=%d,%d pullup=%d,%d pulldown=%d,%d safe=%d\n",n,
      sdk_mode(4),sdk_mode(5),sdk_pullup(4),sdk_pullup(5),sdk_pulldown(4),sdk_pulldown(5),safe_gpio());

  hal_pwm_state_t s={.configured=true};
  TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.get_state(HAL_PWM_CHANNEL_FAN,&s));TEST_ASSERT_FALSE(s.configured);
  TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.start(HAL_PWM_CHANNEL_FAN));
  sdk_fail_at(0);TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));
 }
 printf("Init failures: %d unsafe GPIO states; %d disabled-output states\n",unsafe,disabled);
 TEST_ASSERT_EQUAL(0,unsafe);
}
void partial_delay_update_invalidates(void){
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));sdk_fail_at(sdk_calls()+2);
 TEST_ASSERT_EQUAL(HAL_ERROR,PWM.set_dead_time(HAL_PWM_CHANNEL_FAN,500));gpio_off();
 hal_pwm_state_t s;TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.get_state(HAL_PWM_CHANNEL_FAN,&s));
 TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.start(HAL_PWM_CHANNEL_FAN));
}
void start_and_stop_failures_are_off(void){
 for(int n=1;n<=4;n++){
  sdk_reset();TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));sdk_fail_at(sdk_calls()+n);
  TEST_ASSERT_EQUAL(HAL_ERROR,PWM.start(HAL_PWM_CHANNEL_FAN));gpio_off();sdk_fail_at(0);TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));
 }
 sdk_reset();TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));TEST_ASSERT_EQUAL(HAL_OK,PWM.start(HAL_PWM_CHANNEL_FAN));
 sdk_fail_at(sdk_calls()+1);TEST_ASSERT_EQUAL(HAL_ERROR,PWM.emergency_stop());gpio_off();
}
void invalid_inputs_and_period_failure(void){
 config.frequency_hz=0;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 config.frequency_hz=38000;config.duty_percent=NAN;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 config.duty_percent=50;config.dead_time_ns=0;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 config.dead_time_ns=1001;TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 config.dead_time_ns=500;TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 TEST_ASSERT_EQUAL(HAL_ERROR_INVALID_ARG,PWM.set_duty(HAL_PWM_CHANNEL_FAN,0));
 sdk_fail_at(sdk_calls()+2);TEST_ASSERT_EQUAL(HAL_ERROR,PWM.set_frequency(HAL_PWM_CHANNEL_FAN,40000));gpio_off();
}
void every_deinit_failure_is_reported_and_retryable(void){
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.start(HAL_PWM_CHANNEL_FAN));
 int before=sdk_calls();
 TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));
 int count=sdk_calls()-before;
 printf("Failure injection: %d running deinit API calls\n",count);
 for(int n=1;n<=count;n++){
  sdk_reset();TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
  TEST_ASSERT_EQUAL(HAL_OK,PWM.start(HAL_PWM_CHANNEL_FAN));
  sdk_fail_at(sdk_calls()+n);
  TEST_ASSERT_EQUAL(HAL_ERROR,PWM.deinit(HAL_PWM_CHANNEL_FAN));
  gpio_off(); /* Includes one-shot failures in the final pad-restoration calls. */
  TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.start(HAL_PWM_CHANNEL_FAN));
  sdk_fail_at(0);TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));gpio_off();
 }
}
void operation_failures_finish_with_gpio_cleanup(void){
 for(int operation=0;operation<5;operation++){
  int count=operation==2?1:2;
  for(int n=1;n<=count;n++){
   sdk_reset();TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
   if(operation>=2) TEST_ASSERT_EQUAL(HAL_OK,PWM.start(HAL_PWM_CHANNEL_FAN));
   sdk_fail_at(sdk_calls()+n);
   hal_status_t result;
   switch(operation){
    case 0:result=PWM.set_dead_time(HAL_PWM_CHANNEL_FAN,500);break;
    case 1:result=PWM.set_frequency(HAL_PWM_CHANNEL_FAN,40000);break;
    case 2:result=PWM.set_duty(HAL_PWM_CHANNEL_FAN,45);break;
    case 3:result=PWM.stop(HAL_PWM_CHANNEL_FAN);break;
    default:result=PWM.emergency_stop();break;
   }
   TEST_ASSERT_EQUAL(HAL_ERROR,result);gpio_off();
   TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.start(HAL_PWM_CHANNEL_FAN));
   sdk_fail_at(0);TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));gpio_off();
  }
 }
}
void persistent_gpio_failure_does_not_claim_safe_or_forget_config(void){
 sdk_fail_api("gpio_set_direction");
 TEST_ASSERT_EQUAL(HAL_ERROR,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 TEST_ASSERT_FALSE(safe_gpio());
 TEST_ASSERT_EQUAL(HAL_ERROR,PWM.deinit(HAL_PWM_CHANNEL_FAN));
 TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY,PWM.start(HAL_PWM_CHANNEL_FAN));
 TEST_ASSERT_EQUAL(HAL_ERROR_BUSY,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 sdk_fail_api(NULL);
 TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));gpio_off();
}
void persistent_gpio_failure_after_resource_deletion_is_retryable(void){
 TEST_ASSERT_EQUAL(HAL_OK,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 TEST_ASSERT_EQUAL(HAL_OK,PWM.start(HAL_PWM_CHANNEL_FAN));
 sdk_fail_api("gpio_set_direction");
 TEST_ASSERT_EQUAL(HAL_ERROR,PWM.deinit(HAL_PWM_CHANNEL_FAN));
 TEST_ASSERT_FALSE(safe_gpio());
 TEST_ASSERT_FALSE(sdk_routed(4));TEST_ASSERT_FALSE(sdk_routed(5));
 TEST_ASSERT_EQUAL(HAL_ERROR,PWM.deinit(HAL_PWM_CHANNEL_FAN));
 TEST_ASSERT_EQUAL(HAL_ERROR_BUSY,PWM.init(HAL_PWM_CHANNEL_FAN,&config));
 sdk_fail_api(NULL);
 TEST_ASSERT_EQUAL(HAL_OK,PWM.deinit(HAL_PWM_CHANNEL_FAN));gpio_off();
}
int main(void){UnityBegin(__FILE__);RUN_TEST(gate_channel_remains_rejected);RUN_TEST(successful_deinit_reasserts_gpio_after_generator_reset);RUN_TEST(programmed_ticks_and_waveform);RUN_TEST(every_init_failure_is_off);RUN_TEST(partial_delay_update_invalidates);RUN_TEST(start_and_stop_failures_are_off);RUN_TEST(invalid_inputs_and_period_failure);RUN_TEST(every_deinit_failure_is_reported_and_retryable);RUN_TEST(operation_failures_finish_with_gpio_cleanup);RUN_TEST(persistent_gpio_failure_does_not_claim_safe_or_forget_config);RUN_TEST(persistent_gpio_failure_after_resource_deletion_is_retryable);return UnityEnd();}
