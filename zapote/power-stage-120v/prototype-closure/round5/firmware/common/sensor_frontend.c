#include "sensor_frontend.h"
bool r5_sensors_configure(r5_sensor_frontend_t *s)
{
    if(!s) return false;
    s->configured=s->valid=s->cold=false;double error[8];
    for(unsigned n=0;n<8;n++) {
        float v,e;if(!r5_scale(&s->channel[n],0,&v,&e)) return false;error[n]=e;
    }
    s->configured=r5_measurement_init(&s->measurement,error);return s->configured;
}
bool r5_sensors_sample(r5_sensor_frontend_t *s,const ads_sample_t *sample,bool proof,bool contacts)
{
    if(!s||!sample||!s->configured) return false;
    s->valid=false;
    for(unsigned n=0;n<8;n++) {
        float v,e;if(!r5_scale(&s->channel[n],sample->code[n],&v,&e)) return false;s->physical[n]=v;
    }
    s->valid=r5_measurement_add(&s->measurement,sample->captured_us,s->physical,proof,contacts);return s->valid;
}
bool r5_sensors_ntc(r5_sensor_frontend_t *s,const uint16_t code[2])
{
    if(!s||!code) return false;
    float t;s->cold=r5_ntc_cold(&s->ntc[0],code[0],&t)&&r5_ntc_cold(&s->ntc[1],code[1],&t);return s->cold;
}
