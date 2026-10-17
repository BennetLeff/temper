/* Host fault oracle, not a model of MCPWM waveform timing. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../esp32/mcpwm_target.c"
struct obj { int pin, live; struct obj *parent; };
static struct obj pool[64];
static int used,calls,fail_at,mode[40],level[40],up[40],down[40],route[40];
static int no_stop_event;
static const char *persistent;
static mcpwm_timer_event_callbacks_t callbacks;
static void *callback_ctx;
static const char *names[2048];
#define CHECK() do { names[++calls]=__func__; if(calls==fail_at || (persistent && !strcmp(persistent,__func__))) return ESP_FAIL; } while(0)
static struct obj *make(struct obj *parent) { assert(used<64); pool[used]=(struct obj){.pin=-1,.live=1,.parent=parent}; return &pool[used++]; }
static void valid(struct obj *o) { assert(o && o->live); }
static void destroy(struct obj *o) { valid(o); for(int i=0;i<used;i++) assert(!pool[i].live || pool[i].parent!=o); o->live=0; }
/* Pinned ESP-IDF e0991facf5ecb362af6aac1fae972139eb38d2e4:
 * components/esp_driver_gpio/src/gpio.c:436-448; reset disables output,
 * enables pull-up, disables pull-down. Deletion calls it (mcpwm_gen.c:114-124).
 * https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_gpio/src/gpio.c#L436-L448
 */
