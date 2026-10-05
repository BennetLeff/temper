#include "mcpwm_target.h"
#include "pins.h"
#include "driver/gpio.h"
#include "driver/mcpwm_prelude.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
/* DECISIONS 2026-10-05 (D-27): commanded separation <= half a period.
 * Lower phases remain unqualified; this entire image stays inhibited. */
enum { PHASE_LIMIT_PERIOD_DIVISOR = 2 };
typedef struct {
    mcpwm_timer_handle_t timer;
    mcpwm_oper_handle_t op[2];
    mcpwm_cmpr_handle_t rise[2],fall[2];
    mcpwm_gen_handle_t gen[4];
    bridge_cycle_t programmed;
    bool initialized, enabled, running, request, fault;
    volatile bool stopped;
} target_t;
static target_t hw;
static const int pwm_pins[4]={R5_PWM_AH,R5_PWM_AL,R5_PWM_BH,R5_PWM_BL};
static bool IRAM_ATTR stopped(mcpwm_timer_handle_t timer,const mcpwm_timer_event_data_t *event,void *ctx)
{ (void)timer; (void)event; ((target_t *)ctx)->stopped=true; return false; }

/* Last operation after cleanup, including failed deletion. gpio_reset_pin()
 * disables output and enables a pull-up; generator deletion calls it too.
 * Attempt every operation on every pad even if one fails. The caller retains
 * the error; external pull-downs/PERMIT remain necessary on hardware failure. */
