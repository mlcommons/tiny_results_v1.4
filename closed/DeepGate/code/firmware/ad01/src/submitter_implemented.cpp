/* AD01 (Anomaly Detection, ToyCar autoencoder). Wire is 2560 bytes
 * float32 (640-dim mel-spectrogram window). We cache the float input,
 * quantize to int8 for inference, dequantize the reconstruction, and
 * emit MSE. Adapted from
 * tiny/benchmark/reference_submissions/anomaly_detection/submitter_implemented.cpp. */

#include <stddef.h>
#include <stdint.h>

#include "firmware/common/internally_implemented.h"
#include "api/submitter_implemented.h"
#include "firmware/common/quantization_helpers.h"
#include "firmware/common/eembc_shim.h"
#include "model.h"

/* Refresh after recompile via `jq '.model_graph[0].module_specs |
 * .input_scale, .input_zp, .model_graph[-1].module_specs |
 * .output_scale, .output_zp' models/closed/ad01/schema.json`. */
static constexpr float kModelInputScale = 0.39101523f;
static constexpr int   kModelInputZeroPoint = 89;
static constexpr float kModelOutputScale = 0.36449847f;
static constexpr int   kModelOutputZeroPoint = 96;

static_assert(MAX_DB_INPUT_SIZE == 2560,
              "AD01 wire is canonical FP32 (640 floats x 4 bytes)");
static_assert(MODEL_INPUT_BYTES == 640,
              "AD01 libmodel takes 640 int8 bytes (post-quantisation)");

constexpr int kFeatureCount = 640;
static float input_float[kFeatureCount];

void th_load_tensor() {
    size_t bytes = ee_get_buffer(reinterpret_cast<uint8_t *>(input_float),
                                 MAX_DB_INPUT_SIZE);
    if (bytes != MAX_DB_INPUT_SIZE) {
        th_printf("e-[Input has %u bytes, expected %u]\r\n",
                  static_cast<unsigned>(bytes),
                  static_cast<unsigned>(MAX_DB_INPUT_SIZE));
        return;
    }
    int8_t *q = reinterpret_cast<int8_t *>(get_model_input_buffer());
    for (int i = 0; i < kFeatureCount; ++i) {
        q[i] = QuantizeFloatToInt8(input_float[i], kModelInputScale,
                                   kModelInputZeroPoint);
    }
}

void th_results() {
    const int8_t *q = reinterpret_cast<const int8_t *>(
            get_model_output_buffer());
    float diffsum = 0.0f;
    for (int i = 0; i < kFeatureCount; ++i) {
        float f = DequantizeInt8ToFloat(q[i], kModelOutputScale,
                                        kModelOutputZeroPoint);
        float d = f - input_float[i];
        diffsum += d * d;
    }
    diffsum /= static_cast<float>(kFeatureCount);
    th_printf("m-results-[%0.3f]\r\n", static_cast<double>(diffsum));
}
