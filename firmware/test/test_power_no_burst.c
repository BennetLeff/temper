#include "low_temp_control.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static uint8_t requested;
uint32_t get_time_ms(void)
{
    return UINT32_MAX;
}
float pid_update(float setpoint, float measurement)
{
    (void)setpoint;
    (void)measurement;
    return 100;
}
void power_set_level(uint8_t percent)
{
    requested = percent;
}
int main(void){
    low_temp_init();
    low_temp_start(50);
    requested = 100;
    assert(!low_temp_update(20));
    assert(requested == 0);
    puts("ESP-platform legacy burst path inhibited");
    return 0;
}
