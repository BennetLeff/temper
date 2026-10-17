/**
 * @file main.c
 * @brief Main entry point for induction cooker firmware
 * 
 * ESP-IDF application for ESP32-S3 based induction cooker.
 * 
 * Features:
 * - State machine for cooking operations
 * - PID temperature control
 * - PLL for ZVS frequency tracking
 * - Pan detection
 * - Safety monitoring with watchdog
 */

#include <stdio.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "nvs_flash.h"

#include "state_machine.h"
#include "hal.h"
#include "rtd_service.h"
#include "board_power.h"
#include "power_service.h"
#include "../components/safety/safety.h"
#include "../components/safety/wdi_supervisor.h"

extern uint32_t get_time_ms(void);

static const char *TAG = "main";

/* Task priorities */
#define CONTROL_TASK_PRIORITY   (configMAX_PRIORITIES - 1)  /* Highest */
#define UI_TASK_PRIORITY        (configMAX_PRIORITIES - 3)
#define MONITOR_TASK_PRIORITY   (configMAX_PRIORITIES - 2)
/* Below the control task, above UI/monitor: a starved supervisor stops the
 * heartbeat (fail safe), a starved control loop is what it watches for. */
#define WDI_SUP_TASK_PRIORITY   (configMAX_PRIORITIES - 2)

/* Task stack sizes */
#define CONTROL_TASK_STACK_SIZE 4096
#define UI_TASK_STACK_SIZE      2048
#define MONITOR_TASK_STACK_SIZE 2048
#define WDI_SUP_TASK_STACK_SIZE 2048

/* Control loop timing */
#define CONTROL_LOOP_PERIOD_MS  10  /* 100 Hz */
#define UI_LOOP_PERIOD_MS       50  /* 20 Hz */
#define MONITOR_LOOP_PERIOD_MS  100 /* 10 Hz */

/**
 * @brief Main control loop task
 * 
 * Runs at 100Hz, handles:
 * - State machine updates
 * - PID temperature control
 * - PLL frequency tracking
 */
