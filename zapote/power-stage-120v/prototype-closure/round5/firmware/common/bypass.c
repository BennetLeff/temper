#include "bypass.h"
#include <math.h>
bool r5_bypass_loaded(const r5_measurement_t *s)
{
    return s&&!s->fault&&s->proof_ok&&s->source_ok&&s->serial&&
        isfinite(s->rms[1])&&isfinite(s->error[1])&&s->error[1]>=0&&
        s->rms[1]+s->error[1]<1;
}
