/**
 * @file pll_control.h
 * @brief Phase-Locked Loop for Zero Voltage Switching (ZVS) tracking
 * 
 * Dynamically tracks resonant frequency of tank circuit to maintain
 * ZVS operation under varying load conditions.
 */

#ifndef PLL_CONTROL_H
#define PLL_CONTROL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief PLL frequency limits
 *
 * PLL_MIN_FREQ_HZ RAISED 30000 -> 42000 on 2026-07-29
 * (docs/evidence/2026-07-29-pll-floor-above-resonance.md), then
 * 42000 -> 43000 later the same day
 * (docs/evidence/2026-07-29-pll-floor-cap-tolerance.md), then
 * 43000 -> 44000 later still the same day, when PR #410 re-sourced
 * elec/src/modules.ato's c_tank1/c_tank2 from WIMA FKP 1 (+/-5%) to CDE
 * 942C16P1K-F (+/-10%) and added a third parallel capacitor, c_tank3,
 * raising elec/src/main.ato's c_tank_tolerance 0.05 -> 0.10.
 *
 * THIS FLOOR IS NOT A TUNING CONSTANT; IT IS A SAFETY BOUND, AND IT IS
 * MACHINE-DERIVED. scripts/check_pll_range_consistency.py recomputes the
 * required value from elec/src/main.ato's declared l_tank_assumed,
 * l_pan_loaded_ratio, c_tank_total, l_tank_tolerance AND c_tank_tolerance
 * and FAILS THE BUILD if this number drops below it. Do not lower it
 * here; lower the physics in main.ato (if it is wrong) and let the gate
 * re-derive.
 *
 * Why: this is a SERIES-resonant inverter. Above the loaded resonance the
 * tank is inductive and the half-bridge switches at zero voltage. BELOW
 * resonance the tank is capacitive and the bridge HARD-SWITCHES -- turn-on
 * loss plus diode reverse recovery on a 1200V IGBT half-bridge at the full
 * 340V bus and ~1.8kW. That is a device-destroying regime, not an
 * efficiency penalty. The old 30000 sat 7.58kHz BELOW the loaded resonance
 * (37.58kHz, the same number as pll_control.c's DEFAULT_RESONANT_FREQ), so
 * the firmware's own declared legal range contained it.
 *
 * The trap that makes it worth a hard guard: at 30kHz this tank delivers
 * ~1783W -- essentially the 1800W rating -- while hard-switching. A
 * power-seeking outer loop can settle there and every power reading looks
 * correct.
 *
 * Derivation, worst-casing BOTH tank components (arithmetic in
 * docs/evidence/2026-07-29-pll-floor-cap-tolerance.md, updated for the
 * CDE re-source):
 *   L_loaded(worst case) = 88uH * (1 - 0.10) * 0.68       = 53.856uH
 *   C(worst case)        = 300nF * (1 - 0.10)             = 270nF
 *   f_res,loaded         = 1/(2*pi*sqrt(53.856uH*270nF))  = 41.737kHz
 *   required floor       = 1.05 * 41.737kHz               = 43.824kHz
 *   PLL_MIN_FREQ_HZ      = 44000  -> smallest round kHz above the floor
 * Keyed off MINIMUM coil L *and* MINIMUM capacitance C, not nominal:
 * f_res ~ 1/sqrt(L*C), so a low-tolerance part on EITHER side resonates
 * higher and needs the highest floor. Until 2026-07-29 this gate
 * worst-cased L only and took C at nominal (300nF), which derived a
 * floor of only 41.575kHz -- correct FOR L alone, but silently assuming
 * a 0%-tolerance capacitor. c_tank1/c_tank2/c_tank3 (elec/src/modules.ato,
 * MPN 942C16P1K-F, CDE Type 942C) are +/-10% parts -- confirmed from TWO
 * independent primary sources: CDE's own catalog (942C.pdf, catalog p.1
 * Specifications table: "Capacitance Tolerance: +/-10% (K) Standard;
 * +/-5% (J) Optional"; p.2 Part Numbering System diagram maps the `K` in
 * this MPN to the tolerance field directly) and DigiKey's distributor
 * listing for this exact part (product 1929475: "Tolerance: +/-10%").
 * (The WIMA FKP 1 part this replaces was +/-5% per its own ordering
 * table -- see git history for that decode.) A capacitor 10% low raises
 * f_res enough (39.595kHz -> 41.737kHz at this L) that a floor derived
 * without honoring the real tolerance would sit dangerously close to a
 * real worst-case unit.
 *
 * The L-only inputs were 150uH * 0.399 = 53.87uH -> floor 41.571kHz until
 * 2026-07-29, when the coil was actually specified (88uH +/-10%) and the
 * pan coupling ratio moved WITH it, as a matched pair -- only the LOADED
 * inductance resonates, so the floor moved 3.5Hz. docs/evidence/2026-07-29-
 * tank-coil-specification.md.
 *
 * WHAT THIS FLOOR REQUIRES OF A DELIVERED COIL: inverting the derivation
 * (now against worst-case C too), 44000/1.05 = 41904.8Hz is the highest
 * loaded resonance this floor still guards, i.e. L_loaded must be >=
 * 53.43uH as MEASURED WITH A PAN (against C_worst = 270nF). A coil that
 * is -10% on inductance and only meets the commonly-quoted
 * "L_loaded >= 0.60 x L_unloaded" screen lands at 47.5uH and resonates at
 * 42.15kHz -- above this floor. The CI gate cannot see that (it treats
 * l_pan_loaded_ratio as exact); incoming inspection carries it, per
 * docs/hardware/TANK_COIL_SPECIFICATION.md Sec 2, and
 * scripts/check_pll_range_consistency.py check 8 fails the build if that
 * document's written threshold drifts from what this derivation computes.
 *
 * Cost, stated: for a series-resonant inverter lower frequency means MORE
 * power, so raising the floor lowers maximum deliverable power. 1800W is
 * unaffected (it lands at 47.1kHz nominal; the ZVS margin there against
 * the worst-case-C loaded resonance is 1.126x, comfortably above the
 * 1.05 cliff). PLL_MAX_FREQ_HZ was deliberately NOT widened to
 * compensate.
 */
