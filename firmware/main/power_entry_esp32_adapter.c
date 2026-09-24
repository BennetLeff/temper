#include "power_entry_esp32_adapter.h"

#include <string.h>

enum {
    TCA_INPUT = 0x00,
    TCA_OUTPUT = 0x01,
    TCA_POLARITY = 0x02,
    TCA_CONFIG = 0x03,
    TCA_OUTPUTS_LOW = 0x00,
    TCA_CONFIG_P0_P2_OUTPUT = 0xf8,
};

static void fault(pe_esp32_adapter_t *adapter) {
    adapter->fault = true;
    if (adapter->ops.set_gpio != NULL) {
        (void)adapter->ops.set_gpio(adapter->ops.context,
                                    PE_ESP_GPIO_STOP_N, false);
    }
    if (adapter->ops.cancel_uart_tx != NULL) {
        (void)adapter->ops.cancel_uart_tx(adapter->ops.context);
    }
}

void pe_esp32_adapter_force_stop(pe_esp32_adapter_t *adapter) {
    fault(adapter);
}

static bool checked_expander_write(pe_esp32_adapter_t *adapter,
                                   uint8_t reg, uint8_t value) {
    uint8_t observed = 0;
    if (!adapter->ops.write_expander(adapter->ops.context, reg, value) ||
        !adapter->ops.read_expander(adapter->ops.context, reg, &observed) ||
        observed != value) {
        fault(adapter);
        return false;
    }
    return true;
}

bool pe_esp32_adapter_boot(pe_esp32_adapter_t *adapter,
                           pe_esp32_adapter_ops_t ops) {
    memset(adapter, 0, sizeof(*adapter));
    adapter->ops = ops;
    if (ops.configure_output_low == NULL || ops.configure_input == NULL ||
        ops.set_gpio == NULL || ops.read_gpio == NULL ||
        ops.write_expander == NULL || ops.read_expander == NULL ||
        ops.cancel_uart_tx == NULL || ops.send_frame == NULL ||
        ops.now_ms == NULL) {
        fault(adapter);
        return false;
    }
    /* The direct external STOP pull-down is necessary before code executes.
     * GPIO setup only maintains that already-asserted hardware state. */
    if (!ops.configure_output_low(ops.context, PE_ESP_GPIO_STOP_N)) {
        fault(adapter);
        return false;
    }
    if (!ops.cancel_uart_tx(ops.context) ||
        !ops.configure_output_low(ops.context, PE_ESP_GPIO_PERMIT_SET) ||
        /* Release GPIO14 to the external supervisor. A reset pulse needs a
         * separate verified open-drain owner; never drive this node high. */
        !ops.configure_input(ops.context,
                             PE_ESP_GPIO_COOKER_RESET_REQUEST) ||
        !ops.configure_input(ops.context, PE_ESP_GPIO_PREWATCHDOG_OK) ||
        !ops.configure_input(ops.context, PE_ESP_GPIO_START_BUTTON)) {
        fault(adapter);
        return false;
    }
    /* TCA6408A: POR output latch 0xff and direction 0xff. On CPU-only
     * reset either register may instead retain its previous value. */
    if (!checked_expander_write(adapter, TCA_OUTPUT, TCA_OUTPUTS_LOW) ||
        !checked_expander_write(adapter, TCA_POLARITY, 0x00) ||
        !checked_expander_write(adapter, TCA_CONFIG,
                                TCA_CONFIG_P0_P2_OUTPUT)) return false;
    adapter->output_shadow = TCA_OUTPUTS_LOW;
    adapter->booted = true;
    return true;
}

static bool set_expander_bit(pe_esp32_adapter_t *adapter, uint8_t bit,
                             bool high) {
    uint8_t next = high ? (uint8_t)(adapter->output_shadow | (1u << bit))
                        : (uint8_t)(adapter->output_shadow & ~(1u << bit));
    if (!checked_expander_write(adapter, TCA_OUTPUT, next)) return false;
    adapter->output_shadow = next;
    return true;
}

static uint64_t adapter_now_ms(void *context) {
    pe_esp32_adapter_t *adapter = context;
    return adapter->ops.now_ms(adapter->ops.context);
}

