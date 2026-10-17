/* D25 calculation, not peripheral emulation or pin measurement.
 * Actual pinned ESP-IDF LL functions are extracted into ll_subset.h.
 * Interpretation: ESP32-S3 TRM v1.8 Fig 36.3-13/21, Table 36.3-5,
 * GEN0_FORCE (p1373) and DT0_CFG register definitions.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "mcpwm_struct.h"
/* Host equivalent of the SDK read/modify/write helper; no MMIO here. */
#define HAL_FORCE_MODIFY_U32_REG_FIELD(reg, field, value) do { (reg).field = (value); } while (0)
#include "ll_subset.h"
static mcpwm_dev_t dev;
static void program(unsigned ticks) {
    /* Trace of mcpwm_gen.c:374-390 for D21 program_delay(): A RED, B FED. */
    mcpwm_ll_deadtime_bypass_path(&dev, 0, 0, false);
    mcpwm_ll_deadtime_red_select_generator(&dev, 0, 0);
    mcpwm_ll_deadtime_enable_deb(&dev, 0, false);
    mcpwm_ll_deadtime_invert_outpath(&dev, 0, 0, false);
    mcpwm_ll_deadtime_swap_out_path(&dev, 0, 0, false);
    mcpwm_ll_deadtime_set_rising_delay(&dev, 0, ticks);
    mcpwm_ll_deadtime_bypass_path(&dev, 0, 1, false);
    mcpwm_ll_deadtime_fed_select_generator(&dev, 0, 1);
    mcpwm_ll_deadtime_enable_deb(&dev, 0, false);
    mcpwm_ll_deadtime_invert_outpath(&dev, 0, 1, true);
    mcpwm_ll_deadtime_swap_out_path(&dev, 0, 1, false);
    mcpwm_ll_deadtime_set_falling_delay(&dev, 0, ticks);
}
/* Independent TRM diagram interpretation using literal field bit positions.
 * At constant input, RED/FED preserve that constant. No delay timing claim. */
static unsigned output(unsigned dt, unsigned a, unsigned b, unsigned which) {
    unsigned red = ((dt >> 12) & 1) ? b : a;
    unsigned fed = ((dt >> 11) & 1) ? b : a;
    if ((dt >> 8) & 1) fed = red;
    unsigned ap = ((dt >> 15) & 1) ? a : (red ^ ((dt >> 13) & 1));
    unsigned bp = ((dt >> 16) & 1) ? b : (fed ^ ((dt >> 14) & 1));
    return which ? (((dt >> 10) & 1) ? ap : bp) : (((dt >> 9) & 1) ? bp : ap);
}
int main(void) {
    program(24); /* Existing D21 test request: floor(307 ns * 2 / 25). */
    unsigned dt = dev.operators[0].dt_cfg.val;
    assert(dt == 0x4800); /* DT topology bits only; excludes clock/update flags. */
    assert(dev.operators[0].dt_red_cfg.dt_red == 23);
    assert(dev.operators[0].dt_fed_cfg.dt_fed == 23);
    printf("D21 topology mask DT_CFG[16:8]=0x%05x; RED=23 FED=23 for 24 requested ticks\n", dt);
    puts("raw_A raw_B steady_output_A steady_output_B");
    for (unsigned a=0; a<2; a++) for (unsigned b=0; b<2; b++) {
        unsigned oa=output(dt,a,b,0), ob=output(dt,a,b,1);
        assert(oa==a && ob==(b^1));
        printf("%u %u %u %u\n",a,b,oa,ob);
    }
    mcpwm_ll_gen_set_continue_force_level(&dev,0,0,0);
    mcpwm_ll_gen_set_continue_force_level(&dev,0,1,1);
    unsigned force=dev.operators[0].gen_force.val;
    assert(force==0x240);
    assert(((force>>6)&3)==1 && ((force>>8)&3)==2 && (force&63)==0);
    assert(output(dt,0,1,0)==0 && output(dt,0,1,1)==0);
    printf("Initialized/stop force GEN_FORCE=0x%03x; raw=0,1; output=0,0\n",force);
    mcpwm_ll_gen_disable_continue_force_action(&dev,0,1);
    mcpwm_ll_gen_disable_continue_force_action(&dev,0,0);
    assert(dev.operators[0].gen_force.val==0);
    puts("Start clears continuous force modes; waveform timing is outside this static calculation.");
    puts("PASS: force polarity and LL register encoding agree with TRM static topology.");
    return 0;
}
