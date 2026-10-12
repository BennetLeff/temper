/*
 * UI board on J7 / SPI3 (zapote/controller DECISIONS C3, C26): SSD1322 OLED, MCP23S08 expander
 * (buttons, encoder, buzzer). ESP-IDF only; host doubles: firmware/test/state_machine_stubs.c.
 *
 * Threading: the state machine (control task) only writes small shared fields under s_mux
 * (display lines, buzzer mode, button enables) and reads the debounced inputs. Every SPI
 * transfer happens in the UI I/O task created here (1 ms poll, core 0, low priority), so the
 * control loop never waits on the UI bus. The SPI3 bus itself is created by ctrl_board_init()
 * (controller_board_esp32.c, SCK 40 / MOSI 41 / MISO 44, MISO pulled up).
 *
 * Fail-safe behaviour: with no UI board (or one that stops answering) every button reads
 * released and test_display_communication() fails; nothing here can cause heating.
 */
#if defined(ESP_PLATFORM)
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "controller_pins.h"
#include "platform_esp32.h"
#include "platform_logic.h"
#include "state_machine.h"
#include "ui_board_map.h"

extern uint32_t get_time_ms(void); /* platform_esp32.c */

static const char *TAG = "ui";

static spi_device_handle_t s_oled, s_exp;
static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
static bool s_init_done;

/* Shared with the control task (s_mux). */
static struct {
    char line1[32];
    char line2[32];
    bool dirty;
    led_pattern_t led;
    platform_buzzer_t buzzer;
    uint8_t inputs;      /* debounced GP levels; 0xFF = all released */
    int16_t enc_steps;   /* + = TEMP_UP pending, - = TEMP_DOWN pending */
    uint8_t enabled;     /* bit per button_id_t */
    bool present;
} s_ui = {.inputs = 0xFFu, .enabled = 0xFFu};

/* UI task only. */
static uint8_t s_fb[PLATFORM_OLED_FB_BYTES];
static platform_debounce_t s_deb;
static platform_quad_t s_quad;
static bool s_buzz_written, s_buzz_last;
static platform_ui_link_t s_link;    /* UI-lost tracker, under s_mux (UI task polls, control task takes the STOP) */

/* ---------------------------------------------------------------- MCP23S08 */
static bool exp_write(uint8_t reg, uint8_t v)
{
    uint8_t tx[3] = {UI_EXP_OPCODE_WRITE, reg, v};
    spi_transaction_t t = {.length = 24, .tx_buffer = tx};
    return s_exp && spi_device_polling_transmit(s_exp, &t) == ESP_OK;
}

static bool exp_read(uint8_t reg, uint8_t *v)
{
    uint8_t tx[3] = {UI_EXP_OPCODE_READ, reg, 0x00u}, rx[3] = {0};
    spi_transaction_t t = {.length = 24, .tx_buffer = tx, .rx_buffer = rx};
    if (!s_exp || spi_device_polling_transmit(s_exp, &t) != ESP_OK) return false;
    *v = rx[2];
    return true;
}

/* Buzzer latch 0 (off) before its pin becomes an output; then read the configuration back. An
 * absent board reads 0xFF on every register (MISO pull-up), which never matches UI_EXP_IODIR. */
static bool exp_configure(void)
{
    uint8_t iodir = 0, gppu = 0, olat = 0;
    /* OLAT first: buzzer 0, GP7 (TMP122 CS#) high, so neither output ever starts in the wrong level. */
    bool ok = exp_write(MCP23S08_IOCON, 0x00u) && exp_write(MCP23S08_OLAT, UI_EXP_OLAT_IDLE) &&
              exp_write(MCP23S08_IPOL, 0x00u) && exp_write(MCP23S08_GPPU, UI_EXP_GPPU) &&
              exp_write(MCP23S08_IODIR, UI_EXP_IODIR) && exp_read(MCP23S08_IODIR, &iodir) &&
              exp_read(MCP23S08_GPPU, &gppu) && exp_read(MCP23S08_OLAT, &olat);
    bool present = ok && iodir == UI_EXP_IODIR && gppu == UI_EXP_GPPU && olat == UI_EXP_OLAT_IDLE;
    s_buzz_written = present;
    s_buzz_last = false;
    return present;
}


