/*
 * ESP-IDF glue for the integrated SELV controller board layer (controller_board.h).
 * Target: ESP-IDF v5.2.x. NOT YET COMPILED against ESP-IDF or run on hardware, like
 * components/power/n21_hw_esp32.c: every decision lives in controller_board.c (host-tested); this
 * file only moves bits.
 *
 *  - ctrl_board_init(): RUN_EN preset low and made an output first, then IL_WDI and UI D/C (both
 *    preset low); the I2C master on SDA GPIO37 / SCL GPIO0 with the internal pull-ups OFF (the
 *    board fits 4.7 k); the TCA9555 register plan; the UI SPI3 bus on 40/41/44 (DECISIONS C26).
 *  - GPIO0 is the SPI-boot strap. The bus only drives SCL low inside a transaction, the TCA9555
 *    never stretches the clock, and any reset returns the pad to an input so the 4.7 k restores
 *    the high level. No internal pull-down is ever enabled on it.
 *  - GPIO44 is U0RXD on the module. It is UI MISO here, so the console must be USB-Serial-JTAG
 *    (sdkconfig.defaults, CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG). The UART0 driver is never
 *    installed.
 *  - The expander is polled by the control task (ctrl_board_poll_expander, every 10 ms). Readers in
 *    other tasks take a copy of the cache; a failed or stale read is "not ok" for every consumer.
 */
#include "controller_board.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"

static const char *TAG = "ctrl_board";

static i2c_master_bus_handle_t s_i2c_bus;
static i2c_master_dev_handle_t s_exp;
static portMUX_TYPE s_exp_mux = portMUX_INITIALIZER_UNLOCKED;
static ctrl_exp_cache_t s_exp_cache;
static bool s_pins_ok;
static ctrl_run_en_t s_run_en;
static portMUX_TYPE s_run_en_mux = portMUX_INITIALIZER_UNLOCKED;

static bool esp_set_level(void *ctx, int gpio, int level)
{
    (void)ctx;
    return gpio_set_level((gpio_num_t)gpio, (uint32_t)level) == ESP_OK;
}

static bool esp_config(void *ctx, int gpio, bool output, ctrl_pull_t pull)
{
    (void)ctx;
    gpio_config_t c = {
        .pin_bit_mask = 1ULL << gpio,
        /* Outputs keep the input path so a read-back sees the pad level. */
        .mode = output ? GPIO_MODE_INPUT_OUTPUT : GPIO_MODE_INPUT,
        .pull_up_en = pull == CTRL_PULL_UP ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = pull == CTRL_PULL_DOWN ? GPIO_PULLDOWN_ENABLE : GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&c) == ESP_OK;
}

static const ctrl_gpio_ops_t s_ops = {.set_level = esp_set_level, .config = esp_config, .ctx = NULL};

static bool exp_write(uint8_t reg, uint8_t value)
{
    uint8_t b[2] = {reg, value};
    return i2c_master_transmit(s_exp, b, sizeof b, 5) == ESP_OK;
}

static bool i2c_create(void)
{
    i2c_master_bus_config_t bc = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = CTRL_GPIO_I2C_SDA,
        .scl_io_num = CTRL_GPIO_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false, /* 4.7 k on the board; GPIO0 is a strap */
    };
    if (i2c_new_master_bus(&bc, &s_i2c_bus) != ESP_OK) return false;
    i2c_device_config_t dc = {.dev_addr_length = I2C_ADDR_BIT_LEN_7,
                              .device_address = CTRL_TCA9555_ADDR, .scl_speed_hz = CTRL_I2C_HZ};
    if (i2c_master_bus_add_device(s_i2c_bus, &dc, &s_exp) != ESP_OK) return false;
    /* L3 blower driver is a stub: FAN_OFF stays an input, so the 10 k gate pull-down keeps the
     * blower running (C28). */
    ctrl_i2c_write_t w[6];
    size_t n = ctrl_exp_init_writes(false, w);
    for (size_t i = 0; i < n; i++)
        if (!exp_write(w[i].reg, w[i].value)) return false;
    return true;
}

