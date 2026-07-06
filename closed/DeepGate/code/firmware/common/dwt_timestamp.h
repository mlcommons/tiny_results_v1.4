/* 64-bit cycle counter shim around Zephyr's timing_counter_get().
 *
 * DWT->CYCCNT is 32-bit. At 280 MHz (nucleo_h7a3zi_q) it wraps every
 * ~15.3 s; the runner's latency math turns that wrap into a negative
 * runtime and fails the iteration. We track wraps in a 64-bit shadow.
 *
 * Callers must invoke dwt_poll() at least once per inference iteration
 * so any single iter that crosses a wrap (e.g. IC02's 50 x 367 ms
 * = 18.4 s) still gets caught. dwt_now_us() also polls internally. */

#ifndef MLPERF_TINY_FIRMWARE_COMMON_DWT_TIMESTAMP_H_
#define MLPERF_TINY_FIRMWARE_COMMON_DWT_TIMESTAMP_H_

#include <stdint.h>
#include <zephyr/timing/timing.h>

extern uint32_t dwt_prev_cyc;
extern uint64_t dwt_wrap_cyc;

static inline void dwt_poll(void) {
    uint32_t now = (uint32_t)timing_counter_get();
    if (now < dwt_prev_cyc) {
        dwt_wrap_cyc += 0x100000000ULL;
    }
    dwt_prev_cyc = now;
}

static inline unsigned long dwt_now_us(void) {
    dwt_poll();
    uint64_t total_cyc = dwt_wrap_cyc + (uint64_t)dwt_prev_cyc;
    return (unsigned long)(total_cyc * 1000000ULL / timing_freq_get());
}

#endif  /* MLPERF_TINY_FIRMWARE_COMMON_DWT_TIMESTAMP_H_ */
