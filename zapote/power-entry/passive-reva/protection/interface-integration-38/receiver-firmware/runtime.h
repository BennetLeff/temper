#ifndef TEMPER_POWER_ENTRY_RECEIVER_RUNTIME_H
#define TEMPER_POWER_ENTRY_RECEIVER_RUNTIME_H

#include "receiver.h"

typedef enum {
    PE_PIN_ABORT_N,
    PE_PIN_ATTEMPT_VALID,
    PE_PIN_DISARM_SAMPLE,
    PE_PIN_PREP_RESET,
    PE_PIN_HISTORY_RESET,
    PE_PIN_REVALIDATE,
    PE_PIN_RUN_SET,
    PE_PIN_WDI,
    PE_PIN_RELAY,
    PE_PIN_COUNT,
} pe_output_pin_t;

typedef struct {
    void *context;
    uint64_t (*now_ms)(void *context);
    pe_receiver_inputs_t (*sample)(void *context);
    bool (*set_level)(void *context, pe_output_pin_t pin, bool high);
    /* Synchronous low-high-low edge, with target-verified minimum high/low
     * widths. No timer, DMA, ISR, or queued GPIO write may own these pins. */
    bool (*pulse)(void *context, pe_output_pin_t pin);
    bool (*transmit)(void *context, const uint8_t *bytes, size_t length);
    const pe_journal_io_t *journal;
    uint32_t max_sample_to_run_pin_ms; /* target evidence required */
} pe_runtime_io_t;

typedef struct {
    pe_receiver_t receiver;
    pe_stream_t stream;
    pe_runtime_io_t io;
    bool io_fault;
} pe_runtime_t;

/* All assigned outputs are driven low before the receiver can advance.
 * External pull-down/clear hardware owns safety before this code executes. */
bool pe_runtime_boot(pe_runtime_t *runtime, pe_runtime_io_t io,
                     pe_receiver_config_t config, uint32_t max_byte_gap_ms);
/* One physical sample per core transition; pulse writes are synchronous. */
void pe_runtime_tick(pe_runtime_t *runtime);
void pe_runtime_byte(pe_runtime_t *runtime, uint8_t byte);
/* USART framing, parity or overrun errors invalidate the current attempt. */
void pe_runtime_serial_error(pe_runtime_t *runtime);
/* The target calls these only after one complete local safety iteration and
 * at a bounded ping interval. A received byte alone is never progress. */
void pe_runtime_local_progress(pe_runtime_t *runtime, uint32_t epoch);
bool pe_runtime_ping(pe_runtime_t *runtime);

#endif
