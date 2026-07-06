/* Polled EEMBC main loop; timing_init/start makes DWT live before th_timestamp(). */

#include <zephyr/kernel.h>
#include <zephyr/timing/timing.h>

#include "firmware/common/internally_implemented.h"
#include "api/submitter_implemented.h"

int main(void) {
    timing_init();
    timing_start();

    ee_benchmark_initialize();
    while (1) {
        int c = th_getchar();
        ee_serial_callback(static_cast<char>(c));
    }
    return 0;
}
