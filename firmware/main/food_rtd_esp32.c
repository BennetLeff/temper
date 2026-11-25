/**
 * @file food_rtd_esp32.c
 * @brief C51 food-probe RTD (J9, U50) on ESP-IDF: the link for rtd_food_service.h.
 *
 * U50 shares SPI2 with the pan MAX31865 and the MCP3202 but has no CS GPIO: its device is added with
 * spics_io_num = -1 and CS# is TCA9555 P06. A hold is spi_device_acquire_bus(portMAX_DELAY, the only wait
 * ESP-IDF 5.3 accepts) ... spi_device_release_bus. The monitor task (core 0, priority 23, above the UI)
 * runs it, so only the IPC task and interrupts preempt a hold. Hold = two 2-byte I2C writes at 400 kHz
 * plus a transfer of at most 4 bytes at 500 kHz: about 0.3 ms.
 */
#include "food_rtd.h"

#include <math.h>

#include "controller_board.h"
#include "controller_pins.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "rtd_food_service.h"

static const char *TAG = "food_rtd";
static spi_device_handle_t s_dev;
static rtd_food_service_t s_svc;
static bool s_ready;
static rtd_food_state_t s_logged = RTD_FOOD_NO_READING;

static bool link_lock(void *c) { (void)c; return spi_device_acquire_bus(s_dev, portMAX_DELAY) == ESP_OK; }
static void link_unlock(void *c) { (void)c; spi_device_release_bus(s_dev); }
static bool link_select(void *c, bool selected) { (void)c; return ctrl_board_food_cs(selected); }

static bool link_xfer(void *c, const uint8_t *tx, uint8_t *rx, size_t n)
{
    (void)c;
    spi_transaction_t t = {.length = 8u * n, .tx_buffer = tx, .rx_buffer = rx};
    return spi_device_polling_transmit(s_dev, &t) == ESP_OK;
}

static bool create(void)
{
    /* SPI2 is brought up by rtd_service at boot; until then this fails and is retried next tick. */
    spi_device_interface_config_t dc = {.mode = CTRL_RTD_SPI_MODE, .clock_speed_hz = 500000,
                                        .spics_io_num = -1, .queue_size = 1};
    if (spi_bus_add_device(SPI2_HOST, &dc, &s_dev) != ESP_OK) return false;
    if (!ctrl_board_food_cs_prepare()) {
        (void)spi_bus_remove_device(s_dev);
        s_dev = NULL;
        return false;
    }
    const rtd_food_link_t link = {.bus_lock = link_lock, .bus_unlock = link_unlock, .select = link_select,
                                  .xfer = link_xfer, .ctx = NULL};
    rtd_food_service_init(&s_svc, &link, NULL);
    return true;
}

void food_rtd_tick(void)
{
    if (!s_ready && !(s_ready = create())) return;
    rtd_food_service_tick(&s_svc, (uint64_t)esp_timer_get_time());
    rtd_food_state_t st = rtd_food_service_state(&s_svc, NULL);
    if (st != s_logged) {
        ESP_LOGW(TAG, "food probe state %d -> %d", (int)s_logged, (int)st);
        s_logged = st;
    }
}

rtd_food_state_t food_rtd_read(float *t_c)
{
    if (!s_ready) {
        if (t_c) *t_c = NAN;
        return RTD_FOOD_NO_READING;
    }
    return rtd_food_service_state(&s_svc, t_c);
}
