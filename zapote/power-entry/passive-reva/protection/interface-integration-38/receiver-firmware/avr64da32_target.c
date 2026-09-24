/* AVR64DA32-E/PT engineering adapter. The default image has zero timing
 * windows and cannot leave LOCKOUT. See README before enabling it. */
#include "avr64da32_boot_contract.h"
#include "runtime.h"

#include <avr/cpufunc.h>
#include <avr/interrupt.h>
#include <avr/io.h>

#include <stdint.h>

#if !defined(__AVR_AVR64DA32__)
#error "Build only for AVR64DA32"
#endif
#if EEPROM_SIZE != PE_JOURNAL_BYTES
#error "The durable journal must occupy exactly the selected EEPROM"
#endif

#ifndef PE_TARGET_PREPARE_WINDOW_MS
#define PE_TARGET_PREPARE_WINDOW_MS 0u
#endif
#ifndef PE_TARGET_START_WINDOW_MS
#define PE_TARGET_START_WINDOW_MS 0u
#endif
#ifndef PE_TARGET_WATCHDOG_WINDOW_MS
#define PE_TARGET_WATCHDOG_WINDOW_MS 0u
#endif
#ifndef PE_TARGET_BYTE_GAP_MS
#define PE_TARGET_BYTE_GAP_MS 0u
#endif
#ifndef PE_TARGET_PING_PERIOD_MS
#define PE_TARGET_PING_PERIOD_MS 0u
#endif
#ifndef PE_TARGET_SAMPLE_TO_RUN_MS
#define PE_TARGET_SAMPLE_TO_RUN_MS 0u
#endif
#ifndef PE_TARGET_EXPECTED_WDTCFG
#define PE_TARGET_EXPECTED_WDTCFG 0u
#endif
#ifndef PE_TARGET_EXPECTED_BODCFG
#define PE_TARGET_EXPECTED_BODCFG 0u
#endif
#ifndef PE_TARGET_EXPECTED_SYSCFG0
#define PE_TARGET_EXPECTED_SYSCFG0 0u
#endif
#if PE_TARGET_EXPECTED_WDTCFG > 255u || PE_TARGET_EXPECTED_BODCFG > 255u || \
    PE_TARGET_EXPECTED_SYSCFG0 > 255u
#error "Expected AVR fuse bytes must fit in one byte"
#endif

/* U1 has no accepted numerical limits. This flag exists only to compile all
 * adapter paths offline; it is not a release or programming configuration. */
#if (PE_TARGET_PREPARE_WINDOW_MS != 0u || PE_TARGET_START_WINDOW_MS != 0u || \
     PE_TARGET_WATCHDOG_WINDOW_MS != 0u || PE_TARGET_BYTE_GAP_MS != 0u || \
     PE_TARGET_PING_PERIOD_MS != 0u || PE_TARGET_SAMPLE_TO_RUN_MS != 0u) && \
    !defined(PE_TARGET_OFFLINE_COMPILER_EXERCISE)
#error "Nonzero receiver timing requires a future accepted configuration"
#endif

#define PE_TARGET_CLOCK_HZ 24000000UL
#define PE_TARGET_UART_BAUD 115200UL
#define PE_TARGET_UART_BAUD_REG \
    ((4UL * PE_TARGET_CLOCK_HZ + PE_TARGET_UART_BAUD / 2UL) / PE_TARGET_UART_BAUD)

static volatile uint64_t tick_ms;

static bool programmed_fuses_match(void) {
    const pe_avr_fuses_t actual = {
        FUSE.WDTCFG, FUSE.BODCFG, FUSE.OSCCFG, FUSE.SYSCFG0,
    };
    const pe_avr_fuses_t expected = {
        PE_TARGET_EXPECTED_WDTCFG, PE_TARGET_EXPECTED_BODCFG, 0u,
        PE_TARGET_EXPECTED_SYSCFG0,
    };
    return pe_avr_boot_fuses_ok(actual, expected);
}

ISR(TCB0_INT_vect) {
    ++tick_ms;
    TCB0.INTFLAGS = TCB_CAPT_bm;
}

static uint64_t now_ms(void *context) {
    (void)context;
    uint8_t saved = SREG;
    cli();
    uint64_t result = tick_ms;
    SREG = saved;
    return result;
}

static void pins_low(void) {
    /* OUT is set before DIR, so reset-time high impedance cannot make an
     * unsafe high when firmware takes ownership. External pull-downs own
     * the interval before this function executes. */
    PORTA.OUTCLR = PIN2_bm | PIN4_bm | PIN6_bm;
    PORTC.OUTCLR = PIN3_bm;
    PORTD.OUTCLR = PIN3_bm | PIN4_bm | PIN5_bm | PIN6_bm;
    PORTF.OUTCLR = PIN1_bm;
    PORTA.DIRSET = PIN2_bm | PIN4_bm | PIN6_bm;
    PORTC.DIRSET = PIN3_bm;
    PORTD.DIRSET = PIN3_bm | PIN4_bm | PIN5_bm | PIN6_bm;
    PORTF.DIRSET = PIN1_bm;
}

