/* IC01 (Image Classification, CIFAR-10 ResNet): 32x32x3 uint8 in,
 * 10-class softmax out. Adapted from
 * tiny/benchmark/reference_submissions/image_classification/submitter_implemented.cpp. */

#include <stddef.h>
#include <stdint.h>

#include "firmware/common/internally_implemented.h"
#include "api/submitter_implemented.h"
#include "firmware/common/eembc_shim.h"
#include "model.h"

/* QuantSoftmax tail (canonical TFLite int8 softmax). Re-extract after
 * retrain via `jq '.model_graph[-1].module_specs |
 * .output_scale, .output_zp' models/closed/ic01/schema.json`. */
static constexpr float kModelOutputScale = 0.00390625f;  /* 1/256 */
static constexpr int   kModelOutputZeroPoint = -128;

void th_load_tensor() {
    /* Wire is uint8 [0..255]; model wants int8 [-128..127]. */
    uint8_t staged[MAX_DB_INPUT_SIZE];
    size_t bytes = ee_get_buffer(staged, MAX_DB_INPUT_SIZE);
    if (bytes != MAX_DB_INPUT_SIZE) {
        th_printf("e-[Input has %u bytes, expected %u]\r\n",
                  static_cast<unsigned>(bytes),
                  static_cast<unsigned>(MAX_DB_INPUT_SIZE));
        return;
    }
    int8_t *model_input = reinterpret_cast<int8_t *>(get_model_input_buffer());
    for (size_t i = 0; i < MAX_DB_INPUT_SIZE; ++i) {
        model_input[i] = static_cast<int8_t>(staged[i] - 128);
    }
}

void th_results() {
    emit_classifier_results(
        reinterpret_cast<const int8_t *>(get_model_output_buffer()),
        MODEL_OUTPUT_BYTES,
        kModelOutputScale, kModelOutputZeroPoint);
}
