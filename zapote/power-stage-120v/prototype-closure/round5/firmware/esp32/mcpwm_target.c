#include "mcpwm_target.h"
#include "pins.h"
#include "driver/gpio.h"
#include "driver/mcpwm_prelude.h"
#include "esp_rom_gpio.h"
#include "esp_timer.h"
#include "soc/mcpwm_struct.h"
#include "soc/gpio_sig_map.h"
#include "soc/mcpwm_periph.h"
#include "hal/mcpwm_ll.h"
#include "soc/gpio_struct.h"
#include "mcpwm_readback.h"
#include <string.h>
/* This standalone image exclusively owns MCPWM group 0. Do not mix another
 * driver/ISR owner into the group-wide shadow transaction. */
typedef struct {
    mcpwm_timer_handle_t timer;
    mcpwm_oper_handle_t op[2];
    mcpwm_cmpr_handle_t rise[2],fall[2];
    mcpwm_gen_handle_t gen[4];
    bridge_cycle_t programmed;
    bool initialized,running,request,commissioned,prepared_once,connected;
} target_t;
static target_t hw;
static const int pins[4]={R5_PWM_AH,R5_PWM_AL,R5_PWM_BH,R5_PWM_BL};
static void inhibit(void *context)
{
    target_t *t=context;
    (void)gpio_set_level(R5_REQUEST,0);t->request=false;
    t->connected=false;
    /* Set GPIO latch FIRST then replace matrix signal with GPIO output.
       This disconnect is downstream of both MCPWM deadtime invert paths.
       No force-low-before-inversion assumption; works before handle creation. */
    for(unsigned i=0;i<4;++i) {
        (void)gpio_set_level(pins[i],0);
        esp_rom_gpio_connect_out_signal(pins[i],SIG_GPIO_OUT_IDX,false,false);
        (void)gpio_set_direction(pins[i],GPIO_MODE_OUTPUT);
    }
}
static bool request(void *context,bool value)
{
    target_t *t=context;
    if(value&&(!t->commissioned||!t->running||!t->connected)) { inhibit(t);return false; }
    if(gpio_set_level(R5_REQUEST,value)!=ESP_OK) { inhibit(t);return false; }
    t->request=value;return true;
}
static bool wait_commit(void)
{
    int64_t until=esp_timer_get_time()+1000;
    do {
        if(!(MCPWM0.operators[0].gen_stmp_cfg.val&0x300u)&&
           !(MCPWM0.operators[1].gen_stmp_cfg.val&0x300u)) return true;
    } while(esp_timer_get_time()<until);
    return false;
}
static bool apply(void *context,const bridge_cycle_t *c)
{
    target_t *t=context;
    if(!c||!t->initialized||c->period!=t->programmed.period||
       c->dead_ticks!=t->programmed.dead_ticks) goto fail;
    uint32_t half=c->period/2;
    uint32_t shift=(c->pulse[2].rise+c->period-c->dead_ticks)%c->period;
    if(shift>half||c->pulse[0].rise!=c->dead_ticks||
       c->pulse[1].rise!=half+c->dead_ticks||
       c->pulse[3].rise!=(shift+half+c->dead_ticks)%c->period) goto fail;
    for(unsigned i=0;i<4;++i) if(c->pulse[i].width!=half-c->dead_ticks) goto fail;
    if(t->running&&!wait_commit()) goto fail;
    /* One global gate holds ALL active shadow loads even if TEZ occurs between
       API writes. No timing budget / interrupt-latency assumption is needed.
       Every shadow loads on the same next common TEZ after the gate reopens. */
    MCPWM0.update_cfg.global_up_en=0;
    __asm__ __volatile__("memw" ::: "memory");
    for(unsigned leg=0;leg<2;++leg) {
        uint32_t rise=leg?shift:0, fall=(rise+half)%c->period;
        if(mcpwm_comparator_set_compare_value(t->rise[leg],rise)!=ESP_OK||
           mcpwm_comparator_set_compare_value(t->fall[leg],fall)!=ESP_OK||
           mcpwm_generator_set_action_on_timer_event(t->gen[2*leg],
             MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,MCPWM_TIMER_EVENT_EMPTY,
               rise==0?MCPWM_GEN_ACTION_HIGH:MCPWM_GEN_ACTION_LOW))!=ESP_OK) goto abort;
    }
    __asm__ __volatile__("memw" ::: "memory");
    MCPWM0.update_cfg.global_up_en=1;
    if(!t->running) {
        /* Inhibited initial setup only. Subsequent changes NEVER stop timer. */
        mcpwm_ll_group_flush_shadow(&MCPWM0);
        if(mcpwm_timer_start_stop(t->timer,MCPWM_TIMER_START_NO_STOP)!=ESP_OK) goto fail;
        t->running=true;
    }
    if(!wait_commit()) goto fail;
    t->programmed=*c;return true;
abort:
    inhibit(t); /* Gate permission removed BEFORE releasing incomplete shadow. */
    MCPWM0.update_cfg.global_up_en=1;
