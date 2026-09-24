#include "../main/power_entry_esp32_adapter.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t regs[4];
    bool gpio[49];
    int stop_writes;
    int wdi_writes;
    int uart_cancels;
    int operations;
    int stop_order;
    int latch_order;
    int config_order;
    bool fail_next_read;
    bool fail_next_write;
} fixture_t;

static bool output_low(void *context, int gpio) {
    fixture_t *f = context;
    f->gpio[gpio] = false;
    if (gpio == PE_ESP_GPIO_STOP_N) {
        f->stop_writes++;
        if (!f->stop_order) f->stop_order = ++f->operations;
    } else if (gpio == PE_ESP_GPIO_WDI_REQUEST) {
        f->wdi_writes++;
    }
    return true;
}

static bool input(void *context, int gpio) {
    (void)context;
    return gpio == PE_ESP_GPIO_PREWATCHDOG_OK ||
           gpio == PE_ESP_GPIO_START_BUTTON;
}

static bool set_gpio(void *context, int gpio, bool high) {
    fixture_t *f = context;
    f->gpio[gpio] = high;
    if (gpio == PE_ESP_GPIO_STOP_N) f->stop_writes++;
    if (gpio == PE_ESP_GPIO_WDI_REQUEST) f->wdi_writes++;
    return true;
}

static bool read_gpio(void *context, int gpio, bool *high) {
    fixture_t *f = context;
    *high = f->gpio[gpio];
    return true;
}

static bool write_expander(void *context, uint8_t reg, uint8_t value) {
    fixture_t *f = context;
    if (f->fail_next_write) {
        f->fail_next_write = false;
        return false;
    }
    if (reg > 3) return false;
    f->regs[reg] = value;
    if (reg == 1 && !f->latch_order) f->latch_order = ++f->operations;
    if (reg == 3 && !f->config_order) f->config_order = ++f->operations;
    return true;
}

static bool read_expander(void *context, uint8_t reg, uint8_t *value) {
    fixture_t *f = context;
    if (f->fail_next_read) {
        f->fail_next_read = false;
        return false;
    }
    if (reg > 3) return false;
    *value = f->regs[reg];
    return true;
}

static bool cancel_uart(void *context) {
    fixture_t *f = context;
    f->uart_cancels++;
    return true;
}

static bool send_frame(void *context, const uint8_t *bytes, size_t length) {
    (void)context;
    (void)bytes;
    return length == PE_FRAME_SIZE;
}

static uint64_t now_ms(void *context) {
    (void)context;
    return 1;
}

static pe_esp32_adapter_ops_t ops(fixture_t *f) {
    pe_esp32_adapter_ops_t result = {
        .context = f,
        .configure_output_low = output_low,
        .configure_input = input,
        .set_gpio = set_gpio,
        .read_gpio = read_gpio,
        .write_expander = write_expander,
        .read_expander = read_expander,
        .cancel_uart_tx = cancel_uart,
        .send_frame = send_frame,
        .now_ms = now_ms,
    };
    return result;
}

static void test_retained_output_boot_order(void) {
    fixture_t f = {0};
    pe_esp32_adapter_t adapter;
    /* CPU-only reset: all three expander outputs retain high. */
    f.regs[1] = 0x07;
    f.regs[3] = 0xf8;
    f.gpio[PE_ESP_GPIO_WDI_REQUEST] = true;
    assert(pe_esp32_adapter_boot(&adapter, ops(&f)));
    assert(f.stop_order && f.stop_order < f.latch_order);
    assert(f.latch_order < f.config_order);
    assert(f.regs[1] == 0 && f.regs[2] == 0 && f.regs[3] == 0xf8);
    assert(f.wdi_writes == 0);
    assert(f.gpio[PE_ESP_GPIO_WDI_REQUEST]);
    assert(f.uart_cancels == 1);
}