static bool output_port(pe_output_pin_t pin, volatile PORT_t **port,
                        uint8_t *mask) {
    switch (pin) {
    case PE_PIN_ABORT_N: *port = &PORTD; *mask = PIN3_bm; return true;
    case PE_PIN_ATTEMPT_VALID: *port = &PORTA; *mask = PIN6_bm; return true;
    case PE_PIN_DISARM_SAMPLE: *port = &PORTF; *mask = PIN1_bm; return true;
    case PE_PIN_PREP_RESET: *port = &PORTA; *mask = PIN4_bm; return true;
    case PE_PIN_HISTORY_RESET: *port = &PORTC; *mask = PIN3_bm; return true;
    case PE_PIN_REVALIDATE: *port = &PORTD; *mask = PIN4_bm; return true;
    case PE_PIN_RUN_SET: *port = &PORTD; *mask = PIN5_bm; return true;
    case PE_PIN_WDI: *port = &PORTD; *mask = PIN6_bm; return true;
    case PE_PIN_RELAY: *port = &PORTA; *mask = PIN2_bm; return true;
    default: return false;
    }
}

static bool set_level(void *context, pe_output_pin_t pin, bool high) {
    (void)context;
    volatile PORT_t *port;
    uint8_t mask;
    if (!output_port(pin, &port, &mask)) return false;
    if (high) port->OUTSET = mask;
    else port->OUTCLR = mask;
    return true;
}

static bool pulse(void *context, pe_output_pin_t pin) {
    (void)context;
    if (pin != PE_PIN_DISARM_SAMPLE && pin != PE_PIN_PREP_RESET &&
        pin != PE_PIN_HISTORY_RESET && pin != PE_PIN_REVALIDATE &&
        pin != PE_PIN_RUN_SET && pin != PE_PIN_WDI) return false;
    volatile PORT_t *port;
    uint8_t mask;
    if (!output_port(pin, &port, &mask)) return false;
    uint8_t saved = SREG;
    cli();
    port->OUTCLR = mask;
    __builtin_avr_delay_cycles(240);
    port->OUTSET = mask;
    __builtin_avr_delay_cycles(240);
    port->OUTCLR = mask;
    SREG = saved;
    return true;
}

static pe_receiver_inputs_t sample(void *context) {
    (void)context;
    uint8_t a = PORTA.IN;
    uint8_t c = PORTC.IN;
    uint8_t d = PORTD.IN;
    uint8_t f = PORTF.IN;
    return (pe_receiver_inputs_t){
        .rail_good = (d & PIN7_bm) != 0,
        .fault = (c & PIN2_bm) == 0, /* HOT_FAULT_N */
        .physical_permit = (d & PIN0_bm) != 0,
        .session_q = (d & PIN1_bm) != 0,
        .run_q = (d & PIN2_bm) != 0,
        .disarm_seen = (c & PIN0_bm) != 0,
        .preparation_abort = (c & PIN1_bm) != 0,
        .permit_seen_q = (a & PIN3_bm) != 0,
        .session_clear_n = (f & PIN0_bm) != 0,
    };
}

static uint8_t journal_read(void *context, uint16_t address) {
    (void)context;
    if (address >= PE_JOURNAL_BYTES) return 0;
    return *(volatile uint8_t *)(EEPROM_START + address);
}

static bool journal_write(void *context, uint16_t address, uint8_t value) {
    (void)context;
    if (address >= PE_JOURNAL_BYTES ||
        (NVMCTRL.STATUS & NVMCTRL_ERROR_gm) != NVMCTRL_ERROR_NOERROR_gc)
        return false;
    while (NVMCTRL.STATUS & (NVMCTRL_EEBUSY_bm | NVMCTRL_FBUSY_bm)) {
        /* The external watchdog must expire if NVM never becomes ready. */
    }
    ccp_write_spm(&NVMCTRL.CTRLA, NVMCTRL_CMD_EEERWR_gc);
    *(volatile uint8_t *)(EEPROM_START + address) = value;
    while (NVMCTRL.STATUS & (NVMCTRL_EEBUSY_bm | NVMCTRL_FBUSY_bm)) {
    }
    ccp_write_spm(&NVMCTRL.CTRLA, NVMCTRL_CMD_NONE_gc);
    return (NVMCTRL.STATUS & NVMCTRL_ERROR_gm) == NVMCTRL_ERROR_NOERROR_gc &&
           journal_read(NULL, address) == value;
}

