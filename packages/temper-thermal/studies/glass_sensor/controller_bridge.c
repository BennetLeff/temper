/* Study-only adapter. Links unchanged production PID/cascade source files. */
#include "cascade_pid.h"
#include "pid_control.h"
#include <math.h>
static cascade_pid_handle_t cascade;
static pid_handle_t single;
void study_controller_reset(void) {
    cascade_pid_init_default(&cascade);
    pid_init(&single, 1.0f, 0.05f, 0.2f);
}
float study_controller_step(int variant, float sensor, float dt) {
    return variant == 0 ? pid_compute(&single, 200.0f, sensor, dt)
        : cascade_pid_update(&cascade, 200.0f, NAN, sensor, dt);
}
