/* IC02 (larger ResNet variant of IC01). Same wire format and output
 * shape; only the model differs. */

#include <stddef.h>
#include <stdint.h>

#include "firmware/common/internally_implemented.h"
#include "api/submitter_implemented.h"
#include "firmware/common/eembc_shim.h"
#include "model.h"

static constexpr float kModelOutputScale = 0.00390625f;  /* 1/256 */
static constexpr int   kModelOutputZeroPoint = -128;

void th_load_tensor() {
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