#define PLL_MIN_FREQ_HZ     44000   /**< Minimum switching frequency: derived ZVS floor, 1.05x worst-case loaded resonance (worst-case L AND C). See block comment. */
#define PLL_MAX_FREQ_HZ     50000   /**< Maximum switching frequency */
/**
 * @brief Default startup frequency.
 *
 * CORRECTED 2026-07-28 (was 35000, see
 * docs/evidence/2026-07-28-pll-ratio-tracking-check.md and
 * docs/evidence/2026-07-27-zvs-operating-point.md): 35kHz loses 100.7% of
 * ZVS margin at the corrected pan-coupling model (K=0.79) for
 * ferromagnetic pans -- full hard switching of a 1200V IGBT half-bridge.
 * 47000 matches elec/src/main.ato's f_switching = 47kHz, the ZVS-holding
 * operating point (0.84% margin as measured at the then-assumed L=150uH;
 * the coil was specified at 88uH on 2026-07-29 with the pan ratio moving
 * with it, which left the loaded resonance -- and therefore this
 * operating point -- unchanged to 0.008%). Startup must
 * not begin the bridge at a frequency already known to hard-switch.
 */
#define PLL_DEFAULT_FREQ_HZ 47000

/**
 * @brief PLL configuration structure
 */
typedef struct {
    float kp;               /**< Proportional gain */
    float ki;               /**< Integral gain */
    float target_phase_us;  /**< Target phase lag in microseconds */
    uint32_t min_freq_hz;   /**< Minimum allowed frequency */
    uint32_t max_freq_hz;   /**< Maximum allowed frequency */
} pll_config_t;

/**
 * @brief PLL context structure
 */
