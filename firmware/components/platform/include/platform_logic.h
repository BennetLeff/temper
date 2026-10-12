#ifndef TEMPER_PLATFORM_LOGIC_H
#define TEMPER_PLATFORM_LOGIC_H
/*
 * Pure logic behind the ESP32 platform layer (main/platform/platform_esp32.c, main/platform/ui_esp32.c),
 * host-tested by firmware/test/test_platform_logic.c. No ESP-IDF here; the target files only move
 * values between the drivers and these functions.
 *
 * Fail-safe sentinels (they preserve what state_machine.c / safety.c already treat as a fault):
 *  - resistance / current: +INFINITY. state_machine.c compares with ">" ("> RTD_GROSS_OPEN_DIAGNOSTIC_OHM"
 *    -> FAULT_PROBE_OPEN, "> IGBT_SHORT_CURRENT_THRESHOLD" -> FAULT_IGBT_SHORT) and safety.c checks
 *    !isfinite(). NaN would pass every ordered comparison in state_machine.c, so it is never used for
 *    these two.
 *  - temperature: NaN. check_runaway_boundary() treats !isfinite(pan) as an immediate breach, the
 *    state handlers pass isfinite(pan) as "valid" to the pan cap.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------- pan RTD (PT100, MAX31865) */
/* IEC 60751 Callendar-Van Dusen coefficients for a PT100 (R0 = 100 ohm). */
#define PT100_R0_OHM   100.0f
#define PT100_CVD_A    3.9083e-3f
#define PT100_CVD_B   (-5.775e-7f)
/* The standard's range, -200..850 C (pt100_r_at(): 19.5..390.5 ohm). Outside it: no temperature. */
#define PT100_T_MIN_C (-200.0f)
#define PT100_T_MAX_C  850.0f

/* PT100 resistance at t_c (the standard's T >= 0 C form; used by the tests and for t < 0 too). */
float pt100_r_at(float t_c);
/* Inverse of pt100_r_at() (the quadratic): exact for t >= 0 C; below 0 C it ignores the C term
 * (the error is bounded by test_pt100_below_zero_error). NaN for a non-finite resistance or one
 * outside PT100_T_MIN_C..PT100_T_MAX_C. */
float pt100_ohm_to_c(float ohm);

/* read_rtd_resistance(): have_word = rtd_service_latest_word() succeeded. No usable word, or a word
 * with the MAX31865 fault bit, is +INFINITY. */
float platform_rtd_resistance(bool have_word, uint16_t rtd_word, float rref_ohm);
/* read_pan_temperature(): NaN whenever platform_rtd_resistance() is not finite or out of range. */
float platform_pan_temperature(bool have_word, uint16_t rtd_word, float rref_ohm);

/* ---------------------------------------------------------------- native-21 over-current sources */
/* Design lead decision 2026-10-12: DC bus current is not measured on this hardware; the state
 * machine's over-current interlocks read these instead.
 * FAULT_IGBT_SHORT: status_known = the read-back could be taken (n21 hardware binding started);
 * bus_fault = BUS_FAULT read-back high (GPIO21); permit = PERMIT read-back high (GPIO36);
 * bridge_running = the binding has the bridge live (pads live and run gate on). Unknown status,
 * BUS_FAULT, or PERMIT low while running: tripped. */
bool platform_power_bus_trip(bool status_known, bool bus_fault, bool permit, bool bridge_running);
/* FAULT_OVER_CURRENT: known = the n21 binding exists; n21_fault = its latched n21_fault_t. Tripped
 * for N21_FAULT_TANK_PEAK / N21_FAULT_TANK_RMS (CT peak / RMS trips) and for a failed current
 * channel (N21_FAULT_CT_MON, N21_FAULT_RMS_CHANNEL: the current is unknown), or when unknown. */
bool platform_power_tank_trip(bool known, int n21_fault);

/* ---------------------------------------------------------------- blower request (C28) */
/* The state machine's fan_set_speed()/fan_set_auto_mode() requests. The fan law in thermal_mgmt.c
 * owns the blower (DECISIONS C28). The only thing a request can do is put a full-speed floor under
 * the fan law's command, never lower it: FAN_SPEED_MAX sets the floor; any other speed and
 * fan_set_auto_mode(true) clear it (the fan law alone then decides). */
typedef struct {
    bool full_speed_floor;
} platform_fan_req_t;

/* speed_is_max: the requested fan_speed_t is FAN_SPEED_MAX. */
void platform_fan_request_speed(platform_fan_req_t *r, bool speed_is_max);
void platform_fan_request_auto(platform_fan_req_t *r, bool auto_mode);
/* Applied to blower_ctrl_decide()'s command before the PS3 inlet schedule (thermal_io.c). With the
 * floor: on and duty 0 (C28: duty 0 = full speed). Without: unchanged. */
void platform_blower_apply_floor(bool full_speed_floor, bool *on, float *duty);

/* ---------------------------------------------------------------- fault log (NVS) */
#define PLATFORM_FAULT_LOG_MAGIC 0x544C4631u /* "TLF1" */
#define PLATFORM_FAULT_LOG_LEN   16u

typedef struct {
    uint32_t seq;   /* 1, 2, 3 ... (0 = empty slot) */
    uint32_t t_ms;  /* get_time_ms() at the fault (time since that boot) */
    uint16_t code;  /* fault_code_t */
    uint16_t boot;  /* boot counter at the fault */
} platform_fault_rec_t;

