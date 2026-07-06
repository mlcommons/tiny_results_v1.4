/* VWW01 (Visual Wake Words, MobileNetV1, 2 classes). Wire is 96x96x3
 * uint8 HWC RGB (27 KB). Adapted from
 * tiny/benchmark/reference_submissions/person_detection/submitter_implemented.cpp. */

#include <stddef.h>
#include <stdint.h>

#include "firmware/common/internally_implemented.h"
#include "api/submitter_implemented.h"
#include "firmware/common/eembc_shim.h"
#include "model.h"

static constexpr float kModelOutputScale = 0.00390625f;  /* 1/256 */
static constexpr int   kModelOutputZeroPoint = -128;

void th_load_tensor() {
    /* 27 KB is too big to stage on the stack; read into the model
     * arena and shift uint8 -> int8 in place. */
    uint8_t *model_input = get_model_input_buffer();
    size_t bytes = ee_get_buffer(model_input, MAX_DB_INPUT_SIZE);
    if (bytes != MAX_DB_INPUT_SIZE) {
        th_printf("e-[Input has %u bytes, expected %u]\r\n",
                  static_cast<unsigned>(bytes),
                  static_cast<unsigned>(MAX_DB_INPUT_SIZE));
        return;
    }
    int8_t *as_int8 = reinterpret_cast<int8_t *>(model_input);
    for (size_t i = 0; i < MAX_DB_INPUT_SIZE; ++i) {
        as_int8[i] = static_cast<int8_t>(model_input[i] - 128);
    }
}

void th_results() {
    emit_classifier_results(
        reinterpret_cast<const int8_t *>(get_model_output_buffer()),
        MODEL_OUTPUT_BYTES,
        kModelOutputScale, kModelOutputZeroPoint);
}
