#ifndef TEMPER_POWER_ENTRY_ESP32_ADAPTER_H
#define TEMPER_POWER_ENTRY_ESP32_ADAPTER_H

#include "power_entry_source_runtime.h"
#include "temper_pins.h"

/* Rev38 N8R8 module pin screen. These numbers are candidate GPIOs until the
 * joined electrical netlist and target boot capture establish ownership. */
enum {
    PE_ESP_GPIO_STOP_N = 13,
    PE_ESP_GPIO_WDI_REQUEST = 21,
    PE_ESP_GPIO_PERMIT_SET = 48,
    PE_ESP_GPIO_COOKER_RESET_REQUEST = PIN_RESET_INPUT,
    PE_ESP_GPIO_PREWATCHDOG_OK = PIN_POWER_ENTRY_PREWATCHDOG_OK,
    PE_ESP_GPIO_COMMAND_TX = 40,
    PE_ESP_GPIO_RESPONSE_RX = 41,
    PE_ESP_GPIO_START_BUTTON = 42,
    PE_ESP_GPIO_EXPANDER_SDA = PIN_I2C_SDA,
    PE_ESP_GPIO_EXPANDER_SCL = PIN_I2C_SCL,
    PE_ESP_EXPANDER_ADDRESS_ADDR_LOW = 0x20,
};

typedef struct {
    void *context;
    /* Must load a low output latch BEFORE enabling output direction. */
    bool (*configure_output_low)(void *context, int gpio);
    bool (*configure_input)(void *context, int gpio);
    bool (*set_gpio)(void *context, int gpio, bool high);
    bool (*read_gpio)(void *context, int gpio, bool *high);
    /* Complete bounded I2C transactions, no deferred queue. */
    bool (*write_expander)(void *context, uint8_t reg, uint8_t value);
    bool (*read_expander)(void *context, uint8_t reg, uint8_t *value);
    bool (*cancel_uart_tx)(void *context);
    bool (*send_frame)(void *context, const uint8_t *bytes, size_t length);
    uint64_t (*now_ms)(void *context);
} pe_esp32_adapter_ops_t;

typedef struct {
    pe_esp32_adapter_ops_t ops;
    uint8_t output_shadow;
    bool booted;
    bool fault;
    bool wdi_configured;
} pe_esp32_adapter_t;

/* STOP first; never touch WDI at boot. Set the TCA6408A output latch low
 * and verify it before enabling P0-P2 as outputs. A CPU-only reset can retain
 * old expander outputs until these synchronous writes succeed, so external
 * hardware must independently bound the unsafe interval. */
bool pe_esp32_adapter_boot(pe_esp32_adapter_t *adapter,
                           pe_esp32_adapter_ops_t ops);
pe_source_runtime_io_t pe_esp32_adapter_runtime_io(pe_esp32_adapter_t *adapter,
                                                    uint32_t start_bound_ms,
                                                    uint32_t wdi_bound_ms,
                                                    uint32_t control_bound_ms);
void pe_esp32_adapter_force_stop(pe_esp32_adapter_t *adapter);

#endif
