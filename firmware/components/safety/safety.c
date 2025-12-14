/**
 * @file safety.c
 * @brief Safety and watchdog implementation
 * 
 * Implements multi-level safety:
 * 1. Hardware watchdog - resets MCU if firmware hangs
 * 2. Logical watchdog - only resets if safety conditions met
 * 3. Boot reason detection - enters safe mode after crash
 * 4. Continuous interlock monitoring
 * 
 * Non-ESP Simulation Mode:
 * When building without ESP-IDF, simulation stubs are provided that:
 * - Track safety state for testing
 * - Allow fault injection via safety_sim_* functions
 * - Default to SAFE (not FAULT) to allow normal testing flow
 * - Can be configured for strict mode that always faults
 */

#include "safety.h"
#include <stddef.h>
#include <stdbool.h>
#include <math.h>

/* ESP-IDF includes (available when building with ESP-IDF) */
#ifdef ESP_PLATFORM
#include "esp_task_wdt.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "safety";
#endif

/* Configuration */
#define CONTROL_LOOP_FREQ_HZ    100
#define OVER_TEMP_THRESHOLD     100.0f  /* °C */
#define OVER_CURRENT_THRESHOLD  35.0f   /* Amps */
#define TEMP_HYSTERESIS         5.0f    /* °C - hysteresis band */
#define CURRENT_HYSTERESIS      2.0f    /* A - hysteresis band */

/* Hardware Watchdog GPIO Configuration
 * TPS3823-33 WDI input - must toggle to prevent timeout
 * Timeout: 1.6 seconds
 * GPIO can be any available ESP32 GPIO - configure in sdkconfig or here
 */
#ifdef ESP_PLATFORM
#include "driver/gpio.h"
#define WDI_GPIO_NUM            GPIO_NUM_4  /* Configure as needed */
#endif

/* Module state */
static bool safe_mode_active = false;
static uint32_t current_wdt_timeout = WDT_TIMEOUT_MS;
static bool wdi_state = false;  /* Current state of WDI GPIO (for toggle) */

/* ============================================================================
 * Simulation/Testing Support (Non-ESP builds)
 * ============================================================================ */
#ifndef ESP_PLATFORM

/* Simulated sensor values for testing */
static struct {
    float heatsink_temp;
    float dc_bus_current;
    float rtd_resistance;
    bool fan_running;
    bool strict_mode;           /* If true, always return fault */
    safety_status_t injected_fault;
    uint32_t wdt_feed_count;
} sim_state = {
    .heatsink_temp = 25.0f,     /* Room temperature */
    .dc_bus_current = 0.0f,     /* No current */
    .rtd_resistance = 110.0f,   /* ~25°C for PT100 */
    .fan_running = true,        /* Fan OK */
    .strict_mode = false,
    .injected_fault = SAFETY_OK,
    .wdt_feed_count = 0
};

/* Simulation API for testing */
void safety_sim_set_temp(float temp) { sim_state.heatsink_temp = temp; }
void safety_sim_set_current(float current) { sim_state.dc_bus_current = current; }
void safety_sim_set_rtd(float resistance) { sim_state.rtd_resistance = resistance; }
void safety_sim_set_fan(bool running) { sim_state.fan_running = running; }
void safety_sim_set_strict_mode(bool strict) { sim_state.strict_mode = strict; }
void safety_sim_inject_fault(safety_status_t fault) { sim_state.injected_fault = fault; }
void safety_sim_reset(void) {
    sim_state.heatsink_temp = 25.0f;
    sim_state.dc_bus_current = 0.0f;
    sim_state.rtd_resistance = 110.0f;
    sim_state.fan_running = true;
    sim_state.strict_mode = false;
    sim_state.injected_fault = SAFETY_OK;
    sim_state.wdt_feed_count = 0;
    safe_mode_active = false;
}
uint32_t safety_sim_get_wdt_feeds(void) { return sim_state.wdt_feed_count; }

/* Simulated sensor reads */
static float read_heatsink_temperature(void) { return sim_state.heatsink_temp; }
static float read_dc_bus_current(void) { return sim_state.dc_bus_current; }
static float read_rtd_resistance(void) { return sim_state.rtd_resistance; }
static bool is_fan_running(void) { return sim_state.fan_running; }

/* Simulated output functions */
static void pwm_disable_all(void) { /* no-op in sim */ }
static void power_set_level(uint8_t level) { (void)level; /* no-op in sim */ }

#else

