/**
 * @file tca9555.c
 * @brief Minimal TCA9555 input read and the board's expander instance (see tca9555.h).
 */

#include "tca9555.h"

#include <string.h>

#include "temper_pins.h"

bool tca9555_read_port(const tca9555_bus_t *bus, uint8_t addr7, unsigned port, uint8_t *value)
{
    if (bus == NULL || bus->write_read == NULL || value == NULL || port > 1u) {
        return false;
    }
    const uint8_t cmd = port == 0u ? TCA9555_REG_INPUT0 : TCA9555_REG_INPUT1;
    uint8_t rx = 0u;
    if (!bus->write_read(bus->ctx, addr7, &cmd, 1u, &rx, 1u)) {
        return false;
    }
    *value = rx;
    return true;
}

bool tca9555_read_pin(const tca9555_bus_t *bus, uint8_t addr7, unsigned pin, bool *high)
{
    uint8_t v = 0u;
    if (high == NULL || pin > 15u || !tca9555_read_port(bus, addr7, pin / 8u, &v)) {
        return false;
    }
    *high = (v & (uint8_t)(1u << (pin % 8u))) != 0u;
    return true;
}

/* ---- board instance ------------------------------------------------------ */

static const tca9555_bus_t *s_bus;
static uint32_t s_reads;
static uint32_t s_failures;

#if defined(ESP_PLATFORM) && defined(TEMPER_EXPANDER_I2C_ADDR)
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static i2c_master_bus_handle_t s_i2c_bus;
static i2c_master_dev_handle_t s_i2c_dev;
static SemaphoreHandle_t s_i2c_lock;

static bool esp_write_read(void *ctx, uint8_t addr7, const uint8_t *tx, size_t ntx, uint8_t *rx, size_t nrx)
{
    (void)ctx;
    (void)addr7;   /* the device handle carries the address */
    if (s_i2c_dev == NULL || s_i2c_lock == NULL ||
        xSemaphoreTake(s_i2c_lock, pdMS_TO_TICKS(TCA9555_TIMEOUT_MS)) != pdTRUE) {
        return false;
    }
    const esp_err_t err = i2c_master_transmit_receive(s_i2c_dev, tx, ntx, rx, nrx, TCA9555_TIMEOUT_MS);
    xSemaphoreGive(s_i2c_lock);
    return err == ESP_OK;
}

static const tca9555_bus_t s_esp_bus = {.write_read = esp_write_read, .ctx = NULL};

hal_status_t tca9555_board_attach(void)
{
    if (s_bus != NULL) {
        return HAL_OK;
    }
    if (s_i2c_lock == NULL) {
        s_i2c_lock = xSemaphoreCreateMutex();
        if (s_i2c_lock == NULL) {
            return HAL_ERROR;
        }
    }
    /* Another owner may have created the bus already: share it. */
    if (i2c_master_get_bus_handle(I2C_NUM_0, &s_i2c_bus) != ESP_OK) {
        const i2c_master_bus_config_t bc = {
            .i2c_port = I2C_NUM_0,
            .sda_io_num = PIN_I2C_SDA,
            .scl_io_num = PIN_I2C_SCL,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .flags.enable_internal_pullup = true,   /* the board's 4.7 k pull-ups dominate */
        };
        if (i2c_new_master_bus(&bc, &s_i2c_bus) != ESP_OK) {
            return HAL_ERROR;
        }
    }
    const i2c_device_config_t dc = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = TEMPER_EXPANDER_I2C_ADDR,
        .scl_speed_hz = TCA9555_I2C_HZ,
    };
    if (i2c_master_bus_add_device(s_i2c_bus, &dc, &s_i2c_dev) != ESP_OK) {
        return HAL_ERROR;
    }
    s_bus = &s_esp_bus;
    return HAL_OK;
}
#else
hal_status_t tca9555_board_attach(void)
{
    /* Host builds: the test supplies the transport (tca9555_board_set_bus);
     * a target pin map without the expander has none. */
    return s_bus != NULL ? HAL_OK : HAL_ERROR_NOT_READY;
}
#endif

void tca9555_board_set_bus(const tca9555_bus_t *bus)
{
    s_bus = bus;
    s_reads = 0u;
    s_failures = 0u;
}

bool tca9555_board_read_pin(unsigned pin, bool *high)
{
#ifdef TEMPER_EXPANDER_I2C_ADDR
    s_reads++;
    if (s_bus == NULL || !tca9555_read_pin(s_bus, (uint8_t)TEMPER_EXPANDER_I2C_ADDR, pin, high)) {
        s_failures++;
        return false;
    }
    return true;
#else
    (void)pin;
    (void)high;
    return false;
#endif
}

uint32_t tca9555_board_reads(void) { return s_reads; }
uint32_t tca9555_board_failures(void) { return s_failures; }