typedef struct {
    float current_freq;     /**< Current switching frequency */
    float integrator;       /**< PI integrator state */
    float target_phase_us;  /**< Target phase lag */
    float kp;               /**< Proportional gain */
    float ki;               /**< Integral gain */
    uint32_t min_freq;      /**< Minimum frequency limit */
    uint32_t max_freq;      /**< Maximum frequency limit */
    bool locked;            /**< PLL lock status */
    uint32_t lock_count;    /**< Consecutive cycles within lock tolerance */
    uint32_t unlock_count;  /**< Consecutive cycles outside lock tolerance */
    float resonant_freq;    /**< Expected resonant frequency (Hz) */
} pll_context_t;

/**
 * @brief Default PLL configuration
 *
 * min/max are the MACROS above, not repeated literals. They used to be
 * hardcoded 30000/50000 here -- a second, uncrosschecked declaration of
 * the same safety bound, which is the exact defect shape
 * scripts/check_pll_range_consistency.py exists to catch (and which that
 * gate could not see, because it only reads the #defines). Referencing
 * the macros removes the drift by construction rather than by checking.
 */
#define PLL_DEFAULT_CONFIG() { \
    .kp = 2.0f,                \
    .ki = 50.0f,               \
    .target_phase_us = 1.5f,   \
    .min_freq_hz = PLL_MIN_FREQ_HZ, \
    .max_freq_hz = PLL_MAX_FREQ_HZ  \
}

/**
 * @brief Initialize PLL controller
 * 
 * @param config Configuration (NULL for defaults)
 */
void pll_init(const pll_config_t *config);

/**
 * @brief Set MCPWM timer handle for frequency control
 * 
 * Must be called before pll_enable() to allow hardware frequency updates.
 * 
 * @param timer_handle MCPWM timer handle
 */
#ifdef ESP_PLATFORM
#include "driver/mcpwm_prelude.h"
void pll_set_timer(mcpwm_timer_handle_t timer_handle);
void pll_set_capture_channel(mcpwm_cap_channel_handle_t cap_chan);
#endif

/**
 * @brief Enable PLL tracking
 */
void pll_enable(void);

/**
 * @brief Disable PLL tracking
 */
void pll_disable(void);

/**
 * @brief Update PLL with measured phase lag
 * 
 * Called from high-priority task or ISR at ~1kHz rate.
 * Adjusts switching frequency to maintain target phase.
 * 
 * @param measured_lag_us Measured phase lag in microseconds
 * @param dt_sec Time since last update in seconds
 */
void pll_update_loop(float measured_lag_us, float dt_sec);

/**
 * @brief Simplified update using internal phase measurement
 */
void pll_update(void);

/**
 * @brief Get current switching frequency
 * 
 * @return Current frequency in Hz
 */
float pll_get_frequency(void);

/**
 * @brief Check if PLL is locked
 * 
 * @return true if phase error within tolerance
 */
bool pll_is_locked(void);

/**
 * @brief Set target phase lag
 * 
 * @param phase_us Target phase lag in microseconds
 */
void pll_set_target_phase(float phase_us);

/**
 * @brief Reset PLL to default frequency
 */
void pll_reset(void);

/**
 * @brief Get PLL context for debugging/monitoring
 */
const pll_context_t* pll_get_context(void);

/**
 * @brief Set expected resonant frequency for boundary checking
 *
 * @param freq_hz Expected resonant frequency in Hz
 */
void pll_set_resonant_frequency(float freq_hz);

/**
 * @brief Check if frequency is within safe operating bounds
 *
 * Returns true if current frequency is within acceptable range
 * of the resonant frequency (f_res - 5kHz to f_res + 10kHz).
 *
 * @return true if frequency is safe, false if out of bounds
 */
bool pll_is_frequency_safe(void);

/**
 * @brief Get detailed lock status
 *
 * @param lock_cycles Output: number of consecutive locked cycles
 * @param phase_error_us Output: current phase error in microseconds
 * @return true if locked
 */
bool pll_get_lock_status(uint32_t *lock_cycles, float *phase_error_us);

/* Simulation API for testing */
#ifndef ESP_PLATFORM
void pll_sim_set_locked(bool locked);
void pll_sim_set_frequency_safe(bool safe);
#endif

#ifdef __cplusplus
}
#endif

#endif /* PLL_CONTROL_H */
