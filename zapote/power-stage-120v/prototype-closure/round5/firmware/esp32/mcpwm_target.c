#include "mcpwm_target.h"
#include "pins.h"
#include "driver/gpio.h"
#include "driver/mcpwm_prelude.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
typedef struct {
    mcpwm_timer_handle_t timer;
    mcpwm_oper_handle_t op[2];
    mcpwm_cmpr_handle_t rise[2],fall[2];
    mcpwm_gen_handle_t gen[4];
    bridge_cycle_t programmed;
    bool initialized, running, request;
    volatile bool stopped;
} target_t;
static target_t hw;
static bool IRAM_ATTR stopped(mcpwm_timer_handle_t timer,const mcpwm_timer_event_data_t *event,void *ctx)
{ (void)timer; (void)event; ((target_t *)ctx)->stopped=true; return false; }
static void inhibit(void *context)
{
    target_t *t=context;
    gpio_set_level(R5_REQUEST,0); t->request=false;
    const int pins[4]={R5_PWM_AH,R5_PWM_AL,R5_PWM_BH,R5_PWM_BL};
    for(unsigned i=0;i<4;++i) {
        if(t->gen[i]) (void)mcpwm_generator_set_force_level(t->gen[i],0,true);
        /* Disconnect the GPIO matrix too: dead-time inversion downstream of a
           forced raw generator must never be assumed to produce a low pad. */
        (void)gpio_reset_pin(pins[i]);
        (void)gpio_set_level(pins[i],0);
        (void)gpio_set_direction(pins[i],GPIO_MODE_OUTPUT);
    }
}
static bool request(void *context,bool value)
{
    target_t *t=context;
    /* Hardware commissioning is intentionally absent. No command may grant heat. */
    if(value) { inhibit(t); return false; }
    gpio_set_level(R5_REQUEST,0); t->request=false; return true;
}
static bool apply(void *context,const bridge_cycle_t *c)
{
    target_t *t=context;
    if(!c || !t->initialized || t->request || c->period<4 || !c->dead_ticks) return false;
    uint32_t half=c->period/2;
    if(c->period%2 || c->dead_ticks>=half/2) return false;
    uint32_t shift=(c->pulse[2].rise+c->period-c->dead_ticks)%c->period;
    /* phase=1's fall-at-period requires a different event topology. Reject it.
       Fixed frequency/deadtime once created: do not rewrite an active timer. */
    if(shift>=half || c->period!=t->programmed.period || c->dead_ticks!=t->programmed.dead_ticks) return false;
    for(unsigned i=0;i<4;++i) if(c->pulse[i].width!=half-c->dead_ticks) return false;
    if(c->pulse[0].rise!=c->dead_ticks || c->pulse[1].rise!=half+c->dead_ticks ||
       c->pulse[3].rise!=(shift+half+c->dead_ticks)%c->period) return false;
    if(t->running && memcmp(c,&t->programmed,sizeof *c)==0) return true;
    inhibit(t);
    if(t->running) {
        t->stopped=false;
        if(mcpwm_timer_start_stop(t->timer,MCPWM_TIMER_STOP_EMPTY)!=ESP_OK) return false;
        int64_t until=esp_timer_get_time()+2000;
        while(!t->stopped && esp_timer_get_time()<until) taskYIELD();
        if(!t->stopped) return false;
        t->running=false;
    }
    /* All writes occur on a stopped common timer with both generators forced
       low and request low. This is an atomic DISABLED setup, not a live update. */
    for(unsigned leg=0;leg<2;++leg) {
        uint32_t r=leg?shift:0, f=r+half;
        if(mcpwm_comparator_set_compare_value(t->rise[leg],r)!=ESP_OK ||
           mcpwm_comparator_set_compare_value(t->fall[leg],f)!=ESP_OK ||
           mcpwm_generator_set_action_on_timer_event(t->gen[2*leg],
             MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,MCPWM_TIMER_EVENT_EMPTY,
               r?MCPWM_GEN_ACTION_LOW:MCPWM_GEN_ACTION_HIGH))!=ESP_OK) return false;
    }
    t->programmed=*c;
    /* Deliberately retain force-low. An explicit bench harness may inspect
       internal counters, but this image emits no gate waveform. */
    if(mcpwm_timer_start_stop(t->timer,MCPWM_TIMER_START_NO_STOP)!=ESP_OK) return false;
    t->running=true;
    return true;
}
bool r5_pwm_init(bridge_backend_t *backend)
{
    memset(&hw,0,sizeof hw);
    gpio_config_t io={.pin_bit_mask=1ULL<<R5_REQUEST,.mode=GPIO_MODE_OUTPUT,.pull_down_en=GPIO_PULLDOWN_ENABLE};
    if(gpio_config(&io)!=ESP_OK) return false;
    gpio_set_level(R5_REQUEST,0);
    if(!bridge_plan_cycle(80000000,50000,125,0,&hw.programmed)) return false;
    mcpwm_timer_config_t tc={.group_id=0,.clk_src=MCPWM_TIMER_CLK_SRC_DEFAULT,
      .resolution_hz=80000000,.count_mode=MCPWM_TIMER_COUNT_MODE_UP,.period_ticks=hw.programmed.period};
    if(mcpwm_new_timer(&tc,&hw.timer)!=ESP_OK) return false;
    mcpwm_timer_event_callbacks_t cb={.on_stop=stopped};
    if(mcpwm_timer_register_event_callbacks(hw.timer,&cb,&hw)!=ESP_OK) return false;
    const int pins[4]={R5_PWM_AH,R5_PWM_AL,R5_PWM_BH,R5_PWM_BL};
    for(unsigned leg=0;leg<2;++leg) {
        mcpwm_operator_config_t oc={.group_id=0};
        mcpwm_comparator_config_t cc={0}; /* immediate, but only while stopped */
        if(mcpwm_new_operator(&oc,&hw.op[leg])!=ESP_OK ||
           mcpwm_operator_connect_timer(hw.op[leg],hw.timer)!=ESP_OK ||
           mcpwm_new_comparator(hw.op[leg],&cc,&hw.rise[leg])!=ESP_OK ||
           mcpwm_new_comparator(hw.op[leg],&cc,&hw.fall[leg])!=ESP_OK) goto fail;
        for(unsigned p=0;p<2;++p) {
            mcpwm_generator_config_t gc={.gen_gpio_num=pins[2*leg+p]};
            if(mcpwm_new_generator(hw.op[leg],&gc,&hw.gen[2*leg+p])!=ESP_OK ||
               mcpwm_generator_set_force_level(hw.gen[2*leg+p],0,true)!=ESP_OK) goto fail;
        }
        if(mcpwm_generator_set_action_on_compare_event(hw.gen[2*leg],
             MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,hw.rise[leg],MCPWM_GEN_ACTION_HIGH))!=ESP_OK ||
           mcpwm_generator_set_action_on_compare_event(hw.gen[2*leg],
             MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,hw.fall[leg],MCPWM_GEN_ACTION_LOW))!=ESP_OK) goto fail;
        mcpwm_dead_time_config_t dt={.posedge_delay_ticks=hw.programmed.dead_ticks};
        if(mcpwm_generator_set_dead_time(hw.gen[2*leg],hw.gen[2*leg],&dt)!=ESP_OK) goto fail;
        dt=(mcpwm_dead_time_config_t){.negedge_delay_ticks=hw.programmed.dead_ticks,.flags.invert_output=true};
        if(mcpwm_generator_set_dead_time(hw.gen[2*leg],hw.gen[2*leg+1],&dt)!=ESP_OK) goto fail;
    }
    if(mcpwm_timer_enable(hw.timer)!=ESP_OK) goto fail;
    hw.initialized=true;
    *backend=(bridge_backend_t){apply,request,inhibit,&hw};
    return apply(&hw,&hw.programmed);
fail: inhibit(&hw); return false;
}
