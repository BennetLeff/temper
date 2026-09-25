#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <ngspice/sharedspice.h>

int main(void) {
    printf("{\"size\":%zu,\"alignment\":%zu,\"offsets\":[%zu,%zu,%zu,%zu,%zu,%zu]}\n",
           sizeof(vector_info), _Alignof(vector_info),
           offsetof(vector_info, v_name), offsetof(vector_info, v_type),
           offsetof(vector_info, v_flags), offsetof(vector_info, v_realdata),
           offsetof(vector_info, v_compdata), offsetof(vector_info, v_length));
    return 0;
}
