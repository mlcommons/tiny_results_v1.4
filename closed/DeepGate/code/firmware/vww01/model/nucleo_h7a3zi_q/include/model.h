#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MODEL_INPUT_BYTES  27648
#define MODEL_OUTPUT_BYTES 2

uint8_t *get_model_input_buffer(void);
uint8_t *get_model_output_buffer(void);
int run_model(void);

#ifdef __cplusplus
}
#endif