fail: inhibit(t);return false;
}
bool r5_pwm_prepare_capture(bool verified)
{
    if(!verified||!hw.initialized||!hw.running||hw.request||hw.prepared_once||
       gpio_get_level(R5_REQUEST)||hw.programmed.pulse[2].rise!=hw.programmed.dead_ticks) return false;
    /* The initial differential phase is zero and the external request is low.
       Connect logic signals for independent capture, not power-stage permission.
       A fault's later inhibit cannot be undone through this boot-only entry. */
    for(unsigned i=0;i<4;i++) esp_rom_gpio_connect_out_signal(pins[i],
        mcpwm_periph_signals.groups[0].operators[i/2].generators[i%2].pwm_sig,false,false);
    hw.prepared_once=true;hw.connected=true;return true;
}
bool r5_pwm_init(bridge_backend_t *backend,bool commissioned)
{
    if(!backend||hw.timer) return false; /* Never clear a boot/runtime fault by re-init. */
    memset(&hw,0,sizeof hw);hw.commissioned=commissioned;
    gpio_config_t io={.pin_bit_mask=1ULL<<R5_REQUEST,.mode=GPIO_MODE_OUTPUT,.pull_down_en=GPIO_PULLDOWN_ENABLE};
    if(gpio_config(&io)!=ESP_OK) return false;
    inhibit(&hw);
    if(!bridge_plan_cycle(80000000,50000,125,0,&hw.programmed)) return false;
    mcpwm_timer_config_t tc={.group_id=0,.clk_src=MCPWM_TIMER_CLK_SRC_DEFAULT,
      .resolution_hz=80000000,.count_mode=MCPWM_TIMER_COUNT_MODE_UP,.period_ticks=hw.programmed.period};
    if(mcpwm_new_timer(&tc,&hw.timer)!=ESP_OK) goto fail;
    for(unsigned leg=0;leg<2;++leg) {
        mcpwm_operator_config_t oc={.group_id=0,.flags.update_gen_action_on_tez=true};
        mcpwm_comparator_config_t cc={.flags.update_cmp_on_tez=true};
        if(mcpwm_new_operator(&oc,&hw.op[leg])!=ESP_OK||
           mcpwm_operator_connect_timer(hw.op[leg],hw.timer)!=ESP_OK||
           mcpwm_new_comparator(hw.op[leg],&cc,&hw.rise[leg])!=ESP_OK||
           mcpwm_new_comparator(hw.op[leg],&cc,&hw.fall[leg])!=ESP_OK) goto fail;
        for(unsigned p=0;p<2;++p) {
            mcpwm_generator_config_t gc={.gen_gpio_num=pins[2*leg+p]};
            if(mcpwm_new_generator(hw.op[leg],&gc,&hw.gen[2*leg+p])!=ESP_OK) goto fail;
            inhibit(&hw); /* Disconnect before any deadtime inversion exists. */
        }
        if(mcpwm_generator_set_action_on_compare_event(hw.gen[2*leg],
             MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,hw.rise[leg],MCPWM_GEN_ACTION_HIGH))!=ESP_OK||
           mcpwm_generator_set_action_on_compare_event(hw.gen[2*leg],
             MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,hw.fall[leg],MCPWM_GEN_ACTION_LOW))!=ESP_OK) goto fail;
        mcpwm_dead_time_config_t dt={.posedge_delay_ticks=hw.programmed.dead_ticks};
        if(mcpwm_generator_set_dead_time(hw.gen[2*leg],hw.gen[2*leg],&dt)!=ESP_OK) goto fail;
        dt=(mcpwm_dead_time_config_t){.negedge_delay_ticks=hw.programmed.dead_ticks,.flags.invert_output=true};
        if(mcpwm_generator_set_dead_time(hw.gen[2*leg],hw.gen[2*leg+1],&dt)!=ESP_OK) goto fail;
    }
    inhibit(&hw);
    if(mcpwm_timer_enable(hw.timer)!=ESP_OK) goto fail;
    hw.initialized=true;*backend=(bridge_backend_t){apply,request,inhibit,&hw};
    return apply(&hw,&hw.programmed);
fail: inhibit(&hw);return false;
}
bool r5_pwm_readback(bridge_feedback_t *f)
{
    static uint32_t serial;
    if(!f) return false;
    memset(f,0,sizeof *f);
    if(!hw.initialized||!hw.running||!SYSTEM.perip_clk_en0.pwm0_clk_en||!wait_commit()) return false;
    f->kind=BRIDGE_FEEDBACK_ONCHIP_REGISTER;
    f->onchip.coherent=r5_mcpwm_register_cycle(&MCPWM0,&f->onchip.programmed_cycle,&f->onchip.timer_hz);
    uint32_t initial=MCPWM0.timer[0].timer_status.timer_value;
    int64_t until=esp_timer_get_time()+10;
    do {
        if(MCPWM0.timer[0].timer_status.timer_value!=initial) { f->onchip.timer_advancing=true;break; }
    } while(esp_timer_get_time()<until);
    f->onchip.outputs_connected=hw.connected;
    for(unsigned i=0;i<4;i++) {
        uint32_t sig=mcpwm_periph_signals.groups[0].operators[i/2].generators[i%2].pwm_sig;
        if(!(GPIO.enable&(1u<<pins[i]))||GPIO.func_out_sel_cfg[pins[i]].func_sel!=sig||GPIO.func_out_sel_cfg[pins[i]].inv_sel||
           GPIO.func_out_sel_cfg[pins[i]].oen_inv_sel) f->onchip.outputs_connected=false;
    }
    f->sampled_us=(uint32_t)esp_timer_get_time();f->serial=++serial;
    return f->onchip.coherent&&f->onchip.timer_advancing&&f->onchip.outputs_connected;
}

bool r5_pwm_requested(void) { return hw.request&&hw.connected&&hw.running&&hw.commissioned; }