/* ---------------------------------------------------------------- SSD1322 */
static bool oled_tx(bool data, const uint8_t *p, size_t n)
{
    if (n == 0) return true;
    if (gpio_set_level((gpio_num_t)CTRL_GPIO_UI_DC, data ? 1u : 0u) != ESP_OK) return false;
    spi_transaction_t t = {.length = 8u * n, .tx_buffer = p};
    return s_oled && spi_device_polling_transmit(s_oled, &t) == ESP_OK;
}

/* SSD1322: the command byte with D/C low, its parameters with D/C high. */
static bool oled_cmd(uint8_t c, const uint8_t *param, size_t n)
{
    return oled_tx(false, &c, 1) && oled_tx(true, param, n);
}

#define CMD(c, ...)                                                    \
    do {                                                               \
        static const uint8_t p_[] = {__VA_ARGS__};                     \
        ok = ok && oled_cmd((c), p_, sizeof p_);                       \
    } while (0)
#define CMD0(c) do { ok = ok && oled_cmd((c), NULL, 0); } while (0)

/* Initialisation for the NHD-3.12-25664UCW2 (SSD1322, 3.3 V jumper option, C3), after the
 * Newhaven example sequence. RES# is not driven by firmware (C26: an RC power-on reset on the UI
 * board, or the expander's spare bit, which is left an input with its pull-up = not in reset). */
static bool oled_init(void)
{
    bool ok = true;
    CMD(0xFD, 0x12);       /* command unlock */
    CMD0(0xAE);            /* display off */
    CMD(0xB3, 0x91);       /* clock divider / oscillator */
    CMD(0xCA, 0x3F);       /* multiplex ratio 64 */
    CMD(0xA2, 0x00);       /* display offset */
    CMD(0xA1, 0x00);       /* start line */
    CMD(0xA0, 0x14, 0x11); /* remap: horizontal increment, nibble remap, dual COM */
    CMD(0xB5, 0x00);       /* GPIO disabled */
    CMD(0xAB, 0x01);       /* internal VDD regulator */
    CMD(0xB4, 0xA0, 0xFD); /* display enhancement A: external VSL */
    CMD(0xC1, 0x9F);       /* contrast current */
    CMD(0xC7, 0x0F);       /* master contrast */
    CMD0(0xB9);            /* default linear grey scale */
    CMD(0xB1, 0xE2);       /* phase lengths */
    CMD(0xD1, 0x82, 0x20); /* display enhancement B */
    CMD(0xBB, 0x1F);       /* pre-charge voltage */
    CMD(0xB6, 0x08);       /* second pre-charge period */
    CMD(0xBE, 0x07);       /* VCOMH */
    CMD0(0xA6);            /* normal display */
    CMD0(0xA9);            /* exit partial display */
    CMD0(0xAF);            /* display on */
    return ok;
}

static bool oled_window(void)
{
    bool ok = true;
    CMD(0x15, SSD1322_COL_START, SSD1322_COL_END);
    CMD(0x75, SSD1322_ROW_START, SSD1322_ROW_END);
    CMD0(0x5C); /* write RAM; the frame follows with D/C high */
    return ok;
}

