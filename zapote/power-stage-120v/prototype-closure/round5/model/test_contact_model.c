#include "contact_model.h"
#include <assert.h>
#include <math.h>
int main(void)
{
    double before_pickup=contact_position(.01,0,0,true,.07245);
    assert(before_pickup==0);
    assert(contact_position(.01,.01,before_pickup,false,.024)==0);
    assert(contact_position(.04,.01,before_pickup,false,.024)==0);
    double mid_pickup=contact_position(.0725,0,0,true,.07245);
    assert(fabs(mid_pickup-.5)<1e-10);
    assert(contact_position(.0725,.0725,mid_pickup,false,.024)==mid_pickup);
    assert(contact_position(.09,.0725,mid_pickup,false,.024)==mid_pickup);
    assert(contact_position(.1,.0725,mid_pickup,false,.024)==0);
    double mid_release=contact_position(.02405,0,1,false,.024);
    assert(fabs(mid_release-.5)<1e-10);
    assert(contact_position(.02405,.02405,mid_release,true,.07245)==mid_release);
    assert(contact_position(.1,.02405,mid_release,true,.07245)==1);
    return 0;
}
