/* Execute unmodified pinned D21 HAL, observing GPIO mode at return.
 * Only SDK-stub omissions are instrumented; this is not hardware emulation.
 * gpio.c:436-448: reset disables output, enables pull-up, disables pull-down.
 * mcpwm_gen.c:114-124: successful generator deletion calls gpio_reset_pin.
 * Preserve D21's one-shot failure counter: real reset's internal gpio_config
 * is not an extra injectable public call in the original stub sequence.
 */
#include <assert.h>
#include <stdio.h>
#define gpio_reset_pin original_gpio_reset_pin
#define gpio_set_direction original_gpio_set_direction
#define mcpwm_del_generator original_mcpwm_del_generator
#include "d21/firmware/test/pwm_sdk_stub/sdk_stub.c"
#undef gpio_reset_pin
#undef gpio_set_direction
#undef mcpwm_del_generator
static bool output_enabled[40], pullup_enabled[40];
esp_err_t gpio_reset_pin(int p) {
    esp_err_t e=original_gpio_reset_pin(p);
    if(e==ESP_OK) { output_enabled[p]=false; pullup_enabled[p]=true; }
    return e;
}
esp_err_t gpio_set_direction(int p,int n) {
    esp_err_t e=original_gpio_set_direction(p,n);
    if(e==ESP_OK) output_enabled[p]=(n==GPIO_MODE_OUTPUT);
    return e;
}
esp_err_t mcpwm_del_generator(mcpwm_gen_handle_t g) {
    int pin=g->pin;
    esp_err_t e=original_mcpwm_del_generator(g);
    if(e==ESP_OK) { output_enabled[pin]=false; pullup_enabled[pin]=true; }
    return e;
}
#include "d21/firmware/components/hal/esp32/hal_pwm_esp32.c"
int main(void) {
    const hal_pwm_ops_t *p=&hal_pwm_esp32_ops;
    hal_pwm_config_t c={.frequency_hz=38000,.duty_percent=50,.dead_time_ns=307,
        .pin_high=4,.pin_low=5,.complementary=true};
    sdk_reset();
    assert(p->init(0,&c)==HAL_OK);
    int count=sdk_calls();
    assert(output_enabled[4] && output_enabled[5]);
    assert(p->stop(0)==HAL_OK);
    printf("After init and stop: GPIO output enables=%d,%d; original stub levels=%d,%d\n",
        output_enabled[4],output_enabled[5],sdk_pin(4,0),sdk_pin(5,0));
    assert(p->deinit(0)==HAL_OK);
    assert(!output_enabled[4] && !output_enabled[5]);
    puts("After deinit: both outputs DISABLED with pull-ups (same cleanup side effect).");
    int lost=0;
    printf("Initialization failure positions probed: %d\n",count);
    for(int n=1;n<=count;n++) {
        sdk_reset(); sdk_fail_at(n);
        assert(p->init(0,&c)==HAL_ERROR);
        if(!output_enabled[4] || !output_enabled[5]) {
            lost++;
            printf("failure=%d final_output_en=%d,%d pullup=%d,%d original_stub_level=%d,%d\n",
                n,output_enabled[4],output_enabled[5],pullup_enabled[4],pullup_enabled[5],sdk_pin(4,0),sdk_pin(5,0));
        }
        sdk_fail_at(0); assert(p->deinit(0)==HAL_OK);
    }
    assert(lost>0);
    printf("REPRODUCED: %d failure positions leave at least one output disabled despite stub level 0.\n",lost);
    puts("Pad voltage UNDETERMINED: pull-ups, external pull-downs and pad holds require hardware evidence.");
    return 0; /* Success means discrepancy reproduced, never safe-state acceptance. */
}