static bool transmit(void *context, const uint8_t *bytes, size_t length) {
    (void)context;
    USART0.STATUS = USART_TXCIF_bm; /* completion must belong to this frame */
    for (size_t i = 0; i < length; ++i) {
        uint64_t until = now_ms(NULL) + 3u;
        while (!(USART0.STATUS & USART_DREIF_bm)) {
            if (now_ms(NULL) >= until) return false;
        }
        USART0.TXDATAL = bytes[i];
    }
    uint64_t until = now_ms(NULL) + 3u;
    while (!(USART0.STATUS & USART_TXCIF_bm)) {
        if (now_ms(NULL) >= until) return false;
    }
    USART0.STATUS = USART_TXCIF_bm;
    return true;
}

static void clock_and_io_init(void) {
    _PROTECTED_WRITE(CLKCTRL.OSCHFCTRLA, CLKCTRL_FRQSEL_24M_gc);
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB, 0); /* no prescaler */
    TCB0.CTRLA = 0;
    TCB0.CTRLB = TCB_CNTMODE_INT_gc;
    TCB0.CCMP = PE_TARGET_CLOCK_HZ / 1000UL;
    TCB0.INTCTRL = TCB_CAPT_bm;
    TCB0.CTRLA = TCB_CLKSEL_DIV1_gc | TCB_ENABLE_bm;

    PORTMUX.USARTROUTEA = PORTMUX_USART0_DEFAULT_gc;
    PORTA.OUTSET = PIN0_bm;
    PORTA.DIRSET = PIN0_bm;
    PORTA.DIRCLR = PIN1_bm;
    USART0.BAUD = PE_TARGET_UART_BAUD_REG;
    USART0.CTRLC = USART_CMODE_ASYNCHRONOUS_gc | USART_CHSIZE_8BIT_gc;
    USART0.CTRLB = USART_RXEN_bm | USART_TXEN_bm;
    sei();
}

int main(void) {
    pins_low();
    /* Factory/reset fuse defaults are not an operating configuration. Keep
     * abort and relay low until exact programmed fuses pass readback. */
    if (!programmed_fuses_match()) {
        for (;;) { /* External pull-downs and watchdog own the safe state. */ }
    }
    clock_and_io_init();
    const pe_journal_io_t journal = {
        .context = NULL, .read_byte = journal_read, .write_byte = journal_write,
    };
    const pe_runtime_io_t io = {
        .context = NULL, .now_ms = now_ms, .sample = sample,
        .set_level = set_level, .pulse = pulse, .transmit = transmit,
        .journal = &journal,
        .max_sample_to_run_pin_ms = PE_TARGET_SAMPLE_TO_RUN_MS,
    };
    const pe_receiver_config_t config = {
        .prepare_window_ms = PE_TARGET_PREPARE_WINDOW_MS,
        .start_window_ms = PE_TARGET_START_WINDOW_MS,
        .watchdog_window_ms = PE_TARGET_WATCHDOG_WINDOW_MS,
    };
    pe_runtime_t runtime;
    if (!pe_runtime_boot(&runtime, io, config, PE_TARGET_BYTE_GAP_MS)) {
        for (;;) { /* External pull-downs and watchdog hold the safe state. */ }
    }
    pe_journal_state_t state;
    if (!pe_journal_scan(&journal, &state)) runtime.receiver.storage_fault = true;
    uint64_t last_tick = now_ms(NULL);
    uint64_t last_ping = last_tick;
    uint32_t local_epoch = 0;
    for (;;) {
        if (USART0.STATUS & USART_RXCIF_bm) {
            uint8_t errors = USART0.RXDATAH &
                (USART_FERR_bm | USART_PERR_bm | USART_BUFOVF_bm);
            uint8_t byte = USART0.RXDATAL;
            if (errors) pe_runtime_serial_error(&runtime);
            else pe_runtime_byte(&runtime, byte);
        }
        uint64_t now = now_ms(NULL);
        if (now != last_tick) {
            last_tick = now;
            pe_runtime_tick(&runtime);
            if (!runtime.io_fault && runtime.receiver.state != PE_RX_LOCKOUT &&
                local_epoch != UINT32_MAX) {
                pe_runtime_local_progress(&runtime, ++local_epoch);
            }
            /* Internal WDT is local execution supervision. Only a completed
             * receiver iteration can feed it; USART activity cannot. The
             * external WDI additionally requires matching link progress. */
            if (!runtime.io_fault) __asm__ __volatile__("wdr");
        }
#if PE_TARGET_PING_PERIOD_MS > 0
        if (now - last_ping >= PE_TARGET_PING_PERIOD_MS) {
            last_ping = now;
            (void)pe_runtime_ping(&runtime);
        }
#else
        (void)last_ping;
#endif
    }
}