static bool restore_pads(target_t *t)
{
    bool ok=true;
    t->request=false;
    /* REQUEST never belongs to MCPWM. Do not reset it and briefly enable a
     * pull-up: preload low before configuring its dedicated GPIO output. */
    if(gpio_set_level(R5_REQUEST,0)!=ESP_OK) ok=false;
    gpio_config_t request_io={.pin_bit_mask=1ULL<<R5_REQUEST,
      .mode=GPIO_MODE_OUTPUT,.pull_down_en=GPIO_PULLDOWN_ENABLE};
    if(gpio_config(&request_io)!=ESP_OK) ok=false;
    if(gpio_set_level(R5_REQUEST,0)!=ESP_OK) ok=false;
    for(unsigned i=0;i<4;++i) {
        int pin=pwm_pins[i];
        if(gpio_set_level(pin,0)!=ESP_OK) ok=false;
        if(gpio_reset_pin(pin)!=ESP_OK) ok=false;
        if(gpio_set_level(pin,0)!=ESP_OK) ok=false;
        if(gpio_pullup_dis(pin)!=ESP_OK) ok=false;
        if(gpio_pulldown_en(pin)!=ESP_OK) ok=false;
        if(gpio_set_direction(pin,GPIO_MODE_OUTPUT)!=ESP_OK) ok=false;
    }
    if(!ok) t->fault=true;
    return ok;
}
static bool stop_timer(target_t *t)
{
    if(!t->running) return true;
    t->stopped=false;
    if(mcpwm_timer_start_stop(t->timer,MCPWM_TIMER_STOP_EMPTY)!=ESP_OK) return false;
    int64_t until=esp_timer_get_time()+2000;
    while(!t->stopped && esp_timer_get_time()<until) taskYIELD();
    if(!t->stopped) return false;
    t->running=false;
    return true;
}
static bool cleanup(target_t *t)
{
    bool ok=restore_pads(t); /* REQUEST low independently before MCPWM calls. */
    t->initialized=false;
    if(!stop_timer(t)) ok=false;
    if(t->enabled && !t->running) {
        if(mcpwm_timer_disable(t->timer)==ESP_OK) t->enabled=false;
        else ok=false;
    }
    /* Retain failed handles; never delete a parent with live children or
     * forget resources on reinitialization. Pads are disconnected regardless. */
    if(!t->enabled) {
        for(unsigned i=0;i<4;++i) if(t->gen[i]) {
            if(mcpwm_del_generator(t->gen[i])==ESP_OK) t->gen[i]=NULL;
            else ok=false;
        }
        for(unsigned leg=0;leg<2;++leg) {
            if(t->gen[2*leg] || t->gen[2*leg+1]) continue;
            if(t->rise[leg]) {
                if(mcpwm_del_comparator(t->rise[leg])==ESP_OK) t->rise[leg]=NULL;
                else ok=false;
            }
            if(t->fall[leg]) {
                if(mcpwm_del_comparator(t->fall[leg])==ESP_OK) t->fall[leg]=NULL;
                else ok=false;
            }
            if(t->op[leg] && !t->rise[leg] && !t->fall[leg]) {
                if(mcpwm_del_operator(t->op[leg])==ESP_OK) t->op[leg]=NULL;
                else ok=false;
            }
        }
        if(t->timer && !t->op[0] && !t->op[1]) {
            if(mcpwm_del_timer(t->timer)==ESP_OK) t->timer=NULL;
            else ok=false;
        }
    }
    /* No MCPWM operation follows this. Retry a transient GPIO failure once,
     * but never convert the original error into success. */
    if(!restore_pads(t)) { ok=false; (void)restore_pads(t); }
    if(!ok) t->fault=true;
    return ok;
}
static bool fail(target_t *t)
{
    t->fault=true;
    (void)cleanup(t);
    return false;
}
static void inhibit(void *context)
{
    target_t *t=context;
    /* The shared callback is void: latch GPIO failure, rejecting subsequent
     * bool operations until a successful explicit reinitialization. */
    if(!restore_pads(t)) (void)fail(t);
}
static bool request(void *context,bool value)
{
    target_t *t=context;
    if(value || t->fault) return fail(t);
    if(!restore_pads(t)) return fail(t);
    return true;
}
static bool apply(void *context,const bridge_cycle_t *c)
{
    target_t *t=context;
    if(!c || !t->initialized || t->fault || t->request || c->period<4 || !c->dead_ticks) return fail(t);
    uint32_t half=c->period/2;
    if(c->period%2 || c->dead_ticks>=half/2) return fail(t);
    for(unsigned i=0;i<4;++i)
        if(c->pulse[i].rise>=c->period || c->pulse[i].width!=half-c->dead_ticks) return fail(t);
    uint32_t shift=(c->pulse[2].rise+c->period-c->dead_ticks)%c->period;
    if(shift>c->period/PHASE_LIMIT_PERIOD_DIVISOR ||
       c->period!=t->programmed.period || c->dead_ticks!=t->programmed.dead_ticks) return fail(t);
    if(c->pulse[0].rise!=c->dead_ticks || c->pulse[1].rise!=half+c->dead_ticks ||
       c->pulse[3].rise!=(shift+half+c->dead_ticks)%c->period) return fail(t);
    if(!restore_pads(t)) return fail(t);
    if(t->running && memcmp(c,&t->programmed,sizeof *c)==0) return true;
    if(!stop_timer(t)) return fail(t);
    /* Atomic DISABLED setup. At 180 degrees the B falling compare wraps to
     * zero, consistent with the EMPTY low action. Target timing remains HIL. */
    for(unsigned leg=0;leg<2;++leg) {
        uint32_t r=leg?shift:0, f=(r+half)%c->period;
        if(mcpwm_comparator_set_compare_value(t->rise[leg],r)!=ESP_OK ||
           mcpwm_comparator_set_compare_value(t->fall[leg],f)!=ESP_OK ||
           mcpwm_generator_set_action_on_timer_event(t->gen[2*leg],
             MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,MCPWM_TIMER_EVENT_EMPTY,
               r?MCPWM_GEN_ACTION_LOW:MCPWM_GEN_ACTION_HIGH))!=ESP_OK) return fail(t);
    }
    t->programmed=*c;
    /* Force-low remains set, pads stay on GPIO, REQUEST stays low. */
    if(mcpwm_timer_start_stop(t->timer,MCPWM_TIMER_START_NO_STOP)!=ESP_OK) return fail(t);
    t->running=true;
    return true;
}
bool r5_pwm_init(bridge_backend_t *backend)
{
    if(backend) *backend=(bridge_backend_t){0};
    if(!cleanup(&hw)) return fail(&hw);
    if(!backend) return fail(&hw);
    memset(&hw,0,sizeof hw);
    /* DECISIONS 2026-10-03: 200 ns controller gap = 16 ticks at 80 MHz. */
    if(!bridge_plan_cycle(80000000,50000,200,0,&hw.programmed)) return fail(&hw);
    mcpwm_timer_config_t tc={.group_id=0,.clk_src=MCPWM_TIMER_CLK_SRC_DEFAULT,
      .resolution_hz=80000000,.count_mode=MCPWM_TIMER_COUNT_MODE_UP,.period_ticks=hw.programmed.period};
    if(mcpwm_new_timer(&tc,&hw.timer)!=ESP_OK) return fail(&hw);
    mcpwm_timer_event_callbacks_t cb={.on_stop=stopped};
    if(mcpwm_timer_register_event_callbacks(hw.timer,&cb,&hw)!=ESP_OK) return fail(&hw);
    for(unsigned leg=0;leg<2;++leg) {
        mcpwm_operator_config_t oc={.group_id=0};
        mcpwm_comparator_config_t cc={0};
        if(mcpwm_new_operator(&oc,&hw.op[leg])!=ESP_OK ||
           mcpwm_operator_connect_timer(hw.op[leg],hw.timer)!=ESP_OK ||
           mcpwm_new_comparator(hw.op[leg],&cc,&hw.rise[leg])!=ESP_OK ||
           mcpwm_new_comparator(hw.op[leg],&cc,&hw.fall[leg])!=ESP_OK) return fail(&hw);
        for(unsigned p=0;p<2;++p) {
            mcpwm_generator_config_t gc={.gen_gpio_num=pwm_pins[2*leg+p]};
            if(mcpwm_new_generator(hw.op[leg],&gc,&hw.gen[2*leg+p])!=ESP_OK) return fail(&hw);
            /* Generator creation reconnects the matrix; disconnect before any
             * inversion or counter setup. Do not grant permission to heat. */
            if(!restore_pads(&hw) ||
               mcpwm_generator_set_force_level(hw.gen[2*leg+p],0,true)!=ESP_OK) return fail(&hw);
        }
        if(mcpwm_generator_set_action_on_compare_event(hw.gen[2*leg],
             MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,hw.rise[leg],MCPWM_GEN_ACTION_HIGH))!=ESP_OK ||
           mcpwm_generator_set_action_on_compare_event(hw.gen[2*leg],
             MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,hw.fall[leg],MCPWM_GEN_ACTION_LOW))!=ESP_OK) return fail(&hw);
        mcpwm_dead_time_config_t dt={.posedge_delay_ticks=hw.programmed.dead_ticks};
        if(mcpwm_generator_set_dead_time(hw.gen[2*leg],hw.gen[2*leg],&dt)!=ESP_OK) return fail(&hw);
        dt=(mcpwm_dead_time_config_t){.negedge_delay_ticks=hw.programmed.dead_ticks,.flags.invert_output=true};
        if(mcpwm_generator_set_dead_time(hw.gen[2*leg],hw.gen[2*leg+1],&dt)!=ESP_OK) return fail(&hw);
    }
    if(mcpwm_timer_enable(hw.timer)!=ESP_OK) return fail(&hw);
    hw.enabled=true;
    hw.initialized=true;
    if(!apply(&hw,&hw.programmed)) return false; /* apply already restores. */
    *backend=(bridge_backend_t){apply,request,inhibit,&hw};
    return true;
}
