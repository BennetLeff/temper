#ifndef R5_BYPASS_H
#define R5_BYPASS_H
#include "measurement.h"
/* NC mirror-open alone is never sufficient. The independent proof load must
 * draw its expected full-cycle current with uncertainty-bounded VPRE<1Vrms. */
bool r5_bypass_loaded(const r5_measurement_t *);
#endif
