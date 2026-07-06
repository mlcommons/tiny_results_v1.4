/* Shared EEMBC-API plumbing; per-bench src/submitter_implemented.cpp owns wire format and result interpretation. */

#include <float.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/timing/timing.h>
#include <cmsis_core.h>

#include "firmware/common/internally_implemented.h"
#include "api/submitter_implemented.h"
#include "firmware/common/quantization_helpers.h"
#include "firmware/common/dwt_timestamp.h"
#include "firmware/common/eembc_shim.h"
#include "model.h"

/* The classifier libmodels end in QuantSoftmax, so the int8 model output
 * already represents per-class probabilities. */
void emit_classifier_results(const int8_t *out, int n_classes,
                             float output_scale, int output_zero_point) {
    th_printf("m-results-[");
    for (int i = 0; i < n_classes; ++i) {
        float p = DequantizeInt8ToFloat(out[i], output_scale, output_zero_point);
        th_printf("%0.3f", static_cast<double>(p));
        if (i < n_classes - 1) th_printf(",");
    }
    th_printf("]\r\n");
}

void th_infer() {
    run_model();
    /* feed the wrap-tracker; see dwt_timestamp.h */
    dwt_poll();
}

void th_timestamp(void) {
#if EE_CFG_ENERGY_MODE == 1
    th_printf("e-[energy mode timestamp not implemented]\r\n");
#else
    th_printf(EE_MSG_TIMESTAMP, dwt_now_us());
#endif
}

void th_printf(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    (void)vprintf(fmt, args);
    va_end(args);
}

static const struct device *console_uart = nullptr;

char th_getchar() {
    /* Zephyr's default config doesn't wire stdin into picolibc, so we
     * poll uart_poll_in() directly. The runner is request/response. */
    unsigned char c;
    while (uart_poll_in(console_uart, &c) < 0) {}
    return static_cast<char>(c);
}

void th_serialport_initialize(void) {
    console_uart = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
}

void th_timestamp_initialize(void) {
    /* This message must NOT be changed: the runner identifies the mode
     * from it. */
    th_printf(EE_MSG_TIMESTAMP_MODE);
    th_timestamp();
}

void th_final_initialize(void) {
}

void th_pre() {
    __disable_irq();
    __DSB();
    __ISB();
}

void th_post() {
    __enable_irq();
}

void th_command_ready(char volatile *p_command) {
    ee_serial_command_parser_callback(const_cast<char *>(p_command));
}

int th_strncmp(const char *s1, const char *s2, size_t n) { return strncmp(s1, s2, n); }
char *th_strncpy(char *d, const char *s, size_t n)       { return strncpy(d, s, n); }
size_t th_strnlen(const char *s, size_t maxlen)          { return strnlen(s, maxlen); }
char *th_strcat(char *d, const char *s)                  { return strcat(d, s); }
char *th_strtok(char *s, const char *sep)                { return strtok(s, sep); }
int th_atoi(const char *s)                                { return atoi(s); }
void *th_memset(void *b, int c, size_t len)              { return memset(b, c, len); }
void *th_memcpy(void *d, const void *s, size_t n)        { return memcpy(d, s, n); }
int th_vprintf(const char *format, va_list ap)           { return vprintf(format, ap); }