/* ---------------------------------------------------------------- UI I/O task */
static void ui_io_task(void *arg)
{
    (void)arg;
    uint32_t last_presence = 0, last_frame = 0;
    size_t frame_off = 0;
    bool frame_busy = false;
    bool present = false;
    bool oled_pending = false; /* re-acquired: wait UI_OLED_POWERUP_WAIT_MS before the first OLED write */
    uint32_t oled_ready_at = 0;

    portENTER_CRITICAL(&s_mux);
    present = s_ui.present;
    portEXIT_CRITICAL(&s_mux);

    for (;;) {
        uint32_t now = get_time_ms();

        /* Lost board: try to re-acquire once per UI_PRESENCE_MS. Loss itself is detected per poll below. */
        if (!present && now - last_presence >= UI_PRESENCE_MS) {
            last_presence = now;
            present = exp_configure();
            if (present) {
                platform_debounce_init(&s_deb);
                platform_quad_init(&s_quad);
                portENTER_CRITICAL(&s_mux);
                platform_ui_link_reacquired(&s_link, now); /* keeps a latched STOP until it is taken */
                portEXIT_CRITICAL(&s_mux);
                oled_pending = true; /* U12/U14.3: the OLED RC reset may be fresh */
                oled_ready_at = now + UI_OLED_POWERUP_WAIT_MS;
                frame_busy = false;
                ESP_LOGI(TAG, "UI board present");
            }
        }
        if (present && oled_pending && (int32_t)(now - oled_ready_at) >= 0) {
            (void)oled_init();
            oled_pending = false;
            portENTER_CRITICAL(&s_mux);
            s_ui.dirty = true;
            portEXIT_CRITICAL(&s_mux);
        }

        uint8_t stable = 0xFFu;
        int steps = 0;
        bool buzz = false;
        if (present) {
            /* A valid poll = the GPIO read worked AND the IODIR read-back is the configured value (a
             * power loss resets it to 0xFF; a stuck MISO reads 0x00 / 0xFF). One bad poll only skips
             * the sample; UI_LOST_STOP_MS without a good one is "UI lost". */
            uint8_t raw = 0xFFu, iodir = 0xFFu;
            bool ok = exp_read(MCP23S08_GPIO, &raw) && exp_read(MCP23S08_IODIR, &iodir) &&
                      iodir == UI_EXP_IODIR;
            portENTER_CRITICAL(&s_mux);
            bool lost = platform_ui_link_poll(&s_link, now, ok, UI_LOST_STOP_MS);
            portEXIT_CRITICAL(&s_mux);
            if (ok) {
                stable = platform_debounce_step(&s_deb, raw, UI_DEBOUNCE_POLLS);
                steps = platform_quad_step(&s_quad, (raw & UI_BIT_ENC_A) != 0, (raw & UI_BIT_ENC_B) != 0);
            } else if (lost) {
                present = false; /* lost: buttons read released, STOP request latched */
                ESP_LOGE(TAG, "UI board lost > %u ms: STOP requested", (unsigned)UI_LOST_STOP_MS);
                last_presence = now;
            } else {
                stable = s_ui.inputs; /* keep the last debounced state through a short glitch */
            }
        }

        portENTER_CRITICAL(&s_mux);
        s_ui.present = present;
        s_ui.inputs = present ? stable : 0xFFu;
        if (!present) {
            s_ui.enc_steps = 0;
        } else if (steps > 0 && s_ui.enc_steps < 100) {
            s_ui.enc_steps++;
        } else if (steps < 0 && s_ui.enc_steps > -100) {
            s_ui.enc_steps--;
        }
        buzz = platform_buzzer_output(&s_ui.buzzer, now);
        portEXIT_CRITICAL(&s_mux);

        if (present && (!s_buzz_written || buzz != s_buzz_last)) {
            s_buzz_written = exp_write(MCP23S08_OLAT, (uint8_t)(UI_EXP_OLAT_IDLE | (buzz ? UI_BIT_BUZZER : 0x00u)));
            s_buzz_last = buzz;
        }

        /* Screen: render when dirty, then one chunk per poll. */
        if (present && !oled_pending && !frame_busy && now - last_frame >= UI_FRAME_MIN_MS) {
            char l1[32], l2[32];
            bool dirty;
            portENTER_CRITICAL(&s_mux);
            dirty = s_ui.dirty;
            s_ui.dirty = false;
            memcpy(l1, s_ui.line1, sizeof l1);
            memcpy(l2, s_ui.line2, sizeof l2);
            portEXIT_CRITICAL(&s_mux);
            if (dirty) {
                platform_oled_render(s_fb, l1, l2);
                frame_busy = oled_window();
                frame_off = 0;
                last_frame = now;
            }
        } else if (present && !oled_pending && frame_busy) {
            size_t n = sizeof s_fb - frame_off;
            if (n > UI_FRAME_CHUNK) n = UI_FRAME_CHUNK;
            if (!oled_tx(true, &s_fb[frame_off], n)) {
                frame_busy = false;
                portENTER_CRITICAL(&s_mux);
                s_ui.dirty = true; /* retry the whole frame */
                portEXIT_CRITICAL(&s_mux);
            } else {
                frame_off += n;
                if (frame_off >= sizeof s_fb) frame_busy = false;
            }
        }

        vTaskDelay(pdMS_TO_TICKS(UI_POLL_PERIOD_MS));
    }
}

