#include "driver/mcpwm_prelude.h"
#include "driver/gpio.h"
#include "sdk_stub.h"
#include <string.h>
struct obj {int pin,force,timer_action,compare_action;unsigned rise,fall;bool inverted;};
static struct obj objects[16];
static struct obj *route[40], *red_owner,*fed_owner;
static unsigned used,period,compare;
static int calls,fail_call,glitches,conflicts,level[40];
static bool hold[40];
#define CHECK() do {if (++calls==fail_call) return ESP_FAIL;} while(0)
void sdk_reset(void){memset(objects,0,sizeof(objects));memset(route,0,sizeof(route));memset(level,0,sizeof(level));memset(hold,0,sizeof(hold));used=0;calls=0;fail_call=0;glitches=0;conflicts=0;red_owner=fed_owner=0;}
void sdk_fail_at(int n){fail_call=n;}
int sdk_calls(void){return calls;}
int sdk_glitches(void){return glitches;}
int sdk_conflicts(void){return conflicts;}
unsigned sdk_rise(void){return red_owner?red_owner->rise:0;}
unsigned sdk_fall(void){return fed_owner?fed_owner->fall:0;}
unsigned sdk_period(void){return period;}
unsigned sdk_compare(void){return compare;}
int sdk_pin(int pin,unsigned phase){
 if(hold[pin] || !route[pin]) return level[pin];
 struct obj *g=route[pin];
 int raw=g->force;
 if(raw<0){
  unsigned on=g->rise,off=compare+g->fall;
  raw=phase>=on && phase<off ? g->timer_action:g->compare_action;
 }
 return raw ^ g->inverted;
}
static void observe(void){if(sdk_pin(4,0)||sdk_pin(5,0)) glitches++;}
static struct obj *make(void){struct obj *o=&objects[used++];o->force=0;return o;}
esp_err_t mcpwm_new_timer(const mcpwm_timer_config_t*c,mcpwm_timer_handle_t*h){CHECK();period=c->period_ticks;*h=make();return 0;}
esp_err_t mcpwm_new_operator(const mcpwm_operator_config_t*c,mcpwm_oper_handle_t*h){(void)c;CHECK();*h=make();return 0;}
esp_err_t mcpwm_operator_connect_timer(mcpwm_oper_handle_t o,mcpwm_timer_handle_t t){(void)o;(void)t;CHECK();return 0;}
esp_err_t mcpwm_new_comparator(mcpwm_oper_handle_t o,const mcpwm_comparator_config_t*c,mcpwm_cmpr_handle_t*h){(void)o;(void)c;CHECK();*h=make();return 0;}
esp_err_t mcpwm_comparator_set_compare_value(mcpwm_cmpr_handle_t c,uint32_t n){(void)c;CHECK();compare=n;return 0;}
esp_err_t mcpwm_new_generator(mcpwm_oper_handle_t o,const mcpwm_generator_config_t*c,mcpwm_gen_handle_t*h){(void)o;CHECK();*h=make();(*h)->pin=c->gen_gpio_num;route[c->gen_gpio_num]=*h;observe();return 0;}
esp_err_t mcpwm_generator_set_force_level(mcpwm_gen_handle_t g,int n,bool h){(void)h;CHECK();g->force=n;if(n>=0)observe();return 0;}
esp_err_t mcpwm_generator_set_action_on_timer_event(mcpwm_gen_handle_t g,action_t a){CHECK();g->timer_action=a.action;return 0;}
esp_err_t mcpwm_generator_set_action_on_compare_event(mcpwm_gen_handle_t g,action_t a){CHECK();g->compare_action=a.action;return 0;}
esp_err_t mcpwm_generator_set_dead_time(mcpwm_gen_handle_t in,mcpwm_gen_handle_t out,const mcpwm_dead_time_config_t*c){
 CHECK();
 if((c->posedge_delay_ticks && red_owner && red_owner!=in)||(c->negedge_delay_ticks && fed_owner && fed_owner!=in)){conflicts++;return ESP_FAIL;}
 if(c->posedge_delay_ticks)red_owner=in;else if(red_owner==in)red_owner=0;
 if(c->negedge_delay_ticks)fed_owner=in;else if(fed_owner==in)fed_owner=0;
 out->rise=c->posedge_delay_ticks;out->fall=c->negedge_delay_ticks;out->inverted=c->flags.invert_output;observe();return 0;
}
esp_err_t mcpwm_timer_set_period(mcpwm_timer_handle_t t,uint32_t n){(void)t;CHECK();period=n;return 0;}
esp_err_t mcpwm_timer_enable(mcpwm_timer_handle_t t){(void)t;CHECK();return 0;}
esp_err_t mcpwm_timer_disable(mcpwm_timer_handle_t t){(void)t;CHECK();return 0;}
esp_err_t mcpwm_timer_start_stop(mcpwm_timer_handle_t t,int n){(void)t;(void)n;CHECK();return 0;}
esp_err_t mcpwm_del_generator(mcpwm_gen_handle_t g){CHECK();if(red_owner==g)red_owner=0;if(fed_owner==g)fed_owner=0;if(route[g->pin]==g)route[g->pin]=0;return 0;}
esp_err_t mcpwm_del_comparator(mcpwm_cmpr_handle_t c){(void)c;CHECK();return 0;}
esp_err_t mcpwm_del_operator(mcpwm_oper_handle_t o){(void)o;CHECK();return 0;}
esp_err_t mcpwm_del_timer(mcpwm_timer_handle_t t){(void)t;CHECK();return 0;}
esp_err_t gpio_reset_pin(int p){CHECK();route[p]=0;level[p]=0;return 0;}
esp_err_t gpio_set_level(int p,int n){CHECK();level[p]=n;return 0;}
esp_err_t gpio_set_direction(int p,int n){(void)p;(void)n;CHECK();return 0;}
esp_err_t gpio_hold_en(int p){CHECK();hold[p]=true;return 0;}
esp_err_t gpio_hold_dis(int p){CHECK();hold[p]=false;observe();return 0;}