/* External function declarations (implemented in peripherals) */
extern float read_heatsink_temperature(void);
extern float read_dc_bus_current(void);
extern bool is_fan_running(void);
extern float read_rtd_resistance(void);
extern void pwm_disable_all(void);
extern void power_set_level(uint8_t level);

#endif /* ESP_PLATFORM */

/* ============================================================================
 * Watchdog Functions
 * ============================================================================ */

void safety_wdt_init(void) {
#ifdef ESP_PLATFORM
    esp_task_wdt_config_t config = {
        .timeout_ms = WDT_TIMEOUT_MS,
        .idle_core_mask = (1 << 0) | (1 << 1), /* Watch both cores' Idle tasks */
        .trigger_panic = true,                  /* Panic (Reboot) on timeout */
    };
    ESP_ERROR_CHECK(esp_task_wdt_init(&config));
    ESP_LOGI(TAG, "Task WDT Initialized with %d ms timeout", WDT_TIMEOUT_MS);
#endif
}

void watchdog_set_timeout(uint32_t timeout_ms) {
    current_wdt_timeout = timeout_ms;
#ifdef ESP_PLATFORM
    esp_task_wdt_config_t config = {
        .timeout_ms = timeout_ms,
        .idle_core_mask = (1 << 0) | (1 << 1),
        .trigger_panic = true,
    };
    esp_task_wdt_reconfigure(&config);
    ESP_LOGD(TAG, "WDT timeout set to %lu ms", timeout_ms);
#endif
}

void watchdog_feed(void) {
#ifdef ESP_PLATFORM
    esp_task_wdt_reset();
#else
    sim_state.wdt_feed_count++;
#endif
}

void secure_wdt_reset(void) {
    bool safety_ok = check_hardware_interlocks();
    bool sensor_ok = check_sensors_valid();
    
    if (safety_ok && sensor_ok) {
#ifdef ESP_PLATFORM
        esp_task_wdt_reset();
#else
        sim_state.wdt_feed_count++;
#endif
    } else {
        /* If unsafe, DO NOT reset WDT. 
         * Let it timeout and reboot the system to reach Safe State. */
#ifdef ESP_PLATFORM
        ESP_LOGE(TAG, "Safety check failed! Allowing WDT timeout...");
#endif
    }
}

/* ============================================================================
 * Boot Reason and Safe Mode
 * ============================================================================ */

void check_boot_reason(void) {
#ifdef ESP_PLATFORM
    esp_reset_reason_t reason = esp_reset_reason();
    if (reason == ESP_RST_TASK_WDT || reason == ESP_RST_WDT) {
        ESP_LOGE(TAG, "Rebooted due to Watchdog Timeout! Entering SAFE MODE.");
        enter_safe_mode();
    }
#endif
}

void enter_safe_mode(void) {
    safe_mode_active = true;
    
    /* Disable all power outputs */
    pwm_disable_all();
    power_set_level(0);
    
#ifdef ESP_PLATFORM
    ESP_LOGE(TAG, "SAFE MODE ACTIVE - Manual reset required");
#endif
}

bool is_safe_mode_active(void) {
    return safe_mode_active;
}

/* ============================================================================
 * Safety Checks
 * ============================================================================ */

bool check_hardware_interlocks(void) {
#ifndef ESP_PLATFORM
    /* Simulation mode */
    if (sim_state.strict_mode) {
        return false;  /* Always fail in strict mode */
    }
    if (sim_state.injected_fault != SAFETY_OK) {
        return false;  /* Fail if fault injected */
    }
#endif

    /* Over-temperature check with NaN protection */
    float temp = read_heatsink_temperature();
    if (!isfinite(temp) || temp > OVER_TEMP_THRESHOLD) {
#ifdef ESP_PLATFORM
        ESP_LOGW(TAG, "Over-temperature: %.1f°C", temp);
#endif
        return false;
    }
    
    /* Over-current check with NaN protection */
    float current = read_dc_bus_current();
    if (!isfinite(current) || current > OVER_CURRENT_THRESHOLD) {
#ifdef ESP_PLATFORM
        ESP_LOGW(TAG, "Over-current: %.1fA", current);
#endif
        return false;
    }
    
    /* Fan running check */
    if (!is_fan_running()) {
#ifdef ESP_PLATFORM
        ESP_LOGW(TAG, "Fan failure detected");
#endif
        return false;
    }
    
    return true;
}