bool platform_ui_init(void)
{
    if (s_init_done) return platform_ui_present();
    s_init_done = true;

    spi_device_interface_config_t oled = {.mode = UI_SPI_MODE, .clock_speed_hz = UI_OLED_SPI_CLOCK_HZ,
                                          .spics_io_num = CTRL_GPIO_UI_CS_OLED_N, .queue_size = 1};
    /* Expander (and a future TMP122) at <= 5 MHz, OLED at 8 MHz (U13). */
    spi_device_interface_config_t exp = {.mode = UI_SPI_MODE, .clock_speed_hz = UI_EXP_SPI_CLOCK_HZ,
                                         .spics_io_num = CTRL_GPIO_UI_CS_EXP_N, .queue_size = 1};
    if (spi_bus_add_device(SPI3_HOST, &oled, &s_oled) != ESP_OK) s_oled = NULL;
    if (spi_bus_add_device(SPI3_HOST, &exp, &s_exp) != ESP_OK) s_exp = NULL;
    if (!s_oled || !s_exp) {
        ESP_LOGE(TAG, "UI SPI3 devices not added (bus missing?): no UI");
        return false;
    }

    bool present = exp_configure();
    if (present) {
        platform_debounce_init(&s_deb);
        platform_quad_init(&s_quad);
        /* U12/U14.3: first OLED write no earlier than 30 ms after UI power-up; the UI rail is on from
         * controller power-up, so time since boot is a lower bound. */
        uint32_t wait = platform_ui_powerup_wait_remaining_ms(get_time_ms(), 0u, UI_OLED_POWERUP_WAIT_MS);
        if (wait > 0u) vTaskDelay(pdMS_TO_TICKS(wait) + 1u);
        if (!oled_init()) ESP_LOGE(TAG, "SSD1322 init transfer failed");
    } else {
        ESP_LOGE(TAG, "MCP23S08 not answering on CS_EXP# (GPIO%d): UI board absent", CTRL_GPIO_UI_CS_EXP_N);
    }
    portENTER_CRITICAL(&s_mux);
    platform_ui_link_init(&s_link, get_time_ms());
    s_ui.present = present;
    s_ui.dirty = true;
    portEXIT_CRITICAL(&s_mux);

    if (xTaskCreatePinnedToCore(ui_io_task, "ui_io", 3072, NULL, 2, NULL, 0) != pdPASS) {
        ESP_LOGE(TAG, "UI I/O task not created");
        portENTER_CRITICAL(&s_mux);
        s_ui.present = false;
        portEXIT_CRITICAL(&s_mux);
        return false;
    }
    return present;
}

bool platform_ui_present(void)
{
    portENTER_CRITICAL(&s_mux);
    bool p = s_ui.present;
    portEXIT_CRITICAL(&s_mux);
    return p;
}

/* ---------------------------------------------------------------- state machine API */
static void set_line(char *dst, size_t n, const char *s)
{
    size_t i = 0;
    for (; s && s[i] && i + 1 < n; i++) dst[i] = s[i];
    dst[i] = '\0';
}

void display_show_message(const char *msg)
{
    portENTER_CRITICAL(&s_mux);
    set_line(s_ui.line1, sizeof s_ui.line1, msg);
    s_ui.dirty = true;
    portEXIT_CRITICAL(&s_mux);
}

void display_update_temperature(float temp)
{
    char b[16];
    platform_fmt_temperature(b, sizeof b, temp);
    portENTER_CRITICAL(&s_mux);
    if (strcmp(b, s_ui.line2) != 0) {
        set_line(s_ui.line2, sizeof s_ui.line2, b);
        s_ui.dirty = true;
    }
    portEXIT_CRITICAL(&s_mux);
}

