#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define MCPWM_TIMER_CLK_SRC_DEFAULT 0
#define MCPWM_TIMER_COUNT_MODE_UP 0
#define MCPWM_TIMER_DIRECTION_UP 0
#define MCPWM_TIMER_EVENT_EMPTY 0
#define MCPWM_GEN_ACTION_HIGH 1
#define MCPWM_GEN_ACTION_LOW 0
#define MCPWM_TIMER_START_NO_STOP 1
#define MCPWM_TIMER_STOP_FULL 0
typedef struct obj *mcpwm_timer_handle_t;
typedef struct obj *mcpwm_oper_handle_t;
typedef struct obj *mcpwm_cmpr_handle_t;
typedef struct obj *mcpwm_gen_handle_t;
typedef struct {int group_id,clk_src,count_mode;uint32_t resolution_hz,period_ticks;} mcpwm_timer_config_t;
typedef struct {int group_id;} mcpwm_operator_config_t;
typedef struct {struct {bool update_cmp_on_tez;} flags;} mcpwm_comparator_config_t;
typedef struct {int gen_gpio_num;} mcpwm_generator_config_t;
typedef struct {uint32_t posedge_delay_ticks,negedge_delay_ticks;struct {bool invert_output;} flags;} mcpwm_dead_time_config_t;
typedef struct {int action;} action_t;
#define MCPWM_GEN_TIMER_EVENT_ACTION(d,e,a) ((action_t){a})
#define MCPWM_GEN_COMPARE_EVENT_ACTION(d,c,a) ((action_t){a})
esp_err_t mcpwm_new_timer(const mcpwm_timer_config_t*,mcpwm_timer_handle_t*);
esp_err_t mcpwm_new_operator(const mcpwm_operator_config_t*,mcpwm_oper_handle_t*);
esp_err_t mcpwm_operator_connect_timer(mcpwm_oper_handle_t,mcpwm_timer_handle_t);
esp_err_t mcpwm_new_comparator(mcpwm_oper_handle_t,const mcpwm_comparator_config_t*,mcpwm_cmpr_handle_t*);
esp_err_t mcpwm_comparator_set_compare_value(mcpwm_cmpr_handle_t,uint32_t);
esp_err_t mcpwm_new_generator(mcpwm_oper_handle_t,const mcpwm_generator_config_t*,mcpwm_gen_handle_t*);
esp_err_t mcpwm_generator_set_force_level(mcpwm_gen_handle_t,int,bool);
esp_err_t mcpwm_generator_set_action_on_timer_event(mcpwm_gen_handle_t,action_t);
esp_err_t mcpwm_generator_set_action_on_compare_event(mcpwm_gen_handle_t,action_t);
esp_err_t mcpwm_generator_set_dead_time(mcpwm_gen_handle_t,mcpwm_gen_handle_t,const mcpwm_dead_time_config_t*);
esp_err_t mcpwm_timer_set_period(mcpwm_timer_handle_t,uint32_t);
esp_err_t mcpwm_timer_enable(mcpwm_timer_handle_t);
esp_err_t mcpwm_timer_disable(mcpwm_timer_handle_t);
esp_err_t mcpwm_timer_start_stop(mcpwm_timer_handle_t,int);
esp_err_t mcpwm_del_generator(mcpwm_gen_handle_t);
esp_err_t mcpwm_del_comparator(mcpwm_cmpr_handle_t);
esp_err_t mcpwm_del_operator(mcpwm_oper_handle_t);
esp_err_t mcpwm_del_timer(mcpwm_timer_handle_t);
#define IRAM_ATTR
#define MCPWM_TIMER_STOP_EMPTY 2
typedef struct { int unused; } mcpwm_timer_event_data_t;
typedef struct { bool (*on_stop)(mcpwm_timer_handle_t,const mcpwm_timer_event_data_t*,void*); } mcpwm_timer_event_callbacks_t;
esp_err_t mcpwm_timer_register_event_callbacks(mcpwm_timer_handle_t,const mcpwm_timer_event_callbacks_t*,void*);
