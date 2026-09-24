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
    /* A physical snapshot, not cached GPIO/expander values. Return false on
     * I2C timeout, missing ACK, bad configuration or incomplete readback. */
    bool (*sample)(void *context, pe_source_inputs_t *inputs);
    bool (*set_level)(void *context, pe_source_pin_t pin, bool high);
    /* A synchronous low-high-low request. The positive edge triggers the
     * SELV one-shot, whose active-low output supplies the WDI falling edge.
     * First drive low even from a retained-high pad, without a boot-time
     * write. No queued, timer, DMA or ISR owner. */
    bool (*pulse)(void *context, pe_source_pin_t pin);
    /* Synchronous open-drain GPIO14 low pulse, then release. Only the source
     * owner calls this after a fresh disarm sample; never drive high. */
    bool (*pulse_cooker_reset)(void *context);
    /* Stop and drain pending UART TX, including the hardware shift register.
     * Required before an abort or deliberate disarm can be acknowledged. */
    bool (*cancel_uart_tx)(void *context);
    /* Return only after the complete frame leaves the wire. No queued TX. */
    bool (*send_frame)(void *context, const uint8_t *bytes, size_t length);
    /* Target-verified time from commit sample through final START bit. */
    uint32_t max_sample_to_start_end_ms;
    /* Target-verified time from the source sample to a WDI falling edge. */
    uint32_t max_sample_to_wdi_ms;
    /* Target-verified worst time from source sample to the positive set/reset
     * control edge, including expander bus operations. Runtime reserves this
     * full interval before requesting an edge near a fixed deadline. */
    uint32_t max_sample_to_control_pin_ms;
} pe_source_runtime_io_t;

typedef struct {
    pe_source_t source;
    pe_stream_t stream;
    pe_source_runtime_io_t io;
    bool io_fault;
    bool cooker_reset_attempted;
    bool progress_baselined;
    uint64_t control_observed;
    uint64_t monitor_observed;
    uint64_t control_credited;
    uint64_t monitor_credited;
    uint64_t paired_progress_epoch;
} pe_source_runtime_t;

/* The physical circuit must hold STOP low before code runs. This function
 * writes non-WDI outputs low and drains UART before allowing a session.
 * WDI is left untouched: a retained-high pad must not fall during boot. */
bool pe_source_runtime_boot(pe_source_runtime_t *runtime,
                            pe_source_runtime_io_t io,
                            pe_source_config_t config,
                            uint32_t max_byte_gap_ms);
void pe_source_runtime_tick(pe_source_runtime_t *runtime);
void pe_source_runtime_byte(pe_source_runtime_t *runtime, uint8_t byte);
void pe_source_runtime_serial_error(pe_source_runtime_t *runtime);
/* Called by the sole source owner with atomic snapshots of independent task
 * counters. The first call sets a baseline; each later credit requires both
 * counters to have advanced since the previous credit. Regression fails
 * closed, including wrap. This does not verify the tasks' actual work. */
void pe_source_runtime_local_progress(pe_source_runtime_t *runtime,
                                      uint64_t control_epoch,
                                      uint64_t monitor_epoch);
bool pe_source_runtime_ping(pe_source_runtime_t *runtime);
void pe_source_runtime_stop(pe_source_runtime_t *runtime);
void pe_source_runtime_begin_restart(pe_source_runtime_t *runtime);
bool pe_source_runtime_disarmed_for_restart(pe_source_runtime_t *runtime);
/* Freshly samples the physical disarm nodes while STOP stays low. This is
 * eligibility for a future cooker-latch reset request, not a GPIO14 pulse
 * or permission to restart. A future pulse owner must resample immediately
 * before its edge and reserve a target-verified sample-to-edge bound. */
bool pe_source_runtime_cooker_latch_reset_eligible(pe_source_runtime_t *runtime);
/* A single-use deliberate restart operation. Rechecks disarm immediately before the
 * GPIO14 edge and requires a new healthy physical sample afterward. A failed
 * pulse/readback latches IO fault and keeps STOP asserted. */
bool pe_source_runtime_reset_cooker_latch(pe_source_runtime_t *runtime);

#endif
