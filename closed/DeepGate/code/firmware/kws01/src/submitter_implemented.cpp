/* KWS01 (Keyword Spotting, DS-CNN, 12 classes). Wire is 490 int8 MFCC
 * features (no preprocessing). Adapted from
 * tiny/benchmark/reference_submissions/keyword_spotting/submitter_implemented.cpp. */

#include <stddef.h>
#include <stdint.h>

#include "firmware/common/internally_implemented.h"
#include "api/submitter_implemented.h"
#include "firmware/common/eembc_shim.h"
#include "model.h"

static constexpr float kModelOutputScale = 0.00390625f;  /* 1/256 */
static constexpr int   kModelOutputZeroPoint = -128;

void th_load_tensor() {
    uint8_t *model_input = get_model_input_buffer();
    size_t bytes = ee_get_buffer(model_input, MAX_DB_INPUT_SIZE);
    if (bytes != MAX_DB_INPUT_SIZE) {
        th_printf("e-[Input has %u bytes, expected %u]\r\n",
                  static_cast<unsigned>(bytes),
                  static_cast<unsigned>(MAX_DB_INPUT_SIZE));
    }
}

void th_results() {
    emit_classifier_results(
        reinterpret_cast<const int8_t *>(get_model_output_buffer()),
        MODEL_OUTPUT_BYTES,
        kModelOutputScale, kModelOutputZeroPoint);
}
