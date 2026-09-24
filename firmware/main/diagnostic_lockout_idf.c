#include "diagnostic_lockout.h"
#include "state_machine.h"

#include <stdlib.h>

#if !defined(TEMPER_DIAGNOSTIC_LOCKOUT) || TEMPER_DIAGNOSTIC_LOCKOUT != 1
#error "This entry point is only for the diagnostic lockout image"
#endif

#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "diagnostic_lockout";
/* Keep the actual cooker core in the link so diagnostic hooks resolve its
 * production interface. This pointer is read but never invoked. */
static bool (*volatile cooker_core_link_anchor)(void) = state_machine_update;

static bool drive_pin(void *context, int pin, bool high) {
    (void)context;
    /* The output latch is loaded before direction, including on the first
     * call after reset. External hardware must hold the pre-boot defaults. */
    if (gpio_set_level((gpio_num_t)pin, high ? 1 : 0) != ESP_OK) return false;
    gpio_config_t config = {
        .pin_bit_mask = 1ULL << pin,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&config) == ESP_OK;
}

void diagnostic_lockout_reject_power_request(void) {
    (void)diagnostic_lockout_apply(drive_pin, NULL);
    ESP_LOGE(TAG, "Unexpected cooker power request in diagnostic image");
    abort();
}

void app_main(void) {
    /* No state-machine, safety watchdog, PWM, or Rev38 source task runs in
     * this image. In particular watchdog_hardware_init() clears the cut pin
     * and cannot be called on this path. */
    if (cooker_core_link_anchor == NULL) abort();
    if (!diagnostic_lockout_apply(drive_pin, NULL)) {
        ESP_LOGE(TAG, "Unable to establish all diagnostic cut outputs");
        abort();
    }
    ESP_LOGW(TAG, "DIAGNOSTIC LOCKOUT IMAGE: no power authorization");
    for (;;) {
        /* Reassert the known safe outputs; never feed either watchdog. */
        if (!diagnostic_lockout_apply(drive_pin, NULL)) abort();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
