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
#include "esp_timer.h"
#include "nvs_flash.h"

#include "state_machine.h"
#include "hal.h"
#include "rtd_service.h"
/* These will be included when components are built */
/* #include "pan_detect.h" */
/* #include "pid_control.h" */
/* #include "pll_control.h" */
#include "../components/safety/safety.h"

static const char *TAG = "main";

/* Task priorities */
#define CONTROL_TASK_PRIORITY   (configMAX_PRIORITIES - 1)  /* Highest */
#define UI_TASK_PRIORITY        (configMAX_PRIORITIES - 3)
#define MONITOR_TASK_PRIORITY   (configMAX_PRIORITIES - 2)

/* Task stack sizes */
#define CONTROL_TASK_STACK_SIZE 4096
#define UI_TASK_STACK_SIZE      2048
#define MONITOR_TASK_STACK_SIZE 2048

/* Control loop timing */
#define CONTROL_LOOP_PERIOD_MS  10  /* 100 Hz */
#define UI_LOOP_PERIOD_MS       50  /* 20 Hz */
#define MONITOR_LOOP_PERIOD_MS  100 /* 10 Hz */

/* ============================================================================
 * Time base
 * ============================================================================
 *
 * Board-side definition of the `extern uint32_t get_time_ms(void)` declared by
 * state_machine.c:53, state_handlers.c:24 and low_temp_control.c:22. Defined
 * here because main.c is compiled only into the ESP32-S3 image; the host test
 * builds get their own controllable version from test/state_machine_stubs.c,
 * so this must not move into a translation unit those builds compile.
 *
 * Contract, as fixed by the existing call sites rather than chosen here:
 *
 *   Epoch    -- microseconds since boot, from esp_timer. Every consumer forms
 *               `now - then`; the only absolute uses are the `> 0` "have I got
 *               a prior sample" sentinel in check_runaway_boundary()
 *               (state_machine.c:472) and the eeprom_log_fault() timestamp.
 *               Nothing needs a wall clock.
 *   Width    -- uint32_t, matching both the declarations above and
 *               hal_time_ms_t (hal_types.h:224). Wraps every ~49.7 days;
 *               consumers subtract in unsigned arithmetic, which is correct
 *               across the wrap.
 *   Failure  -- none. esp_timer is brought up by the IDF startup code before
 *               app_main and is monotonic; esp_timer_get_time() has no error
 *               return.
 *
 * Deliberately NOT routed through HAL_TIME_MS() / hal_timer->get_time_ms(),
 * which is what the obvious reading of hal_timer.h suggests. That macro
 * (hal_timer.h:163-164) evaluates to 0 whenever `hal_timer` is NULL, so a
 * HAL that was never initialised -- and init_peripherals() below explicitly
 * continues past a failed hal_init() -- would freeze this counter at 0.
 * A frozen clock does not announce itself: check_runaway_boundary() gates its
 * rate-of-rise test on `last_pan_temp_time_ms > 0`, which never becomes true
 * if the clock never leaves 0, so the thermal-runaway rate trip would be
 * silently and permanently disarmed while every other check still appeared to
 * run. esp_timer removes that coupling instead of papering over it, and is
 * also cheaper (no indirect call). See docs/FIRMWARE_LINK_TRIAGE.md.
 */
uint32_t get_time_ms(void) {
    /* esp_timer_get_time() is int64 microseconds since boot and always
     * non-negative, so the narrowing to uint32_t is a well-defined modular
     * reduction -- the intended wrap, not undefined behaviour. */
    return (uint32_t)(esp_timer_get_time() / 1000);
}

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
    
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(CONTROL_LOOP_PERIOD_MS);
    
    while (1) {
        /* DRDY ISR only records completion. Keep MAX31865 SPI and resulting
         * state changes in this task so it is the sole state-machine owner. */
        rtd_service_control_tick();

        /* Update state machine (handles PID, PLL internally) */
        state_machine_update();
        
        /* Wait for next period */
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
    
    /* Initialize MCPWM for gate driver */
    /* mcpwm_init(); */
    
    /* Board-owned SPI2/MAX31865 bootstrap. DRDY on GPIO9 is configured as a
     * falling-edge handoff; no SPI transfer is performed in its ISR. */
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
    
    /* Initialize external hardware watchdog (TPS3823-33)
     * CRITICAL: Must be called before control task starts!
     * This configures the WDI GPIO that state_machine_update() toggles.
     * See SAFETY_INTERLOCK_DESIGN.md Section 7. */
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
