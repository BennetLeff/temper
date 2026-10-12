/*
 * ESP32-S3 platform layer, part 1 (see platform_esp32.h): time, peripherals_*, sensor reads, the
 * blower request, the NVS fault log and the POST self-tests. ESP-IDF only; the host doubles are in
 * firmware/test/state_machine_stubs.c. Hardware mapping and failure behaviour per function:
 * firmware/build-evidence/esp-idf/PLATFORM.md.
 *
 * Every read that cannot be performed returns the sentinel its caller already trips on, never a
 * plausible value: resistance / current +INFINITY, temperature NaN, self-test false.
 */
#if defined(ESP_PLATFORM)
#include <math.h>
#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "sdkconfig.h"

#include "config.h"
#include "controller_board.h"
#include "max31865.h"
#include "platform_esp32.h"
#include "platform_logic.h"
#include "rtd_service.h"
#include "state_machine.h"
#include "../components/control/thermal_mgmt.h"
#if CONFIG_TEMPER_POWER_HW_BINDING
#include "n21_hw.h"
#endif

static const char *TAG = "platform";

/* thermal_io.c (no header) */
extern bool is_fan_running(void);
extern blower_diag_t thermal_blower_diag(void);

/* ---------------------------------------------------------------- time */
uint32_t get_time_ms(void)
{
    /* esp_timer: 64-bit microseconds since boot. The 32-bit ms value wraps after 49.7 days; the
     * state machine only uses unsigned differences. */
    return (uint32_t)(esp_timer_get_time() / 1000);
}

/* ---------------------------------------------------------------- sensors */
/* Pan RTD: PT100 on the MAX31865 (RTDSensing "rtd_pan", SPI2 RTD_SCK 11 / SDI 13 / SDO 12 / CS 10,
 * DRDY on TCA9555 P07; DECISIONS C20, C23). The word comes from rtd_service, which reads it on each
 * DRDY completion in the control task (the only caller of these two functions). */
float read_rtd_resistance(void)
{
    uint16_t w = 0;
    bool ok = rtd_service_latest_word(&w, NULL);
    return platform_rtd_resistance(ok, w, MAX31865_RREF_OHM);
}

float read_pan_temperature(void)
{
    uint16_t w = 0;
    bool ok = rtd_service_latest_word(&w, NULL);
    return platform_pan_temperature(ok, w, MAX31865_RREF_OHM);
}

/* DC bus current: this hardware has no DC-bus current measurement. Native-21's 1 mOhm DC-return
 * shunt feeds only a comparator (~61 A) whose output is ORed into BUS_FAULT (J4.10 -> GPIO21 and the
 * interlock latch, which drops PERMIT in hardware): zapote/power-stage-120v/README.md:79 and :113,
 * controller DECISIONS C5. The ADC channels are VBUS (bus voltage) and CT_MON / the AD8436 RMS (tank
 * current, not bus current; DECISIONS C11, C19), which the n21 binding already trips on. No
 * measurement is fabricated from them: the documented "unavailable" sentinel is returned, +INFINITY,
 * which check_safety_interlocks() latches as FAULT_IGBT_SHORT (> IGBT_SHORT_CURRENT_THRESHOLD) and
 * safety.c as SAFETY_OVER_CURRENT (!isfinite). */
float read_dc_bus_current(void)
{
    static bool s_logged;
    if (!s_logged) {
        s_logged = true;
        ESP_LOGE(TAG, "read_dc_bus_current: no DC-bus current measurement on this controller "
                      "(native-21 shunt -> comparator -> BUS_FAULT only); returning +inf (fault)");
    }
    return INFINITY;
}

/* ---------------------------------------------------------------- blower request (C28) */
static portMUX_TYPE s_fan_mux = portMUX_INITIALIZER_UNLOCKED;
static platform_fan_req_t s_fan_req;

void fan_set_speed(fan_speed_t speed)
{
    portENTER_CRITICAL(&s_fan_mux);
    platform_fan_request_speed(&s_fan_req, speed == FAN_SPEED_MAX);
    portEXIT_CRITICAL(&s_fan_mux);
}

void fan_set_auto_mode(bool enabled)
{
    portENTER_CRITICAL(&s_fan_mux);
    platform_fan_request_auto(&s_fan_req, enabled);
    portEXIT_CRITICAL(&s_fan_mux);
}

bool platform_fan_full_speed_requested(void)
{
    portENTER_CRITICAL(&s_fan_mux);
    bool full = s_fan_req.full_speed_floor;
    portEXIT_CRITICAL(&s_fan_mux);
    return full;
}

/* ---------------------------------------------------------------- fault log (NVS) */
/* There is no EEPROM on this controller; the store is the NVS partition (partitions.csv "nvs",
 * initialised by init_nvs() in main.c before any task starts). One blob, a 16-entry ring. */
