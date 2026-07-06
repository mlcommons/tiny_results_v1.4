/* Shared firmware-side helpers; per-bench submitter_implemented.cpp owns wire format and result interpretation. */

#ifndef MLPERF_TINY_FIRMWARE_COMMON_EEMBC_SHIM_H_
#define MLPERF_TINY_FIRMWARE_COMMON_EEMBC_SHIM_H_

#include <stddef.h>
#include <stdint.h>

void emit_classifier_results(const int8_t *out, int n_classes,
                             float output_scale, int output_zero_point);

#endif  /* MLPERF_TINY_FIRMWARE_COMMON_EEMBC_SHIM_H_ */
