#ifndef TEMPER_DIAGNOSTIC_CONTACT_MODEL_H
#define TEMPER_DIAGNOSTIC_CONTACT_MODEL_H
#include <stdbool.h>
/* Diagnostic held-position delay and100us conductance ramp. State is carried
 * through command reversals; no mechanical travel or contact bounce claim. */
static inline double contact_position(double t,double since,double initial,
                                      bool energized,double delay)
{
    double fraction=(t-since-delay)/100e-6;
    if(fraction<0) fraction=0;
    if(fraction>1) fraction=1;
    return initial+((energized?1.:0.)-initial)*fraction;
}
#endif
