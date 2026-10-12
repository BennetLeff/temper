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
 *  - L3 blower (DECISIONS C28): LEDC on GPIO46 (duty 0 = full speed; the channel is configured at
 *    duty 0 and every failure stops it at idle level 0), PCNT on GPIO3 (FG rising edges), and
 *    expander P15 FAN_OFF (latch written 0 = on before the pin becomes an output). The speed and
 *    on/off decisions are blower_ctrl_step() in components/control/thermal_mgmt.c.
 */
#include "controller_board.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/spi_master.h"
#include "driver/ledc.h"
#include "driver/pulse_cnt.h"
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
static bool s_fan_off_output;  /* P15 configured as an output (latch 0 first) */
static bool s_fan_off_written; /* last FAN_OFF write succeeded */
static bool s_fan_off_last;
static bool s_ledc_ok;
static pcnt_unit_handle_t s_tach;
static uint16_t s_tach_total;
#define BLOWER_LEDC_MODE    LEDC_LOW_SPEED_MODE
#define BLOWER_LEDC_TIMER   LEDC_TIMER_0
#define BLOWER_LEDC_CHANNEL LEDC_CHANNEL_0

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
    /* L3: FAN_OFF (P15) becomes an output with its latch written 0 (blower on) first (C28). */
    ctrl_i2c_write_t w[6];
    size_t n = ctrl_exp_init_writes(true, w);
    for (size_t i = 0; i < n; i++)
        if (!exp_write(w[i].reg, w[i].value)) return false;
    s_fan_off_output = true;
    s_fan_off_written = true;
    s_fan_off_last = false;
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

static bool blower_create(void)
{
    /* LEDC at duty 0 = GPIO46 low = full speed: the same direction as reset (100 k pull-down). If
     * this fails the pad stays an input with the pull-down: the blower still runs (~11.2 V). */
    ledc_timer_config_t tc = {.speed_mode = BLOWER_LEDC_MODE, .duty_resolution = CTRL_BLOWER_LEDC_RES_BITS,
                              .timer_num = BLOWER_LEDC_TIMER, .freq_hz = CTRL_BLOWER_LEDC_FREQ_HZ,
                              .clk_cfg = LEDC_AUTO_CLK};
    ledc_channel_config_t cc = {.gpio_num = CTRL_GPIO_FAN_PWM, .speed_mode = BLOWER_LEDC_MODE,
                                .channel = BLOWER_LEDC_CHANNEL, .intr_type = LEDC_INTR_DISABLE,
                                .timer_sel = BLOWER_LEDC_TIMER, .duty = 0, .hpoint = 0};
    s_ledc_ok = ledc_timer_config(&tc) == ESP_OK && ledc_channel_config(&cc) == ESP_OK;
    /* PCNT: count FG rising edges; read and cleared every blower tick into a 16-bit total. */
    pcnt_unit_config_t uc = {.high_limit = 32767, .low_limit = -1};
    pcnt_glitch_filter_config_t fc = {.max_glitch_ns = CTRL_BLOWER_TACH_GLITCH_NS};
    pcnt_chan_config_t chc = {.edge_gpio_num = CTRL_GPIO_FAN_TACH, .level_gpio_num = -1};
    pcnt_channel_handle_t ch = NULL;
    bool tach_ok = pcnt_new_unit(&uc, &s_tach) == ESP_OK &&
                   pcnt_unit_set_glitch_filter(s_tach, &fc) == ESP_OK &&
                   pcnt_new_channel(s_tach, &chc, &ch) == ESP_OK &&
                   pcnt_channel_set_edge_action(ch, PCNT_CHANNEL_EDGE_ACTION_INCREASE,
                                                PCNT_CHANNEL_EDGE_ACTION_HOLD) == ESP_OK &&
                   pcnt_unit_enable(s_tach) == ESP_OK && pcnt_unit_clear_count(s_tach) == ESP_OK &&
                   pcnt_unit_start(s_tach) == ESP_OK;
    if (!tach_ok) s_tach = NULL; /* no tach: blower_ctrl_step() sees count_ok=false = stalled */
    return s_ledc_ok && tach_ok;
}

bool ctrl_board_init(void)
{
    s_pins_ok = ctrl_board_apply_pins(&s_ops);
    if (!s_pins_ok) ESP_LOGE(TAG, "GPIO setup failed (RUN_EN stays low by its pull-down)");
    bool i2c_ok = i2c_create();
    if (!i2c_ok) ESP_LOGE(TAG, "TCA9555 setup failed: SUP_RUN_OK and RTD_DRDY read as not ok");
    bool ui_ok = ui_bus_create();
    if (!ui_ok) ESP_LOGE(TAG, "UI SPI3 bus setup failed");
    bool blower_ok = blower_create();
    if (!blower_ok) ESP_LOGE(TAG, "blower LEDC/PCNT setup failed: blower at its full-speed default");
    return s_pins_ok && i2c_ok && ui_ok && blower_ok;
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

/* ---------------------------------------------------------------- blower (L3, C28) */
bool ctrl_board_blower_apply(bool on, uint32_t ledc_counts)
{
    bool ok = s_ledc_ok;
    if (s_ledc_ok) {
        uint32_t counts = on ? ledc_counts : 0u; /* off: duty 0, so a failed FAN_OFF runs full */
        if (ledc_set_duty(BLOWER_LEDC_MODE, BLOWER_LEDC_CHANNEL, counts) != ESP_OK ||
            ledc_update_duty(BLOWER_LEDC_MODE, BLOWER_LEDC_CHANNEL) != ESP_OK) {
            (void)ledc_stop(BLOWER_LEDC_MODE, BLOWER_LEDC_CHANNEL, 0); /* idle low = full speed */
            ok = false;
        }
    }
    /* FAN_OFF only when explicitly asked; rewrite on change or after a failed write. */
    bool off = !on;
    if (s_fan_off_output && s_exp && (!s_fan_off_written || off != s_fan_off_last)) {
        s_fan_off_written = exp_write(TCA9555_REG_OUTPUT1, ctrl_exp_output1(off));
        s_fan_off_last = off;
    }
    return ok && s_fan_off_output && s_fan_off_written;
}

bool ctrl_board_blower_tach_count(uint16_t *count)
{
    int v = 0;
    if (!s_tach || pcnt_unit_get_count(s_tach, &v) != ESP_OK || pcnt_unit_clear_count(s_tach) != ESP_OK)
        return false;
    s_tach_total = (uint16_t)(s_tach_total + (uint16_t)v); /* a pulse between get and clear is
                                                          * lost: the error reads slow (safe) */
    *count = s_tach_total;
    return true;
}
