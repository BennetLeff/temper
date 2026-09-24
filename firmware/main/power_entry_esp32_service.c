#include "power_entry_esp32_service.h"

#include "power_entry_esp32_idf.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* These are zero until the selected board and IDF target establish the
 * worst-case sample-to-edge/frame times, protocol windows, UART final-bit
 * completion, reset feed tail, and independent monitor progress owner. A
 * nonzero guess here could release STOP before those constraints are proved. */
enum {
    PE_SAMPLE_TO_START_END_MS = 0,
    PE_SAMPLE_TO_WDI_MS = 0,
    PE_SAMPLE_TO_CONTROL_PIN_MS = 0,
    PE_MAX_BYTE_GAP_MS = 0,
    PE_PREPARE_WINDOW_MS = 0,
    PE_START_WINDOW_MS = 0,
    PE_WATCHDOG_WINDOW_MS = 0,
    PE_UART_FRAME_END_QUALIFIED = 0,
    PE_RESET_FEED_TAIL_QUALIFIED = 0,
    PE_LOCAL_PROGRESS_QUALIFIED = 0,
    PE_TASK_STACK_BYTES = 4096,
    PE_TASK_PRIORITY = configMAX_PRIORITIES - 1,
};

static const char *TAG = "pe_source";
static pe_esp32_adapter_t s_adapter;
static pe_source_runtime_t s_runtime;
static TaskHandle_t s_source_task;
static TaskHandle_t s_boot_waiter;
static bool s_runtime_armed;
static uint32_t s_control_epoch;
static uint32_t s_monitor_epoch;

void pe_esp32_source_service_control_progress(void) {
    (void)__atomic_add_fetch(&s_control_epoch, 1u, __ATOMIC_RELEASE);
}

void pe_esp32_source_service_monitor_progress(void) {
    (void)__atomic_add_fetch(&s_monitor_epoch, 1u, __ATOMIC_RELEASE);
}

static bool assert_stop_before_task(void) {
    /* The board's external pull-down holds STOP before code executes. Load
     * the output latch low before changing direction here as well. */
    if (gpio_set_level((gpio_num_t)PE_ESP_GPIO_STOP_N, 0) != ESP_OK) return false;
    gpio_config_t config = {
        .pin_bit_mask = 1ULL << PE_ESP_GPIO_STOP_N,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&config) == ESP_OK;
}

static void stop_forever(void) {
    pe_esp32_adapter_force_stop(&s_adapter);
    for (;;) vTaskDelay(portMAX_DELAY);
}

static void source_task(void *unused) {
    (void)unused;
    bool adapter_ready = pe_esp32_idf_boot(&s_adapter);
    const bool timing_qualified = PE_SAMPLE_TO_START_END_MS > 0 &&
        PE_SAMPLE_TO_WDI_MS > 0 && PE_SAMPLE_TO_CONTROL_PIN_MS > 0 &&
        PE_MAX_BYTE_GAP_MS > 0 && PE_PREPARE_WINDOW_MS > 0 &&
        PE_START_WINDOW_MS > 0 && PE_WATCHDOG_WINDOW_MS > 0 &&
        PE_UART_FRAME_END_QUALIFIED && PE_RESET_FEED_TAIL_QUALIFIED &&
        PE_LOCAL_PROGRESS_QUALIFIED;

    if (adapter_ready && timing_qualified) {
        pe_source_runtime_io_t io = pe_esp32_adapter_runtime_io(
            &s_adapter, PE_SAMPLE_TO_START_END_MS, PE_SAMPLE_TO_WDI_MS,
            PE_SAMPLE_TO_CONTROL_PIN_MS);
        pe_source_config_t config = {
            .prepare_window_ms = PE_PREPARE_WINDOW_MS,
            .start_window_ms = PE_START_WINDOW_MS,
            .watchdog_window_ms = PE_WATCHDOG_WINDOW_MS,
        };
        s_runtime_armed = pe_source_runtime_boot(&s_runtime, io, config,
                                                  PE_MAX_BYTE_GAP_MS);
    }
    xTaskNotifyGive(s_boot_waiter);

    if (!s_runtime_armed) {
        ESP_LOGE(TAG, "Rev38 source locked out: target timing or boot open");
        stop_forever();
    }

    for (;;) {
        uint32_t control = __atomic_load_n(&s_control_epoch, __ATOMIC_ACQUIRE);
        uint32_t monitor = __atomic_load_n(&s_monitor_epoch, __ATOMIC_ACQUIRE);
        pe_source_runtime_local_progress(&s_runtime, control, monitor);
        if (s_runtime.io_fault) stop_forever();
        uint8_t byte;
        int received;
        while ((received = pe_esp32_idf_poll_byte(&byte)) > 0) {
            pe_source_runtime_byte(&s_runtime, byte);
        }
        if (received < 0) {
            pe_source_runtime_serial_error(&s_runtime);
            stop_forever();
        }
        pe_source_runtime_tick(&s_runtime);
        if (s_runtime.io_fault) stop_forever();
        vTaskDelay(1);
    }
}

bool pe_esp32_source_service_start(void) {
    if (s_source_task != NULL) return s_runtime_armed;
    if (!assert_stop_before_task()) return false;
    s_boot_waiter = xTaskGetCurrentTaskHandle();
    if (xTaskCreatePinnedToCore(source_task, "pe_source", PE_TASK_STACK_BYTES,
                                NULL, PE_TASK_PRIORITY, &s_source_task, 0) !=
        pdPASS) return false;
    /* The source task owns all UART1/I2C0/expander transactions. Application
     * initialization cannot outrun its fail-low boot decision. */
    (void)ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    return s_runtime_armed;
}
