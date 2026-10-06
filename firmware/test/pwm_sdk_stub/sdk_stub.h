#pragma once
void sdk_reset(void);
void sdk_fail_at(int call);
int sdk_calls(void);
int sdk_pin(int pin, unsigned phase);
int sdk_glitches(void);
int sdk_conflicts(void);
unsigned sdk_rise(void);
unsigned sdk_fall(void);
unsigned sdk_period(void);
unsigned sdk_compare(void);
int sdk_mode(int pin);
int sdk_pullup(int pin);
int sdk_pulldown(int pin);
int sdk_routed(int pin);
int sdk_held(int pin);
void sdk_fail_api(const char *name);
