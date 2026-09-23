#ifndef TEMPER_POWER_ENTRY_SOURCE_RUNTIME_H
#define TEMPER_POWER_ENTRY_SOURCE_RUNTIME_H

#include "power_entry_authorization.h"

typedef enum {
    PE_SOURCE_PIN_STOP_N,
    PE_SOURCE_PIN_CHALLENGE_ACTIVE,
    PE_SOURCE_PIN_SEEN_RESET_REQUEST,
    PE_SOURCE_PIN_PERMIT_SET_REQUEST,
    PE_SOURCE_PIN_WDI_HEARTBEAT,
    PE_SOURCE_PIN_COUNT,
} pe_source_pin_t;

typedef struct {
    void *context;
    uint64_t (*now_ms)(void *context);
    pe_source_inputs_t (*sample)(void *context);
    bool (*set_level)(void *context, pe_source_pin_t pin, bool high);
    /* A synchronous low-high-low edge. No queued, timer, DMA or ISR owner. */
    bool (*pulse)(void *context, pe_source_pin_t pin);
    /* Stop and drain pending UART TX, including the hardware shift register.
     * Required before an abort or deliberate disarm can be acknowledged. */
    bool (*cancel_uart_tx)(void *context);
    /* Return only after the complete frame leaves the wire. No queued TX. */
    bool (*send_frame)(void *context, const uint8_t *bytes, size_t length);
    /* Target-verified time from commit sample through final START bit. */
    uint32_t max_sample_to_start_end_ms;
    /* Target-verified time from the source sample to a WDI falling edge. */
    uint32_t max_sample_to_wdi_ms;
    /* Target-verified time from source sample to a set/reset control edge. */
    uint32_t max_sample_to_control_pin_ms;
} pe_source_runtime_io_t;

typedef struct {
    pe_source_t source;
    pe_stream_t stream;
    pe_source_runtime_io_t io;
    bool io_fault;
} pe_source_runtime_t;

/* The physical circuit must hold STOP low before code runs. This function
 * writes every source output low and drains UART before allowing a session. */
bool pe_source_runtime_boot(pe_source_runtime_t *runtime,
                            pe_source_runtime_io_t io,
                            pe_source_config_t config,
                            uint32_t max_byte_gap_ms);
void pe_source_runtime_tick(pe_source_runtime_t *runtime);
void pe_source_runtime_byte(pe_source_runtime_t *runtime, uint8_t byte);
void pe_source_runtime_serial_error(pe_source_runtime_t *runtime);
void pe_source_runtime_local_progress(pe_source_runtime_t *runtime,
                                      uint32_t epoch);
bool pe_source_runtime_ping(pe_source_runtime_t *runtime);
void pe_source_runtime_stop(pe_source_runtime_t *runtime);
void pe_source_runtime_begin_restart(pe_source_runtime_t *runtime);
bool pe_source_runtime_disarmed_for_restart(pe_source_runtime_t *runtime);

#endif