static void reset_pin(int p) { mode[p]=GPIO_MODE_DISABLE; up[p]=1; down[p]=0; route[p]=0; }
esp_err_t gpio_reset_pin(int p) { CHECK(); assert(p!=R5_REQUEST); reset_pin(p); return ESP_OK; }
esp_err_t gpio_set_level(int p,int v) { CHECK(); assert(v==0); level[p]=v; return ESP_OK; }
esp_err_t gpio_set_direction(int p,int v) { CHECK(); mode[p]=v; return ESP_OK; }
esp_err_t gpio_pullup_dis(int p) { CHECK(); up[p]=0; return ESP_OK; }
esp_err_t gpio_pulldown_en(int p) { CHECK(); down[p]=1; return ESP_OK; }
esp_err_t gpio_config(const gpio_config_t *c) { CHECK(); for(int p=0;p<40;p++) if(c->pin_bit_mask&(1ULL<<p)) {mode[p]=c->mode;up[p]=c->pull_up_en;down[p]=c->pull_down_en;route[p]=0;} return ESP_OK; }
esp_err_t mcpwm_new_timer(const mcpwm_timer_config_t*c,mcpwm_timer_handle_t*h) { (void)c; CHECK(); *h=make(0); return 0; }
esp_err_t mcpwm_new_operator(const mcpwm_operator_config_t*c,mcpwm_oper_handle_t*h) { (void)c; CHECK(); *h=make(0); return 0; }
esp_err_t mcpwm_operator_connect_timer(mcpwm_oper_handle_t o,mcpwm_timer_handle_t t) { CHECK();valid(o);valid(t);o->parent=t;return 0; }
esp_err_t mcpwm_new_comparator(mcpwm_oper_handle_t o,const mcpwm_comparator_config_t*c,mcpwm_cmpr_handle_t*h) {(void)c;CHECK();valid(o);*h=make(o);return 0;}
esp_err_t mcpwm_new_generator(mcpwm_oper_handle_t o,const mcpwm_generator_config_t*c,mcpwm_gen_handle_t*h) {CHECK();valid(o);*h=make(o);(*h)->pin=c->gen_gpio_num;mode[(*h)->pin]=GPIO_MODE_OUTPUT;route[(*h)->pin]=1;return 0;}
esp_err_t mcpwm_generator_set_force_level(mcpwm_gen_handle_t g,int n,bool hold) {(void)hold;CHECK();valid(g);assert(n==0);return 0;}
esp_err_t mcpwm_generator_set_dead_time(mcpwm_gen_handle_t g,mcpwm_gen_handle_t h,const mcpwm_dead_time_config_t*c) {(void)c;CHECK();valid(g);valid(h);return 0;}
esp_err_t mcpwm_generator_set_action_on_timer_event(mcpwm_gen_handle_t g,action_t a) {(void)a;CHECK();valid(g);return 0;}
esp_err_t mcpwm_generator_set_action_on_compare_event(mcpwm_gen_handle_t g,action_t a) {(void)a;CHECK();valid(g);return 0;}
esp_err_t mcpwm_comparator_set_compare_value(mcpwm_cmpr_handle_t g,uint32_t v) {CHECK();valid(g);assert(v<1600);return 0;}
esp_err_t mcpwm_timer_register_event_callbacks(mcpwm_timer_handle_t t,const mcpwm_timer_event_callbacks_t*c,void*ctx) {CHECK();valid(t);callbacks=*c;callback_ctx=ctx;return 0;}
esp_err_t mcpwm_timer_enable(mcpwm_timer_handle_t t) {CHECK();valid(t);return 0;}
esp_err_t mcpwm_timer_disable(mcpwm_timer_handle_t t) {CHECK();valid(t);return 0;}
esp_err_t mcpwm_timer_start_stop(mcpwm_timer_handle_t t,int cmd) {CHECK();valid(t);if(cmd==MCPWM_TIMER_STOP_EMPTY && !no_stop_event) callbacks.on_stop(t,0,callback_ctx);if(cmd==MCPWM_TIMER_START_NO_STOP) {assert(!route[R5_PWM_AH]&&!route[R5_PWM_AL]&&!route[R5_PWM_BH]&&!route[R5_PWM_BL]);assert(!level[R5_REQUEST]);}return 0;}
esp_err_t mcpwm_del_generator(mcpwm_gen_handle_t g) {CHECK();reset_pin(g->pin);destroy(g);return 0;}
esp_err_t mcpwm_del_comparator(mcpwm_cmpr_handle_t g) {CHECK();destroy(g);return 0;}
esp_err_t mcpwm_del_operator(mcpwm_oper_handle_t g) {CHECK();destroy(g);return 0;}
esp_err_t mcpwm_del_timer(mcpwm_timer_handle_t g) {CHECK();destroy(g);return 0;}
int64_t esp_timer_get_time(void) {static int64_t now;return now+=100;}
static void fresh(void) {
 memset(&hw,0,sizeof hw);memset(pool,0,sizeof pool);memset(route,0,sizeof route);
 for(int p=0;p<40;p++) {mode[p]=GPIO_MODE_DISABLE;level[p]=1;up[p]=1;down[p]=0;}
 used=calls=fail_at=no_stop_event=0;persistent=0;
}
static void pads(void) {
 const int pins[]={R5_REQUEST,R5_PWM_AH,R5_PWM_AL,R5_PWM_BH,R5_PWM_BL};
 for(unsigned i=0;i<sizeof pins/sizeof pins[0];i++) {int p=pins[i];assert(mode[p]==GPIO_MODE_OUTPUT);assert(level[p]==0);assert(!up[p]);assert(down[p]);assert(!route[p]);}
}
static bridge_cycle_t cycle(float phase) {bridge_cycle_t c;assert(bridge_plan_cycle(80000000,50000,200,phase,&c));return c;}
static void reset_calls(void) {calls=fail_at=0;}
int main(void) {
 bridge_backend_t b;
 fresh();assert(r5_pwm_init(&b));pads();int init_calls=calls;
 for(int n=1;n<=init_calls;n++) {fresh();fail_at=n;assert(!r5_pwm_init(&b));pads();printf("init %d PASS\n",n);}
 fresh();assert(r5_pwm_init(&b));reset_calls();bridge_cycle_t c=cycle(1);assert(b.apply_cycle(b.context,&c));pads();int update_calls=calls;
 for(int n=1;n<=update_calls;n++) {fresh();assert(r5_pwm_init(&b));reset_calls();fail_at=n;c=cycle(1);assert(!b.apply_cycle(b.context,&c));pads();printf("update %d PASS\n",n);}
 fresh();assert(r5_pwm_init(&b));reset_calls();assert(!b.apply_cycle(b.context,0));pads();int cleanup_calls=calls;
 for(int n=1;n<=cleanup_calls;n++) {fresh();assert(r5_pwm_init(&b));reset_calls();fail_at=n;assert(!b.apply_cycle(b.context,0));pads();fail_at=0;assert(r5_pwm_init(&b));pads();printf("cleanup %d PASS\n",n);}
 fresh();assert(r5_pwm_init(&b));reset_calls();assert(b.set_request(b.context,false));int request_calls=calls;
 for(int n=1;n<=request_calls;n++) {fresh();assert(r5_pwm_init(&b));reset_calls();fail_at=n;assert(!b.set_request(b.context,false));pads();}
 fresh();assert(r5_pwm_init(&b));reset_calls();b.inhibit(b.context);int inhibit_calls=calls;
 for(int n=1;n<=inhibit_calls;n++) {fresh();assert(r5_pwm_init(&b));reset_calls();fail_at=n;b.inhibit(b.context);pads();assert(!b.apply_cycle(b.context,&hw.programmed));}
 fresh();assert(r5_pwm_init(&b));c=cycle(1);assert(b.apply_cycle(b.context,&c));pads();
 for(unsigned phase=0;phase<100;phase++) {bridge_cycle_t rejected;assert(!bridge_plan_cycle(80000000,50000,200,phase/100.0f,&rejected));}
 c.pulse[2].rise--;c.pulse[3].rise--;assert(!b.apply_cycle(b.context,&c));pads();
 fresh();assert(r5_pwm_init(&b));c=cycle(1);
 /* One timer tick above 180 degrees must reject, including modulo aliases. */
 c.pulse[2].rise++;c.pulse[3].rise++;assert(!b.apply_cycle(b.context,&c));pads();
 fresh();assert(r5_pwm_init(&b));c=cycle(1);c.pulse[2].rise+=c.period;assert(!b.apply_cycle(b.context,&c));pads();
 fresh();assert(!r5_pwm_init(0));pads();
 fresh();assert(r5_pwm_init(&b));no_stop_event=1;assert(!b.apply_cycle(b.context,NULL));pads();
 fresh();assert(r5_pwm_init(&b));assert(!b.set_request(b.context,true));pads();
 const char *gpio_failures[]={"gpio_config","gpio_set_level","gpio_reset_pin","gpio_set_direction","gpio_pullup_dis","gpio_pulldown_en"};
 for(unsigned i=0;i<sizeof gpio_failures/sizeof gpio_failures[0];i++) {
  fresh();assert(r5_pwm_init(&b));persistent=gpio_failures[i];assert(!b.set_request(b.context,false));persistent=0;
  assert(!b.apply_cycle(b.context,&hw.programmed));pads();
  fresh();assert(r5_pwm_init(&b));persistent=gpio_failures[i];b.inhibit(b.context);persistent=0;
  assert(!b.apply_cycle(b.context,&hw.programmed));pads();
 }
 printf("request/inhibit: %d/%d single-failure positions PASS\n",request_calls,inhibit_calls);
 printf("PASS: %d init, %d update, %d cleanup fault positions; phase endpoints/aliases, NULL, timeout, request rejection, persistent GPIO errors and void-inhibit error latch\n",init_calls,update_calls,cleanup_calls);
}