static bool ui_bus_create(void)
{
    spi_bus_config_t bus = {.sclk_io_num = CTRL_GPIO_UI_SCK, .mosi_io_num = CTRL_GPIO_UI_MOSI,
                            .miso_io_num = CTRL_GPIO_UI_MISO, .quadwp_io_num = -1,
                            .quadhd_io_num = -1, .max_transfer_sz = 512};
    if (spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_CH_AUTO) != ESP_OK) return false;
    /* CS_OLED# (47) and CS_EXP# (48) are added by the UI driver as spics_io_num; they have 10 k
     * pull-ups on the board. MISO: weak pull-up so an unplugged UI board reads 1s. */
    return gpio_pullup_en((gpio_num_t)CTRL_GPIO_UI_MISO) == ESP_OK;
}

bool ctrl_board_init(void)
{
    s_pins_ok = ctrl_board_apply_pins(&s_ops);
    if (!s_pins_ok) ESP_LOGE(TAG, "GPIO setup failed (RUN_EN stays low by its pull-down)");
    bool i2c_ok = i2c_create();
    if (!i2c_ok) ESP_LOGE(TAG, "TCA9555 setup failed: SUP_RUN_OK and RTD_DRDY read as not ok");
    bool ui_ok = ui_bus_create();
    if (!ui_ok) ESP_LOGE(TAG, "UI SPI3 bus setup failed");
    return s_pins_ok && i2c_ok && ui_ok;
}

bool ctrl_board_set_run_en(bool on)
{
    if (!s_pins_ok && on) return false; /* never claim permission on an unconfigured pad */
    portENTER_CRITICAL(&s_run_en_mux);
    bool ok = ctrl_run_en_request(&s_run_en, &s_ops, on);
    portEXIT_CRITICAL(&s_run_en_mux);
    /* Read-back of the pad (input path kept enabled): a stuck pad is reported, not trusted. */
    return ok && gpio_get_level((gpio_num_t)CTRL_GPIO_RUN_EN) == (on ? 1 : 0);
}

bool ctrl_board_run_en_kill(void)
{
    portENTER_CRITICAL(&s_run_en_mux);
    bool ok = ctrl_run_en_kill(&s_run_en, &s_ops);
    portEXIT_CRITICAL(&s_run_en_mux);
    return ok;
}

bool ctrl_board_poll_expander(void)
{
    uint8_t reg = TCA9555_REG_INPUT0, rx[2] = {0};
    bool ok = s_exp && i2c_master_transmit_receive(s_exp, &reg, 1, rx, sizeof rx, 2) == ESP_OK;
    uint64_t now = (uint64_t)esp_timer_get_time();
    portENTER_CRITICAL(&s_exp_mux);
    /* A failed read keeps the last snapshot and its time stamp, so one bus glitch is tolerated
     * and a sustained failure ages out past CTRL_EXP_MAX_AGE_US (consumers then read "not ok"). */
    if (ok) {
        s_exp_cache.raw = (uint16_t)(rx[0] | (rx[1] << 8));
        s_exp_cache.t_us = now;
        s_exp_cache.valid = true;
    }
    portEXIT_CRITICAL(&s_exp_mux);
    return ok;
}

bool ctrl_board_expander(ctrl_exp_cache_t *out)
{
    portENTER_CRITICAL(&s_exp_mux);
    *out = s_exp_cache;
    portEXIT_CRITICAL(&s_exp_mux);
    return out->valid;
}

/* ---------------------------------------------------------------- blower (STUB, controller L3) */
bool ctrl_board_blower_drive(bool on, float drive)
{
    (void)on;
    (void)drive;
    /* TODO(controller L3): LEDC on CTRL_GPIO_FAN_PWM (never an internal pull-up: strap) and the
     * expander FAN_OFF bit via ctrl_exp_init_writes(true, ...), output latch written first. */
    return false;
}

bool ctrl_board_blower_tach_hz(float *hz)
{
    /* TODO(controller L3): PCNT on CTRL_GPIO_FAN_TACH (strap only with an eFuse; input only). */
    *hz = 0.0f;
    return false;
}
