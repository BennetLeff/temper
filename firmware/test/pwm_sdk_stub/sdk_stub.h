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
