#include "diagnostic_lockout.h"

#include "power_entry_esp32_adapter.h"
#include "temper_pins.h"

bool diagnostic_lockout_apply(diagnostic_drive_pin_t drive, void *context) {
    if (drive == 0) return false;

    /* Attempt every cut even if an earlier GPIO operation failed. Repeating
     * this operation cannot grant a power request or create a PWM edge. */
    bool ok = true;
    if (!drive(context, PE_ESP_GPIO_STOP_N, false)) ok = false;
    if (!drive(context, PIN_RUNAWAY_CUT, true)) ok = false;
    if (!drive(context, PIN_PWM_HI, false)) ok = false;
    if (!drive(context, PIN_PWM_LO, false)) ok = false;
    if (!drive(context, PIN_RELAY_BYPASS, false)) ok = false;
    return ok;
}