static bool adapter_sample(void *context, pe_source_inputs_t *inputs) {
    pe_esp32_adapter_t *adapter = context;
    uint8_t config, polarity, output, port;
    bool safety_ok, button_high;
    memset(inputs, 0, sizeof(*inputs));
    if (!adapter->booted || adapter->fault ||
        !adapter->ops.read_expander(adapter->ops.context, TCA_CONFIG, &config) ||
        config != TCA_CONFIG_P0_P2_OUTPUT ||
        !adapter->ops.read_expander(adapter->ops.context, TCA_POLARITY, &polarity) ||
        polarity != 0 ||
        !adapter->ops.read_expander(adapter->ops.context, TCA_OUTPUT, &output) ||
        output != adapter->output_shadow ||
        !adapter->ops.read_expander(adapter->ops.context, TCA_INPUT, &port) ||
        !adapter->ops.read_gpio(adapter->ops.context,
                                PE_ESP_GPIO_PREWATCHDOG_OK, &safety_ok) ||
        !adapter->ops.read_gpio(adapter->ops.context,
                                PE_ESP_GPIO_START_BUTTON, &button_high)) {
        fault(adapter);
        return false;
    }
    inputs->rail_good = (port & (1u << 3)) != 0;
    inputs->local_permit_q = (port & (1u << 4)) != 0;
    inputs->hot_permit = (port & (1u << 5)) != 0;
    inputs->hot_session_q = (port & (1u << 6)) != 0;
    inputs->permit_seen_q = (port & (1u << 7)) != 0;
    inputs->safety_ok = safety_ok;
    inputs->start_button_pressed = !button_high;
    return true;
}

static bool adapter_set_level(void *context, pe_source_pin_t pin, bool high) {
    pe_esp32_adapter_t *adapter = context;
    bool ok = false;
    if (!adapter->booted || adapter->fault) return false;
    switch (pin) {
    case PE_SOURCE_PIN_STOP_N:
        ok = adapter->ops.set_gpio(adapter->ops.context,
                                   PE_ESP_GPIO_STOP_N, high);
        break;
    case PE_SOURCE_PIN_CHALLENGE_ACTIVE:
        ok = set_expander_bit(adapter, 0, high);
        break;
    case PE_SOURCE_PIN_SEEN_RESET_REQUEST:
        ok = set_expander_bit(adapter, 1, high);
        break;
    case PE_SOURCE_PIN_PERMIT_SET_REQUEST:
        ok = adapter->ops.set_gpio(adapter->ops.context,
                                   PE_ESP_GPIO_PERMIT_SET, high);
        break;
    case PE_SOURCE_PIN_WDI_HEARTBEAT:
    case PE_SOURCE_PIN_COUNT:
        return false;
    }
    if (!ok) fault(adapter);
    return ok;
}

static bool adapter_pulse(void *context, pe_source_pin_t pin) {
    pe_esp32_adapter_t *adapter = context;
    if (!adapter->booted || adapter->fault) return false;
    if (pin == PE_SOURCE_PIN_WDI_HEARTBEAT) {
        /* First access after boot loads low before output direction. The
         * external one-shot responds only to the subsequent positive edge. */
        if (!adapter->wdi_configured) {
            if (!adapter->ops.configure_output_low(adapter->ops.context,
                                                  PE_ESP_GPIO_WDI_REQUEST)) {
                fault(adapter);
                return false;
            }
            adapter->wdi_configured = true;
        }
        if (!adapter->ops.set_gpio(adapter->ops.context,
                                   PE_ESP_GPIO_WDI_REQUEST, false) ||
            !adapter->ops.set_gpio(adapter->ops.context,
                                   PE_ESP_GPIO_WDI_REQUEST, true) ||
            !adapter->ops.set_gpio(adapter->ops.context,
                                   PE_ESP_GPIO_WDI_REQUEST, false)) {
            fault(adapter);
            return false;
        }
        return true;
    }
    if (pin != PE_SOURCE_PIN_SEEN_RESET_REQUEST &&
        pin != PE_SOURCE_PIN_PERMIT_SET_REQUEST) return false;
    if (!adapter_set_level(context, pin, false) ||
        !adapter_set_level(context, pin, true) ||
        !adapter_set_level(context, pin, false)) {
        fault(adapter);
        return false;
    }
    return true;
}

static bool adapter_cancel_uart(void *context) {
    pe_esp32_adapter_t *adapter = context;
    return adapter->ops.cancel_uart_tx(adapter->ops.context);
}

static bool adapter_send_frame(void *context, const uint8_t *bytes,
                               size_t length) {
    pe_esp32_adapter_t *adapter = context;
    if (!adapter->booted || adapter->fault) return false;
    if (!adapter->ops.send_frame(adapter->ops.context, bytes, length)) {
        fault(adapter);
        return false;
    }
    return true;
}

pe_source_runtime_io_t pe_esp32_adapter_runtime_io(pe_esp32_adapter_t *adapter,
                                                    uint32_t start_bound_ms,
                                                    uint32_t wdi_bound_ms,
                                                    uint32_t control_bound_ms) {
    pe_source_runtime_io_t io = {
        .context = adapter,
        .now_ms = adapter_now_ms,
        .sample = adapter_sample,
        .set_level = adapter_set_level,
        .pulse = adapter_pulse,
        .cancel_uart_tx = adapter_cancel_uart,
        .send_frame = adapter_send_frame,
        .max_sample_to_start_end_ms = start_bound_ms,
        .max_sample_to_wdi_ms = wdi_bound_ms,
        .max_sample_to_control_pin_ms = control_bound_ms,
    };
    return io;
}