static void control_task(void *arg) {
    ESP_LOGI(TAG, "Control task started");

    /* Subscribe to the task watchdog: the state handlers' watchdog_feed()
     * calls reset it, and without the subscription each one logged "task not
     * found" (sensor-r3 DECISIONS.md open item 1). A loop that stops feeding
     * for the state's timeout panics and reboots into safe mode
     * (check_boot_reason()). */
    esp_err_t wdt_err = esp_task_wdt_add(NULL);
    if (wdt_err != ESP_OK) {
        /* The WDI supervisor still watches this loop's progress. */
        ESP_LOGE(TAG, "esp_task_wdt_add(control) failed: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(CONTROL_LOOP_PERIOD_MS);
    
    while (1) {
        /* DRDY ISR only records completion. Keep MAX31865 SPI and resulting
         * state changes in this task so it is the sole state-machine owner. */
        rtd_service_control_tick();

        /* Update state machine (handles PID, PLL internally) */
        state_machine_update();

        power_service_tick();

        /* Progress for the WDI supervisor (zapote C42): one loop iteration,
         * and the newest RTD conversion this loop has seen. */
        {
            bool rtd_valid = false;
            uint32_t rtd_seq = 0u;
#ifdef TEMPER_PAN_CONTROL_C1
            rtd_sample_t rtd;
            if (rtd_service_latest_sample(&rtd)) {
                rtd_valid = true;
                rtd_seq = rtd.seq;
            }
#endif
            wdi_progress_publish(rtd_valid, rtd_seq);
        }
        
        /* Wait for next period */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

/**
 * @brief TPS3823 WDI supervisor (zapote/controller DECISIONS C42)
 *
 * The only code that toggles WDI (GPIO18). Every WDI_SUP_PERIOD_MS it checks
 * that the control loop advanced and the newest RTD conversion is recent
 * (wdi_supervisor.c), and drives one WDI edge only then. A stalled loop, a
 * stopped converter or a late supervisor stops the heartbeat for good; the
 * TPS3823 then trips the interlock latch within 0.9-2.5 s and PERMIT drops.
 * Not an ISR, timer, LEDC or RMT: a live timer with a dead loop must not keep
 * the heartbeat going.
 */
static void wdi_supervisor_task(void *arg) {
    (void)arg;
    wdi_sup_t sup;
    const wdi_sup_params_t params = WDI_SUP_DEFAULT_PARAMS();
    if (!wdi_sup_init(&sup, &params)) {
        ESP_LOGE(TAG, "WDI supervisor parameters rejected: no heartbeat");
    }
    wdi_stop_reason_t reported = WDI_STOP_NONE;

    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(WDI_SUP_PERIOD_MS);
    while (1) {
        uint32_t loop_seq;
        bool rtd_valid;
        uint32_t rtd_seq;
        bool level;
        wdi_progress_read(&loop_seq, &rtd_valid, &rtd_seq);
        if (wdi_sup_step(&sup, get_time_ms(), loop_seq, rtd_valid, rtd_seq, &level)) {
            watchdog_hardware_write_wdi(level);
        }
        if (wdi_sup_state(&sup) == WDI_SUP_STOPPED && reported == WDI_STOP_NONE) {
            reported = wdi_sup_stop_reason(&sup);
            ESP_LOGE(TAG, "WDI heartbeat stopped (reason %d): the TPS3823 will trip the latch",
                     (int)reported);
        }
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

/**
 * @brief UI handling task
 * 
 * Runs at 20Hz, handles:
 * - Button inputs
 * - Display updates
 * - User feedback
 */
static void ui_task(void *arg) {
    ESP_LOGI(TAG, "UI task started");
    
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(UI_LOOP_PERIOD_MS);
    
    while (1) {
        /* Handle button presses, update display */
        /* ui_update(); */
        
        /* Wait for next period */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

/**
 * @brief Safety monitor task
 * 
 * Runs at 10Hz, handles:
 * - Temperature monitoring
 * - Current monitoring
 * - Fan status
 * - Safety interlocks
 */
static void monitor_task(void *arg) {
    ESP_LOGI(TAG, "Monitor task started");
    
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(MONITOR_LOOP_PERIOD_MS);
    
    while (1) {
        /* Run safety checks */
        /* safety_monitor_update(); */
        
        /* Wait for next period */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

/**
 * @brief Initialize NVS (Non-Volatile Storage)
 */
static void init_nvs(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
}

/**
 * @brief Initialize all peripherals
 */
static void init_peripherals(void) {
    ESP_LOGI(TAG, "Initializing peripherals...");

    if (hal_init() != HAL_OK) {
        /* rtd_service_control_tick() will fail closed before the power stage
         * can run. Continue initialization only to preserve the boot owner. */
        ESP_LOGE(TAG, "HAL initialization failed");
    }
    
    /* Initialize GPIO */
    /* gpio_init(); */
    
    /* Initialize ADC for temperature sensing */
    /* adc_init(); */
    
    /* Inhibited until a reviewed full-bridge board binding is installed. */
    power_service_bootstrap();

    /* Power-stage side of the controller: gate commands held low, RUN_EN
     * low through power_gate, the PLL and pan-detect capture on CT_ZC. The
     * gate drive belongs to the power owner (power_service.c); its board
     * binding is TODO(hardware) (board_power.c). */
    board_power_init();
    
    /* Board-owned SPI2/MAX31865 bootstrap. On zapote DRDY is TCA9555 P07,
     * polled over I2C (D-DRDY); an expander that does not answer fails the
     * bootstrap closed. No SPI transfer is performed in an ISR. */
    if (rtd_service_bootstrap() != HAL_OK) {
        ESP_LOGE(TAG, "MAX31865 bootstrap failed; control task will fail closed");
    }
    
    /* Initialize I2C for display */
    /* i2c_init(); */
    
    ESP_LOGI(TAG, "Peripherals initialized");
}

/**
 * @brief Application entry point
 */
void app_main(void) {
    ESP_LOGI(TAG, "=================================");
    ESP_LOGI(TAG, "  Induction Cooker Firmware");
    ESP_LOGI(TAG, "  Version: 1.0.0");
    ESP_LOGI(TAG, "=================================");
    
    /* Initialize NVS */
    init_nvs();
    
    /* Initialize peripherals */
    init_peripherals();
    
    /* Initialize state machine */
    state_machine_init();
    
    /* External hardware watchdog (TPS3823-33, zapote C42): WDI (GPIO18) as an
     * output, low. Only wdi_supervisor_task toggles it. */
    watchdog_hardware_init();
    
    /* Initialize software safety watchdog */
    safety_wdt_init();
    
    /* Check boot reason (watchdog reset handling) */
    check_boot_reason();
    
    /* Create control task (highest priority) */
    xTaskCreatePinnedToCore(
        control_task,
        "control",
        CONTROL_TASK_STACK_SIZE,
        NULL,
        CONTROL_TASK_PRIORITY,
        NULL,
        1  /* Pin to Core 1 */
    );
    
    /* Create the WDI supervisor (C42) */
    xTaskCreatePinnedToCore(
        wdi_supervisor_task,
        "wdi_sup",
        WDI_SUP_TASK_STACK_SIZE,
        NULL,
        WDI_SUP_TASK_PRIORITY,
        NULL,
        0  /* Core 0: not the control loop's core */
    );

    /* Create UI task */
    xTaskCreatePinnedToCore(
        ui_task,
        "ui",
        UI_TASK_STACK_SIZE,
        NULL,
        UI_TASK_PRIORITY,
        NULL,
        0  /* Pin to Core 0 */
    );
    
    /* Create safety monitor task */
    xTaskCreatePinnedToCore(
        monitor_task,
        "monitor",
        MONITOR_TASK_STACK_SIZE,
        NULL,
        MONITOR_TASK_PRIORITY,
        NULL,
        0  /* Pin to Core 0 */
    );
    
    ESP_LOGI(TAG, "All tasks started successfully");
    
    /* Main loop - just idle, tasks handle everything */
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