#define FAULT_LOG_NS  "temper"
#define FAULT_LOG_KEY "faultlog"

static platform_fault_log_t s_log;
static bool s_log_ready;

/* ESP_OK: s_log holds the stored log, or a fresh one if none / a corrupt one was stored.
 * Anything else: NVS itself failed (s_log is then a fresh RAM log). */
static esp_err_t fault_log_load(void)
{
    nvs_handle_t h;
    esp_err_t e = nvs_open(FAULT_LOG_NS, NVS_READWRITE, &h);
    if (e != ESP_OK) {
        platform_fault_log_init(&s_log);
        return e;
    }
    size_t len = sizeof s_log;
    e = nvs_get_blob(h, FAULT_LOG_KEY, &s_log, &len);
    nvs_close(h);
    if (e == ESP_ERR_NVS_NOT_FOUND) {
        platform_fault_log_init(&s_log);
        return ESP_OK;
    }
    if (e == ESP_ERR_NVS_INVALID_LENGTH || (e == ESP_OK && (len != sizeof s_log || !platform_fault_log_valid(&s_log)))) {
        ESP_LOGW(TAG, "stored fault log unreadable (format): starting a new one");
        platform_fault_log_init(&s_log);
        return ESP_OK;
    }
    if (e != ESP_OK) platform_fault_log_init(&s_log);
    return e;
}

static esp_err_t fault_log_store(void)
{
    nvs_handle_t h;
    esp_err_t e = nvs_open(FAULT_LOG_NS, NVS_READWRITE, &h);
    if (e != ESP_OK) return e;
    e = nvs_set_blob(h, FAULT_LOG_KEY, &s_log, sizeof s_log);
    if (e == ESP_OK) e = nvs_commit(h);
    nvs_close(h);
    return e;
}

/* Called on FAULT / RUNAWAY_FAULT entry (state_handlers.c), after the power cut. A storage failure
 * is logged and otherwise ignored: the fault handling itself never depends on the log. */
void eeprom_log_fault(fault_code_t code, uint32_t timestamp)
{
    if (!s_log_ready) {
        (void)fault_log_load();
        s_log_ready = true;
    }
    platform_fault_log_append(&s_log, (uint16_t)code, timestamp);
    esp_err_t e = fault_log_store();
    if (e != ESP_OK)
        ESP_LOGE(TAG, "fault %d not stored: %s", (int)code, esp_err_to_name(e));
    else
        ESP_LOGW(TAG, "fault %d logged (seq %u)", (int)code, (unsigned)(s_log.next_seq - 1u));
}

/* ---------------------------------------------------------------- peripherals */
/* DECISIONS C6: after BIAS is on (rtd_service_bootstrap() in main.c) wait >= 10 ms (MAX31865 start
 * and the 0.67 ms threshold RC) before the RTD comparator read-back is trusted. */
#define PLATFORM_RTD_BIAS_SETTLE_MS 10u
/* Wait for the first calibrated ADC1 frame (n21 continuous pattern) before POST, bounded. */
#define PLATFORM_ADC_FIRST_FRAME_MS 100u
#define PLATFORM_ADC_MAX_AGE_US     20000u /* thermal_io.c THERMAL_MAX_AGE_US */

/* Called from state_init_entry() (state_machine_init() in app_main, before the tasks start). The
 * board itself (pins, I2C expander, UI SPI3 bus, blower, RTD bootstrap, n21) is brought up by
 * init_peripherals() in main.c; this adds the UI board, the fault-log boot record and the settle
 * delays POST depends on. Idempotent. */
void peripherals_init(void)
{
    static bool s_done;
    if (s_done) return;
    s_done = true;

    if (fault_log_load() == ESP_OK) {
        platform_fault_log_new_boot(&s_log);
        if (fault_log_store() != ESP_OK) ESP_LOGW(TAG, "fault log boot record not stored");
    }
    s_log_ready = true;

    if (!platform_ui_init()) ESP_LOGE(TAG, "UI board not available: POST display test will fail");

    vTaskDelay(pdMS_TO_TICKS(PLATFORM_RTD_BIAS_SETTLE_MS));
#if CONFIG_TEMPER_POWER_HW_BINDING
    float mv[N21_THERMAL_COUNT];
    for (unsigned i = 0; i < PLATFORM_ADC_FIRST_FRAME_MS && !n21_hw_thermal_mv(mv, PLATFORM_ADC_MAX_AGE_US); i++)
        vTaskDelay(pdMS_TO_TICKS(1));
#endif
}

/* No low-power mode on this controller: sdkconfig.defaults sets CONFIG_PM_ENABLE=n ("need
 * deterministic timing"), the control task must keep the TPS3823 heartbeat (IL_WDI) and the
 * expander/RTD polls running in IDLE, and the blower belongs to the fan law. Documented no-ops. */