bool check_sensors_valid(void) {
#ifndef ESP_PLATFORM
    /* Simulation mode */
    if (sim_state.strict_mode) {
        return false;  /* Always fail in strict mode */
    }
#endif

    /* RTD probe checks with NaN protection */
    float rtd_resistance = read_rtd_resistance();
    
    if (!isfinite(rtd_resistance)) {
#ifdef ESP_PLATFORM
        ESP_LOGW(TAG, "RTD probe invalid reading (NaN/Inf)");
#endif
        return false;
    }
    
    /* Open circuit check */
    if (rtd_resistance > 10000.0f) {
#ifdef ESP_PLATFORM
        ESP_LOGW(TAG, "RTD probe open circuit");
#endif
        return false;
    }
    
    /* Short circuit check */
    if (rtd_resistance < 10.0f) {
#ifdef ESP_PLATFORM
        ESP_LOGW(TAG, "RTD probe short circuit");
#endif
        return false;
    }
    
    return true;
}

safety_status_t run_safety_check(void) {
#ifndef ESP_PLATFORM
    /* Simulation mode - check for injected faults first */
    if (sim_state.strict_mode) {
        return SAFETY_INTERLOCK_TRIP;  /* Always fail in strict mode */
    }
    if (sim_state.injected_fault != SAFETY_OK) {
        return sim_state.injected_fault;
    }
#endif

    /* Temperature check with NaN protection */
    float temp = read_heatsink_temperature();
    if (!isfinite(temp) || temp > OVER_TEMP_THRESHOLD) {
        return SAFETY_OVER_TEMP;
    }
    
    /* Current check with NaN protection */
    float current = read_dc_bus_current();
    if (!isfinite(current) || current > OVER_CURRENT_THRESHOLD) {
        return SAFETY_OVER_CURRENT;
    }
    
    /* Fan check */
    if (!is_fan_running()) {
        return SAFETY_FAN_FAILURE;
    }
    
    /* Sensor check */
    if (!check_sensors_valid()) {
        return SAFETY_SENSOR_FAULT;
    }
    
    return SAFETY_OK;
}

void trigger_hardware_shutdown(void) {
#ifdef ESP_PLATFORM
    ESP_LOGE(TAG, "EMERGENCY HARDWARE SHUTDOWN");
#endif
    pwm_disable_all();
    power_set_level(0);
    safe_mode_active = true;
}

/* ============================================================================
 * External Hardware Watchdog (TPS3823-33)
 * ============================================================================
 * 
 * The external hardware watchdog provides MCU lockup protection independent
 * of software. If the ESP32 hard-locks (ESD, silicon bug, power glitch), the
 * TPS3823-33 will timeout after 1.6s and assert RESET, which is integrated
 * into the fault OR gate to disable the power stage.
 * 
 * See SAFETY_INTERLOCK_DESIGN.md Section 7 for circuit details.
 * See sim_21_hardware_watchdog.cir for SPICE verification.
 */

void watchdog_hardware_init(void) {
#ifdef ESP_PLATFORM
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << WDI_GPIO_NUM),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));
    gpio_set_level(WDI_GPIO_NUM, 0);
    wdi_state = false;
    ESP_LOGI(TAG, "Hardware watchdog WDI initialized on GPIO%d", WDI_GPIO_NUM);
#else
    /* Simulation: just reset state */
    wdi_state = false;
#endif
}

void watchdog_hardware_feed(void) {
    /* Toggle WDI state to generate edge for TPS3823-33 */
    wdi_state = !wdi_state;
    
#ifdef ESP_PLATFORM
    gpio_set_level(WDI_GPIO_NUM, wdi_state ? 1 : 0);
#endif
    /* No simulation tracking needed - the behavior is in the GPIO toggle */
}

/* ============================================================================
 * Example Control Task (ESP32 only)
 * ============================================================================ */

#ifdef ESP_PLATFORM
/**
 * @brief Example critical control task with watchdog monitoring
 * 
 * This shows how to integrate watchdog into the main control loop.
 */
void task_control_loop(void *arg) {
    /* 1. Subscribe this task to the WDT */
    /* If we don't call reset() within timeout, system reboots */
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(1000 / CONTROL_LOOP_FREQ_HZ);
    
    while (1) {
        /* 2. Execute critical logic */
        /* If this hangs > timeout, WDT triggers */
        /* run_pid_loop(); */
        /* check_safety_interlocks(); */
        
        /* 3. "Pet the Dog" (Reset Timer) */
        /* CRITICAL: Only reset if logical conditions are met */
        secure_wdt_reset();
        
        /* 4. Wait for next cycle */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}
#endif
