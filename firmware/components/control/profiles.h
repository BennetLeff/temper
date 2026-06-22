/**
 * @file profiles.h
 * @brief Cooking profiles for multi-stage temperature control
 */

#ifndef PROFILES_H
#define PROFILES_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_PROFILE_STAGES 5

/**
 * @brief Definition of a single cooking stage
 */
typedef struct {
    float target_temp;      /**< Target temperature in °C */
    uint8_t intensity;      /**< 1-10 intensity level */
    uint32_t duration_ms;   /**< Duration in ms (0 = hold indefinitely) */
    bool use_probe;         /**< Use cascade control if probe present */
} profile_stage_t;

/**
 * @brief Full cooking profile
 */
typedef struct cooking_profile_t cooking_profile_t;
struct cooking_profile_t {
    char name[32];          /**< Profile name */
    uint8_t num_stages;     /**< 1-5 */
    profile_stage_t stages[MAX_PROFILE_STAGES];
};

/**
 * @brief Profile execution status
 */
typedef struct {
    const cooking_profile_t *active_profile;
    uint8_t current_stage_idx;
    uint32_t stage_start_time_ms;
    bool active;
    bool completed;
} profile_status_t;

/**
 * @brief Initialize a profile status structure
 */
void profile_init_status(profile_status_t *status);

/**
 * @brief Start a cooking profile
 */
void profile_start(profile_status_t *status, const cooking_profile_t *profile, uint32_t now_ms);

/**
 * @brief Update profile execution
 * 
 * @param status Status structure
 * @param current_temp Current temperature (probe or pan)
 * @param now_ms Current timestamp
 * @return true if stage changed
 */
bool profile_update(profile_status_t *status, float current_temp, uint32_t now_ms);

/**
 * @brief Get current target settings from active stage
 */
void profile_get_current_settings(const profile_status_t *status, float *target_temp, uint8_t *intensity, bool *use_probe);

/**
 * @brief Get preset profiles
 */
const cooking_profile_t* profile_get_simmer(void);
const cooking_profile_t* profile_get_sear_and_hold(void);
const cooking_profile_t* profile_get_sous_vide(void);

#ifdef __cplusplus
}
#endif

#endif /* PROFILES_H */
