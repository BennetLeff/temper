/**
 * @file soak_store_nvs.c
 * @brief NVS binding of the coil-off token (components/control/pan_soak_store.h,
 *        output/temper-sensor-r3/firmware/DECISIONS.md D-SOAKNV).
 *
 * Namespace "temper_soak", key "off_s" (u32). nvs_flash_init() runs in main.c
 * before the state machine; every operation opens, acts, commits and closes,
 * so no handle is held across a power loss. ESP-IDF v5.3.6 nvs_flash.rst: a
 * power-off at any time loses at most the key-value pair being written.
 */

#include "pan_soak_store.h"

#include "esp_log.h"
#include "nvs.h"

#define SOAK_NVS_NS  "temper_soak"
#define SOAK_NVS_KEY "off_s"

static const char *TAG = "soak_nvs";

static bool nvs_load(void *ctx, uint32_t *off_s)
{
    (void)ctx;
    nvs_handle_t h;
    if (nvs_open(SOAK_NVS_NS, NVS_READONLY, &h) != ESP_OK) {
        return false;   /* namespace absent: no token */
    }
    const esp_err_t err = nvs_get_u32(h, SOAK_NVS_KEY, off_s);
    nvs_close(h);
    return err == ESP_OK;
}

static bool nvs_save(void *ctx, uint32_t off_s)
{
    (void)ctx;
    nvs_handle_t h;
    esp_err_t err = nvs_open(SOAK_NVS_NS, NVS_READWRITE, &h);
    if (err == ESP_OK) {
        err = nvs_set_u32(h, SOAK_NVS_KEY, off_s);
        if (err == ESP_OK) {
            err = nvs_commit(h);
        }
        nvs_close(h);
    }
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "coil-off token write failed: %s", esp_err_to_name(err));
    }
    return err == ESP_OK;
}

static bool nvs_clear(void *ctx)
{
    (void)ctx;
    nvs_handle_t h;
    esp_err_t err = nvs_open(SOAK_NVS_NS, NVS_READWRITE, &h);
    if (err == ESP_OK) {
        err = nvs_erase_key(h, SOAK_NVS_KEY);
        if (err == ESP_ERR_NVS_NOT_FOUND) {
            err = ESP_OK;
        } else if (err == ESP_OK) {
            err = nvs_commit(h);
        }
        nvs_close(h);
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "coil-off token revoke failed: %s (store disabled this session)",
                 esp_err_to_name(err));
    }
    return err == ESP_OK;
}

static const pss_hal_t s_hal = {.load = nvs_load, .save = nvs_save, .clear = nvs_clear, .ctx = NULL};

const pss_hal_t *pan_soak_store_hal(void)
{
    return &s_hal;
}
