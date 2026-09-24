#include "power_entry_esp32_idf.h"

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

enum {
    PE_IDF_I2C_TIMEOUT_MS = 5,
    PE_IDF_UART_DRAIN_MS = 20,
    PE_IDF_UART_BAUD = 115200,
};

static i2c_master_bus_handle_t s_i2c_bus;
static i2c_master_dev_handle_t s_expander;
static bool s_uart_ready;
static QueueHandle_t s_uart_events;

static bool idf_output_low(void *context, int gpio) {
    (void)context;
    /* Configure the latch first. GPIO21 is not called during boot. */
    if (gpio_set_level((gpio_num_t)gpio, 0) != ESP_OK) return false;
    gpio_config_t config = {
        .pin_bit_mask = 1ULL << gpio,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&config) == ESP_OK;
}

static bool idf_input(void *context, int gpio) {
    (void)context;
    gpio_config_t config = {
        .pin_bit_mask = 1ULL << gpio,
        .mode = GPIO_MODE_INPUT,
        /* External button pull-up and physical safety signal drive these. */
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&config) == ESP_OK;
}

static bool idf_set_gpio(void *context, int gpio, bool high) {
    (void)context;
    return gpio_set_level((gpio_num_t)gpio, high ? 1 : 0) == ESP_OK;
}

static bool idf_read_gpio(void *context, int gpio, bool *high) {
    (void)context;
    int level = gpio_get_level((gpio_num_t)gpio);
    if (level < 0) return false;
    *high = level != 0;
    return true;
}

static bool idf_write_expander(void *context, uint8_t reg, uint8_t value) {
    (void)context;
    const uint8_t bytes[2] = {reg, value};
    return i2c_master_transmit(s_expander, bytes, sizeof(bytes),
                               PE_IDF_I2C_TIMEOUT_MS) == ESP_OK;
}

static bool idf_read_expander(void *context, uint8_t reg, uint8_t *value) {
    (void)context;
    return i2c_master_transmit_receive(s_expander, &reg, 1, value, 1,
                                       PE_IDF_I2C_TIMEOUT_MS) == ESP_OK;
}

static bool idf_cancel_uart(void *context) {
    (void)context;
    /* Candidate drain only. ESP-IDF documents FIFO empty, not cancellation
     * or final shift-register-bit completion. STOP_N must already be low. */
    return s_uart_ready &&
           uart_wait_tx_done(UART_NUM_1,
                             pdMS_TO_TICKS(PE_IDF_UART_DRAIN_MS)) == ESP_OK;
}

static bool idf_send_frame(void *context, const uint8_t *bytes, size_t length) {
    (void)context;
    if (!s_uart_ready ||
        uart_write_bytes(UART_NUM_1, bytes, length) != (int)length) return false;
    /* The API documents FIFO empty. Final bit completion needs target
     * capture before this can satisfy the synchronous START contract. */
    return uart_wait_tx_done(UART_NUM_1,
                             pdMS_TO_TICKS(PE_IDF_UART_DRAIN_MS)) == ESP_OK;
}

static uint64_t idf_now_ms(void *context) {
    (void)context;
    return (uint64_t)esp_timer_get_time() / 1000u;
}

bool pe_esp32_idf_boot(pe_esp32_adapter_t *adapter) {
    /* STOP must be the first actively configured pin. The external pull-down
     * is needed during the interval before this function can run. */
    if (!idf_output_low(NULL, PE_ESP_GPIO_STOP_N)) return false;

    i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = PE_ESP_GPIO_EXPANDER_SDA,
        .scl_io_num = PE_ESP_GPIO_EXPANDER_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false,
    };
    if (i2c_new_master_bus(&bus_config, &s_i2c_bus) != ESP_OK) return false;
    i2c_device_config_t device_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = PE_ESP_EXPANDER_ADDRESS_ADDR_LOW,
        .scl_speed_hz = 100000,
    };
    if (i2c_master_bus_add_device(s_i2c_bus, &device_config,
                                  &s_expander) != ESP_OK) return false;

    uart_config_t uart_config = {
        .baud_rate = PE_IDF_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    if (uart_param_config(UART_NUM_1, &uart_config) != ESP_OK ||
        uart_set_pin(UART_NUM_1, PE_ESP_GPIO_COMMAND_TX,
                     PE_ESP_GPIO_RESPONSE_RX,
                     UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) != ESP_OK ||
        uart_driver_install(UART_NUM_1, 256, 0, 16,
                            &s_uart_events, 0) != ESP_OK) return false;
    s_uart_ready = true;

    pe_esp32_adapter_ops_t ops = {
        .context = NULL,
        .configure_output_low = idf_output_low,
        .configure_input = idf_input,
        .set_gpio = idf_set_gpio,
        .read_gpio = idf_read_gpio,
        .write_expander = idf_write_expander,
        .read_expander = idf_read_expander,
        .cancel_uart_tx = idf_cancel_uart,
        .send_frame = idf_send_frame,
        .now_ms = idf_now_ms,
    };
    return pe_esp32_adapter_boot(adapter, ops);
}

int pe_esp32_idf_poll_byte(uint8_t *byte) {
    if (!s_uart_ready || byte == NULL) return -1;
    uart_event_t event;
    while (xQueueReceive(s_uart_events, &event, 0) == pdTRUE) {
        if (event.type == UART_FIFO_OVF ||
            event.type == UART_BUFFER_FULL ||
            event.type == UART_BREAK ||
            event.type == UART_PARITY_ERR ||
            event.type == UART_FRAME_ERR) {
            (void)uart_flush_input(UART_NUM_1);
            return -1;
        }
    }
    return uart_read_bytes(UART_NUM_1, byte, 1, 0);
}