void peripherals_enter_low_power(void) {}
void peripherals_exit_low_power(void) {}

/* ---------------------------------------------------------------- POST self-tests */
/* ADC1 is the n21 continuous pattern (DECISIONS C12); a thermal mean exists only for samples that
 * adc_cali_raw_to_voltage() converted (n21_hw_esp32.c), so a fresh, in-range frame shows the ADC
 * and its calibration working. Without the n21 hardware binding there is no ADC owner: fail. */
bool test_adc_calibration(void)
{
#if CONFIG_TEMPER_POWER_HW_BINDING
    float mv[N21_THERMAL_COUNT];
    if (!n21_hw_thermal_mv(mv, PLATFORM_ADC_MAX_AGE_US)) {
        ESP_LOGE(TAG, "POST adc: no fresh calibrated ADC1 frame");
        return false;
    }
    for (unsigned k = 0; k < N21_THERMAL_COUNT; k++) {
        if (!isfinite(mv[k]) || mv[k] < 0.0f || mv[k] > 3300.0f) {
            ESP_LOGE(TAG, "POST adc: thermal channel %u = %.1f mV out of range", k, (double)mv[k]);
            return false;
        }
    }
    return true;
#else
    ESP_LOGE(TAG, "POST adc: CONFIG_TEMPER_POWER_HW_BINDING=n, no ADC1 owner");
    return false;
#endif
}

/* Blower (C28, C33): supervised continuously by the stall detector (is_fan_running() false ->
 * FAULT_FAN_FAILURE). POST passes only while no stall / PS3-absent / blower-failed diagnosis is
 * active. The tach counter is not read here: it belongs to the monitor task. */
bool test_fan_operation(void)
{
    blower_diag_t d = thermal_blower_diag();
    bool ok = is_fan_running() && d == BLOWER_DIAG_OK;
    if (!ok) ESP_LOGE(TAG, "POST fan: running=%d diag=%d", (int)is_fan_running(), (int)d);
    return ok;
}

/* The hardware comparators (thermal-sense HS / COIL trips, RTD window comparator RTD_HW_FAULT) can
 * only be observed, never driven, by the MCU (DECISIONS C4). POST reads them back through the
 * TCA9555 (P12, P13, P11) and passes only on a fresh snapshot with none asserted. The interlock
 * latch (P10) is not checked: it is latched at power-up until the reset request (C6). */
bool test_hardware_comparators(void)
{
    ctrl_exp_cache_t c;
    if (!ctrl_board_expander(&c) || !ctrl_exp_fresh(&c, (uint64_t)esp_timer_get_time(), CTRL_EXP_MAX_AGE_US)) {
        ESP_LOGE(TAG, "POST comparators: no fresh TCA9555 snapshot");
        return false;
    }
    ctrl_exp_inputs_t in = ctrl_exp_decode(c.raw);
    if (in.hs_fault || in.coil_fault || in.rtd_fault) {
        ESP_LOGE(TAG, "POST comparators: hs=%d coil=%d rtd=%d", in.hs_fault, in.coil_fault, in.rtd_fault);
        return false;
    }
    return true;
}

/* MAX31865: the service bootstrapped (thresholds written, fault cycle armed). If a conversion has
 * completed, its resistance must lie strictly inside the guard window; before the first one the
 * service's 100 ms DRDY bound and the runtime interlocks supervise. */
bool test_rtd_sensor(void)
{
    if (!rtd_service_is_ready()) {
        ESP_LOGE(TAG, "POST rtd: MAX31865 service not ready");
        return false;
    }
    uint16_t w = 0;
    if (rtd_service_latest_word(&w, NULL)) {
        float r = platform_rtd_resistance(true, w, MAX31865_RREF_OHM);
        if (!(r > RTD_SHORT_FAULT_OHM && r < RTD_OPEN_FAULT_OHM)) {
            ESP_LOGE(TAG, "POST rtd: %.2f ohm outside the guard window", (double)r);
            return false;
        }
    }
    return true;
}

/* The SSD1322 is write-only on its serial interface, so the UI bus is proven through the MCP23S08
 * on the same connector and bus (configuration read-back, ui_esp32.c). */
bool test_display_communication(void)
{
    bool ok = platform_ui_present();
    if (!ok) ESP_LOGE(TAG, "POST display: UI board (MCP23S08) not answering");
    return ok;
}

/* NVS fault log readable: an empty or format-reset log passes, an NVS failure does not. */
bool test_eeprom_read(void)
{
    esp_err_t e = fault_log_load();
    s_log_ready = true;
    if (e != ESP_OK) ESP_LOGE(TAG, "POST nvs: %s", esp_err_to_name(e));
    return e == ESP_OK;
}

#endif /* ESP_PLATFORM */