void display_update_countdown(uint16_t seconds)
{
    char b[16];
    platform_fmt_countdown(b, sizeof b, seconds);
    portENTER_CRITICAL(&s_mux);
    if (strcmp(b, s_ui.line2) != 0) {
        set_line(s_ui.line2, sizeof s_ui.line2, b);
        s_ui.dirty = true;
    }
    portEXIT_CRITICAL(&s_mux);
}

void display_show_fault(fault_code_t code)
{
    const char *name = state_machine_get_fault_string(code);
    portENTER_CRITICAL(&s_mux);
    set_line(s_ui.line1, sizeof s_ui.line1, "FAULT");
    set_line(s_ui.line2, sizeof s_ui.line2, name);
    s_ui.dirty = true;
    portEXIT_CRITICAL(&s_mux);
}

void buzzer_beep(uint32_t duration_ms)
{
    uint32_t now = get_time_ms();
    portENTER_CRITICAL(&s_mux);
    platform_buzzer_beep(&s_ui.buzzer, now, duration_ms);
    portEXIT_CRITICAL(&s_mux);
}

void buzzer_beep_continuous(void)
{
    portENTER_CRITICAL(&s_mux);
    platform_buzzer_continuous(&s_ui.buzzer);
    portEXIT_CRITICAL(&s_mux);
}

void buzzer_stop(void)
{
    portENTER_CRITICAL(&s_mux);
    platform_buzzer_stop(&s_ui.buzzer);
    portEXIT_CRITICAL(&s_mux);
}

bool button_is_pressed(button_id_t button)
{
    bool pressed = false;
    portENTER_CRITICAL(&s_mux);
    uint8_t in = s_ui.inputs;
    bool enabled = (s_ui.enabled & (1u << (unsigned)button)) != 0;
    /* UI lost for > UI_LOST_STOP_MS: STOP reads pressed (even if disabled) until the loss has been
     * reported once after recovery; the state machine's existing stop path ends heating and START
     * still needs a deliberate press (never an auto-restart). */
    if (button == BUTTON_STOP && platform_ui_link_take_stop(&s_link)) {
        pressed = true;
    } else if (s_ui.present && enabled) {
        switch (button) {
        case BUTTON_START: pressed = (in & UI_BIT_BTN_START) == 0; break;
        case BUTTON_STOP: pressed = (in & UI_BIT_BTN_STOP) == 0; break;
        case BUTTON_BACK: pressed = (in & UI_BIT_BTN_BACK) == 0; break;
        /* One encoder detent = one TEMP_UP / TEMP_DOWN press, consumed by the read. */
        case BUTTON_TEMP_UP:
            if (s_ui.enc_steps > 0) { s_ui.enc_steps--; pressed = true; }
            break;
        case BUTTON_TEMP_DOWN:
            if (s_ui.enc_steps < 0) { s_ui.enc_steps++; pressed = true; }
            break;
        default: break;
        }
    }
    portEXIT_CRITICAL(&s_mux);
    return pressed;
}

void button_set_enabled(button_id_t button, bool enabled)
{
    if ((unsigned)button >= 8u) return;
    portENTER_CRITICAL(&s_mux);
    if (enabled) s_ui.enabled |= (uint8_t)(1u << (unsigned)button);
    else s_ui.enabled &= (uint8_t)~(1u << (unsigned)button);
    portEXIT_CRITICAL(&s_mux);
}

/* No indicator LED exists on this hardware: C26 deleted J5/J6/J8 and the UI board's MCP23S08 bits
 * are allocated to buttons, encoder, buzzer and a local CS/reset. The pattern is kept for
 * diagnostics only; the OLED carries the state text. */
void led_set_pattern(led_pattern_t pattern)
{
    portENTER_CRITICAL(&s_mux);
    s_ui.led = pattern;
    portEXIT_CRITICAL(&s_mux);
}

#endif /* ESP_PLATFORM */
