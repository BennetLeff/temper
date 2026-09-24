#include "diagnostic_lockout.h"
#include "power_entry_esp32_service.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <stdlib.h>

#if !defined(TEMPER_REV38_TEST_IMAGE) || TEMPER_REV38_TEST_IMAGE != 1
#error "This entry point is only for the Rev38 target test image"
#endif

static const char *TAG = "rev38_target_test";

static bool drive_pin(void *context, int pin, bool high) {
    (void)context;
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

void app_main(void) {
    /* Hold both power stages and the bypass relay off before touching the
     * shared Rev38 GPIO/UART/I2C owner. Hardware pull-downs own pre-boot. */
    if (!diagnostic_lockout_apply(drive_pin, NULL)) abort();

    /* This runs the real target binding and expander boot writes. All source
     * timing qualifications are zero, so the task stops without WDI, PERMIT,
     * or START authorization. A false result is the expected test image. */
    if (pe_esp32_source_service_start()) {
        ESP_LOGE(TAG, "Unexpected authorization in Rev38 test image");
        abort();
    }

    ESP_LOGW(TAG, "Rev38 target interface initialized; source locked out");
    for (;;) {
        if (!diagnostic_lockout_apply(drive_pin, NULL)) abort();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