static void test_physical_sample_and_failure_stop(void) {
    fixture_t f = {0};
    pe_esp32_adapter_t adapter;
    assert(pe_esp32_adapter_boot(&adapter, ops(&f)));
    pe_source_runtime_io_t io = pe_esp32_adapter_runtime_io(&adapter, 1, 1, 1);
    f.regs[0] = 0xb8; /* P3, P4, P5, P7; P6 low. */
    f.gpio[PE_ESP_GPIO_PREWATCHDOG_OK] = true;
    f.gpio[PE_ESP_GPIO_START_BUTTON] = false;
    pe_source_inputs_t inputs;
    assert(io.sample(io.context, &inputs));
    assert(inputs.rail_good && inputs.local_permit_q && inputs.hot_permit);
    assert(!inputs.hot_session_q && inputs.permit_seen_q);
    assert(inputs.safety_ok && inputs.start_button_pressed);
    assert(io.set_level(io.context, PE_SOURCE_PIN_STOP_N, true));
    f.fail_next_read = true;
    assert(!io.sample(io.context, &inputs));
    assert(adapter.fault && !f.gpio[PE_ESP_GPIO_STOP_N]);
    assert(f.uart_cancels >= 2);
}

static void test_boot_readback_failure(void) {
    fixture_t f = {0};
    pe_esp32_adapter_t adapter;
    f.fail_next_read = true;
    assert(!pe_esp32_adapter_boot(&adapter, ops(&f)));
    assert(adapter.fault && !adapter.booted);
    assert(f.stop_writes >= 2);
    assert(f.wdi_writes == 0);
    assert(f.config_order == 0);
}

static void test_configuration_drift_and_interrupted_write(void) {
    fixture_t f = {0};
    pe_esp32_adapter_t adapter;
    assert(pe_esp32_adapter_boot(&adapter, ops(&f)));
    pe_source_runtime_io_t io = pe_esp32_adapter_runtime_io(&adapter, 1, 1, 1);
    f.regs[3] = 0xff; /* An expander reset released all outputs. */
    pe_source_inputs_t inputs;
    assert(io.set_level(io.context, PE_SOURCE_PIN_STOP_N, true));
    assert(!io.sample(io.context, &inputs));
    assert(adapter.fault && !f.gpio[PE_ESP_GPIO_STOP_N]);

    memset(&f, 0, sizeof(f));
    assert(pe_esp32_adapter_boot(&adapter, ops(&f)));
    assert(io.set_level(io.context, PE_SOURCE_PIN_STOP_N, true));
    f.fail_next_write = true;
    assert(!io.set_level(io.context, PE_SOURCE_PIN_CHALLENGE_ACTIVE, true));
    assert(adapter.fault && !f.gpio[PE_ESP_GPIO_STOP_N]);
    assert(f.regs[1] == 0);
}

static void test_expander_retain_and_pulse(void) {
    fixture_t f = {0};
    pe_esp32_adapter_t adapter;
    assert(pe_esp32_adapter_boot(&adapter, ops(&f)));
    pe_source_runtime_io_t io = pe_esp32_adapter_runtime_io(&adapter, 1, 1, 1);
    assert(io.set_level(io.context, PE_SOURCE_PIN_CHALLENGE_ACTIVE, true));
    assert(f.regs[1] == 1);
    assert(io.pulse(io.context, PE_SOURCE_PIN_SEEN_RESET_REQUEST));
    assert(f.regs[1] == 1);
    assert(f.wdi_writes == 0);
    assert(io.pulse(io.context, PE_SOURCE_PIN_WDI_HEARTBEAT));
    assert(f.wdi_writes == 4); /* configure low, low, high, low */
    assert(!f.gpio[PE_ESP_GPIO_WDI_REQUEST]);
}

static void test_source_runtime_boot_with_adapter(void) {
    fixture_t f = {0};
    pe_esp32_adapter_t adapter;
    pe_source_runtime_t runtime;
    assert(pe_esp32_adapter_boot(&adapter, ops(&f)));
    pe_source_runtime_io_t io = pe_esp32_adapter_runtime_io(&adapter, 10, 10, 10);
    pe_source_config_t config = {
        .prepare_window_ms = 100,
        .start_window_ms = 100,
        .watchdog_window_ms = 1000,
    };
    assert(pe_source_runtime_boot(&runtime, io, config, 5));
    assert(!runtime.io_fault && !adapter.fault);
    assert(f.wdi_writes == 0);
    assert(f.regs[1] == 0);
    assert(!f.gpio[PE_ESP_GPIO_STOP_N]);
}

int main(void) {
    test_retained_output_boot_order();
    test_physical_sample_and_failure_stop();
    test_boot_readback_failure();
    test_configuration_drift_and_interrupted_write();
    test_expander_retain_and_pulse();
    test_source_runtime_boot_with_adapter();
    puts("power_entry_esp32_adapter: PASS");
    return 0;
}