typedef struct {
    uint32_t magic;
    uint32_t next_seq; /* seq of the next record */
    uint16_t boot;     /* incremented once per boot by platform_fault_log_new_boot() */
    uint16_t reserved;
    platform_fault_rec_t rec[PLATFORM_FAULT_LOG_LEN];
} platform_fault_log_t;

void platform_fault_log_init(platform_fault_log_t *log);
/* A blob read back from storage: right magic and a consistent sequence. */
bool platform_fault_log_valid(const platform_fault_log_t *log);
void platform_fault_log_new_boot(platform_fault_log_t *log);
void platform_fault_log_append(platform_fault_log_t *log, uint16_t code, uint32_t t_ms);
size_t platform_fault_log_count(const platform_fault_log_t *log);
/* k = 0 is the newest record; NULL past the end. */
const platform_fault_rec_t *platform_fault_log_get(const platform_fault_log_t *log, size_t k);

/* ---------------------------------------------------------------- display text */
/* "123 C"; "--- C" for a non-finite value. Always NUL-terminated. */
void platform_fmt_temperature(char *out, size_t n, float temp_c);
/* "m:ss" (minutes unbounded). */
void platform_fmt_countdown(char *out, size_t n, uint16_t seconds);

/* SSD1322 256 x 64, 4 bit grey, two pixels per byte (left pixel in the high nibble), rows top down. */
#define PLATFORM_OLED_W 256u
#define PLATFORM_OLED_H 64u
#define PLATFORM_OLED_FB_BYTES (PLATFORM_OLED_W * PLATFORM_OLED_H / 2u)
void platform_oled_clear(uint8_t *fb);
void platform_oled_set_pixel(uint8_t *fb, unsigned x, unsigned y, uint8_t grey);
uint8_t platform_oled_get_pixel(const uint8_t *fb, unsigned x, unsigned y);
/* 5 x 7 font, ASCII 0x20..0x5F (lower case is drawn as upper case, anything else as '?'), each
 * glyph in a 6 x 8 cell times scale. Clipped at the panel edge. Returns the x after the text. */
unsigned platform_oled_text(uint8_t *fb, unsigned x, unsigned y, unsigned scale, const char *s,
                            uint8_t grey);
/* The two-line screen: line1 (state message) at the top, line2 (value) below, both scale 2. */
void platform_oled_render(uint8_t *fb, const char *line1, const char *line2);

/* ---------------------------------------------------------------- UI board inputs */
/* Debounce over consecutive polls: a bit changes only after `polls` identical reads. */
typedef struct {
    uint8_t stable;
    uint8_t candidate;
    uint8_t run;
    bool primed;
} platform_debounce_t;
void platform_debounce_init(platform_debounce_t *d);
uint8_t platform_debounce_step(platform_debounce_t *d, uint8_t raw, uint8_t polls);

/* Quadrature decoder: +1 / -1 per full Gray cycle (four valid transitions in one direction); an
 * invalid (double) transition resets the partial count. */
typedef struct {
    uint8_t prev; /* (a << 1) | b */
    int8_t acc;
    bool primed;
} platform_quad_t;
void platform_quad_init(platform_quad_t *q);
int platform_quad_step(platform_quad_t *q, bool a, bool b);

/* UI link supervision (UI board DECISIONS U14.2 / U15: a UI that cannot be read is a STOP).
 * poll(): ok = this poll got a valid expander read (GPIO read worked and the IODIR read-back matched).
 * Once MORE than lost_ms has passed since the last valid read, a STOP is latched (returns true while
 * lost). The latch is only released by take_stop() after the link is valid again, and is reported at
 * least once, so a loss that ends before the control task samples still stops the cooker. A recovery
 * never produces a START: it only keeps/clears the STOP request. */
typedef struct {
    uint32_t last_good_ms;
    bool ok;
    bool stop_latched;
} platform_ui_link_t;
void platform_ui_link_init(platform_ui_link_t *l, uint32_t now_ms);
bool platform_ui_link_poll(platform_ui_link_t *l, uint32_t now_ms, bool ok, uint32_t lost_ms);
/* The board answered again (re-configured): link valid, a latched STOP is kept. */
void platform_ui_link_reacquired(platform_ui_link_t *l, uint32_t now_ms);
/* BUTTON_STOP request: true while latched; the latch clears on the first call made while the link is ok. */
bool platform_ui_link_take_stop(platform_ui_link_t *l);
/* Milliseconds still to wait so that `wait_ms` have passed since `since_ms` (wrap-safe, 0 = done). */
uint32_t platform_ui_powerup_wait_remaining_ms(uint32_t now_ms, uint32_t since_ms, uint32_t wait_ms);

/* Buzzer (self-oscillating, on an expander output: on/off only). */
typedef enum { PLATFORM_BUZZ_OFF = 0, PLATFORM_BUZZ_TIMED, PLATFORM_BUZZ_CONTINUOUS } platform_buzz_mode_t;
typedef struct {
    platform_buzz_mode_t mode;
    uint32_t until_ms;
} platform_buzzer_t;
void platform_buzzer_beep(platform_buzzer_t *b, uint32_t now_ms, uint32_t duration_ms);
void platform_buzzer_continuous(platform_buzzer_t *b);
void platform_buzzer_stop(platform_buzzer_t *b);
/* Output level now; a timed beep ends (mode -> OFF) once now_ms reaches until_ms (wrap-safe). */
bool platform_buzzer_output(platform_buzzer_t *b, uint32_t now_ms);

#ifdef __cplusplus
}
#endif

#endif
