/* Per-element float<->int8 helpers used by every bench's th_load_tensor /
 * th_results. Scale and zero_point are per-bench static constexpr in each
 * submitter_implemented.cpp, sourced from models/closed/<bench>/schema.json.
 *
 * Ported verbatim from tiny/benchmark/util/quantization_helpers.h
 * (mlcommons/tiny). Closed-division equivalence depends on byte-for-byte
 * match; refresh from upstream rather than editing locally. */

#ifndef MLPERF_TINY_FIRMWARE_COMMON_QUANTIZATION_HELPERS_H_
#define MLPERF_TINY_FIRMWARE_COMMON_QUANTIZATION_HELPERS_H_

#include <limits.h>
#include <math.h>
#include <stdint.h>

static inline float DequantizeInt8ToFloat(int8_t value, float scale,
                                          int zero_point) {
    return (float)(value - zero_point) * scale;
}

static inline int8_t QuantizeFloatToInt8(float value, float scale,
                                         int zero_point) {
    int32_t result = (int32_t)lroundf(value / scale) + zero_point;
    if (result < INT8_MIN) {
        result = INT8_MIN;
    }
    if (result > INT8_MAX) {
        result = INT8_MAX;
    }
    return (int8_t)result;
}

#endif  /* MLPERF_TINY_FIRMWARE_COMMON_QUANTIZATION_HELPERS_H_ */
