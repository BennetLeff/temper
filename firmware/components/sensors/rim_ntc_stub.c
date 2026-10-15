/**
 * @file rim_ntc_stub.c
 * @brief TODO(hardware) fail-safe stand-in for read_rim_ntc_temperature().
 *
 * The rim NTC driver is being written on a sibling branch
 * (sensor-c1-rim-ntc). When it lands, delete this file and its line in
 * firmware/main/CMakeLists.txt; nothing else refers to it. Host builds never
 * compile it (the host suites stub the symbol per test).
 *
 * Only pan_control_step() calls this, i.e. only while the C1 loop is trying
 * to heat. The C1 estimator uses the rim reading as its leak sink, so a NAN
 * would poison its state rather than stop it. The stub therefore latches
 * safe mode through trigger_hardware_shutdown() (pwm_disable_all() and
 * power_set_level(0)) on its first call and returns NAN, never a plausible
 * temperature.
 */

#include <math.h>
#include <stdbool.h>

#include "esp_log.h"

extern void trigger_hardware_shutdown(void);

float read_rim_ntc_temperature(void)
{
    static bool s_latched;
    if (!s_latched) {
        s_latched = true;
        ESP_LOGE("rim_ntc", "TODO(hardware): no rim NTC driver; latching safe mode (coil off)");
        trigger_hardware_shutdown();
    }
    return NAN;
}
