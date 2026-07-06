#include <stdint.h>

/* See dwt_timestamp.h for why dwt_poll() and dwt_now_us() share these. */
uint32_t dwt_prev_cyc = 0;
uint64_t dwt_wrap_cyc = 0;
