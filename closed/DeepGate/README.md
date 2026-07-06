# DeepGate MLPerf Tiny v1.4 closed-division submission

## Layout

```
closed/DeepGate/
├── README.md                                                # this file
├── code/
│   └── firmware/                                            # Zephyr source tree for the DUT firmware (one app per benchmark)
│       ├── common/
│       │   ├── internally_implemented.{cpp,h}              # Vendored EEMBC harness; byte-identical with tiny/benchmark/api/
│       │   ├── quantization_helpers.h                      # QuantizeFloatToInt8 / DequantizeInt8ToFloat; ported from tiny/benchmark/util/
│       │   ├── main.cpp, eembc_shim.{cpp,h}, dwt_timestamp.{cpp,h}
│       │   └── boards/<board>.{overlay,conf}
│       └── <bench>/                                        # one of ad01, ic01, ic02, kws01, vww01
│           ├── src/submitter_implemented.cpp               # per-bench th_load_tensor / th_results; mirrors tiny/benchmark/reference_submissions/<bench>/
│           ├── api/submitter_implemented.h                 # per-bench EEMBC API extension
│           ├── model/<board>/                              # precompiled artefacts (one set per board)
│           │   ├── lib/libmodel.a                          # static library produced by the DeepGate Bitweaver compiler per (board, bench)
│           │   └── include/model.h
│           └── CMakeLists.txt
├── results/<board>/<bench>/                                # runner outputs per (board, benchmark, mode)
│   ├── performance/                                        # m-lap-us-... timestamps; results.json + results.txt
│   └── accuracy/                                           # top-1 / AUC summary; results.json + results.txt
└── systems/<board>.json                                    # system description, one per board
```

## Boards

| Board id (Zephyr) | Description |
|---|---|
| `nucleo_h7a3zi_q` | STM32H7A3 Nucleo (Cortex-M7, 280 MHz); primary integration board |
| `xg24_ek2703a`    | Silicon Labs xG24 Explorer Kit (Cortex-M33, 78 MHz) |

## Benchmarks

| Folder | Benchmark | Notes |
|---|---|---|
| `ic`  | Image Classification (CIFAR-10 ResNet) | uint8 wire, int8 model, 10 logits |
| `kws` | Keyword Spotting (DS-CNN, 12 classes)  | int8 wire, int8 model, 12 logits |
| `vww` | Visual Wake Words (MobileNetV1, 2 classes) | uint8 wire, int8 model, 2 logits |
| `ad`  | Anomaly Detection (autoencoder, 640-dim) | float32 wire, int8 model, single MSE |

## Build and flash

The firmware sources at `code/firmware/` in this tarball are a verbatim copy of the public source mirror at <https://github.com/deepgatelimited/mlperf-tiny>. Build by cloning that mirror and following the steps below.

```bash
git clone https://github.com/deepgatelimited/mlperf-tiny && cd mlperf-tiny

# Python venv (installs west + runner-side deps from pyproject.toml)
uv sync

# Zephyr workspace + SDK (per Zephyr's getting-started flow, with our manifest)
uv run west init -l manifest
uv run west update
uv run west packages pip | xargs uv pip install
uv run west sdk install -t arm-zephyr-eabi
uv run west zephyr-export

# Build + flash one (board, bench) pair. Group by board so you only swap
# which DUT is plugged in once.

# H7A3 / Image Classification (ic01)
uv run west build -b nucleo_h7a3zi_q firmware/ic01  && uv run west flash
# H7A3 / Image Classification (ic02, larger ResNet)
uv run west build -b nucleo_h7a3zi_q firmware/ic02  && uv run west flash
# H7A3 / Keyword Spotting (kws01)
uv run west build -b nucleo_h7a3zi_q firmware/kws01 && uv run west flash
# H7A3 / Visual Wake Words (vww01)
uv run west build -b nucleo_h7a3zi_q firmware/vww01 && uv run west flash
# H7A3 / Anomaly Detection (ad01)
uv run west build -b nucleo_h7a3zi_q firmware/ad01  && uv run west flash

# xG24 / Image Classification (ic01)
uv run west build -b xg24_ek2703a firmware/ic01  && uv run west flash
# xG24 / Image Classification (ic02, larger ResNet)
uv run west build -b xg24_ek2703a firmware/ic02  && uv run west flash
# xG24 / Keyword Spotting (kws01)
uv run west build -b xg24_ek2703a firmware/kws01 && uv run west flash
# xG24 / Visual Wake Words (vww01)
uv run west build -b xg24_ek2703a firmware/vww01 && uv run west flash
# xG24 / Anomaly Detection (ad01)
uv run west build -b xg24_ek2703a firmware/ad01  && uv run west flash
```

This repo ships precompiled `firmware/<bench>/model/<board>/{lib/libmodel.a, include/model.h}` for all 10 `(board, bench)` pairs. To regenerate from `models/closed/<bench>/schema.json`, upload it to <https://bitweaver.deepgate.ai>, pick the target board, and drop the returned files in `firmware/<bench>/model/<board>/{lib,include}/`.

## Run a benchmark

Fetch the evaluation datasets (the venv from the previous section is required):

```bash
export TINY=/path/to/your/mlcommons-tiny-clone
scripts/fetch_datasets.sh
```

`scripts/fetch_datasets.sh` defers to upstream `mlcommons/tiny`'s per-bench helpers; deviations (CIFAR-10 download for IC01, PIL transcode for VWW01 since upstream has no bin generator, `curl -L` for AD01 to handle Zenodo redirects) are inlined.

Drive `$TINY/benchmark/runner/main.py` against the flashed DUT. `runner/devices.yaml` lists both DUTs; plug in only the board you're targeting.

```bash
export REPO=$(pwd)
export DATASETS=$REPO/runner/tests/data
cd $TINY/benchmark/runner

# Accuracy (same script for both boards)
python main.py \
    --device_list=$REPO/runner/devices.yaml \
    --dataset_path=$DATASETS \
    --test_script=tests_accuracy.yaml --mode=a

# Performance (H7A3)
python main.py \
    --device_list=$REPO/runner/devices.yaml \
    --dataset_path=$DATASETS \
    --test_script=$REPO/runner/tests_performance_h7a3.yaml --mode=p

# Performance (xG24)
python main.py \
    --device_list=$REPO/runner/devices.yaml \
    --dataset_path=$DATASETS \
    --test_script=$REPO/runner/tests_performance_xg24.yaml --mode=p
```

Each run writes `log.txt`, `results.txt`, and `results.json` under `$TINY/benchmark/runner/sessions/<timestamp>/`.

## Quantization method

### Source weights

The benchmark owner publishes fp32 trained weights and an int8 reference TFLite for each of the four closed-division benchmarks. This submission's source is:

| Benchmark | Reference artifact used as source |
|---|---|
| ic01 Image Classification | Int8 reference TFLite (`pretrainedResnet_quant.tflite`); the int8 weights in our compiled `libmodel.a` are bit-identical to the reference's stored int8 weights. |
| kws01 Keyword Spotting | **fp32 reference** (`kws_ref_model_float32.tflite`). |
| vww01 Visual Wake Words | Int8 reference TFLite; bit-identical int8 weights in our compiled `libmodel.a`. |
| ad01 Anomaly Detection | Int8 reference TFLite; bit-identical int8 weights in our compiled `libmodel.a`. |

For all models except KWS01 we use the benchmark owner's supplied int8 reference TFLite directly; the int8 weights in our compiled `libmodel.a` are bit-identical to the reference's stored int8 weights, so no local quantization is performed.

KWS01 is the exception. The supplied int8 reference TFLite did not meet the v1.4 closed-division accuracy floor under our compilation pipeline, so we re-quantized from the fp32 reference (`kws_ref_model_float32.tflite`) using post-training quantization (PTQ) on the official calibration set. The PTQ result clears the 90 % top-1 floor.

### Calibration data

KWS01 is the only model that needs local calibration (see Source weights above). We use the 120 fixed validation-split indices listed in `tiny/benchmark/training/keyword_spotting/quant_cal_idxs.txt` (10 per class, 12 classes) and no other data.

### Numerical format

- **Weights:** 8-bit signed integer, stored **per-channel** along the output-channel axis for every convolution and depthwise-convolution weight tensor, and **per-tensor** for every fully-connected (matmul) weight tensor. All weight tensors use a symmetric scheme (`zero_point = 0`).
- **Activations:** 8-bit signed integer throughout the model graph; the model boundary is int8 to int8. Per-tensor asymmetric scheme.
- **Biases / intermediate accumulators:** 32-bit signed integer biases with `bias_scale = input_scale * weight_scale` per output channel. Convolution / GEMM accumulators are 32-bit signed and are requantised to int8 by a per-channel int32 multiplier + right-shift.

### Algorithm

- **Class:** post-training quantization (PTQ), for KWS01 only.
- **Weight quantisation (all benches):** deterministic symmetric mapping. `scale = max(|w|) / 127` per output channel (per-tensor for fully-connected layers); `zero_point = 0`. Weights are mapped as `int8 = clamp(round(w / scale), -127, 127)`, with `round` using banker's rounding (round-half-to-even). No stochastic rounding.
- **Activation quantisation, IC01 / IC02 / VWW01 / AD01:** adopt the per-tensor activation `scale` and `zero_point` recorded in the benchmark owner's int8 reference TFLite verbatim. No further calibration.
- **Activation quantisation, KWS01:** our PTQ on top of the fp32 reference weights. Each output-tensor observer records the running `min` and `max` of fp32 activations as the 120 official calibration samples are forwarded through the model. After the calibration pass, each `max` (and `min`, where applicable) is multiplied by `1.06` as a fixed quantization-headroom hyperparameter; final qparams are then `scale = (max - min) / 255` and `zero_point = clamp(round(-128 - min / scale), -128, 127)`. For post-ReLU outputs the observer pins `min = 0` and `zero_point = -128` and tracks only `max`. The first-layer input observer is pinned at `(scale = 0.5847029, zero_point = 83)` to match the int8 MFCC wire format the runner sends; the softmax output observer is pinned at `(scale = 1/256, zero_point = -128)` by the canonical TFLite int8 softmax convention.
- **Determinism:** deterministic. The KWS01 calibration `DataLoader` uses `shuffle = False`; sample order is fixed by index. No RNG is used in the quantisation step.

### Where the parameters live

For each `(bench, board)` pair the compiler produces:

- `code/firmware/<bench>/model/<board>/lib/libmodel.a`: the quantised graph + weights as a static library. Reproducible from `models/closed/<bench>/schema.json` (shipped in the public source bundle at <https://github.com/deepgatelimited/mlperf-tiny>) by invoking the public Bitweaver endpoint at <https://bitweaver.deepgate.ai> at the pinned compiler version.
- `code/firmware/<bench>/model/<board>/include/model.h`: declares `MODEL_INPUT_BYTES` / `MODEL_OUTPUT_BYTES`, the input/output buffer accessors, and `run_model()`. The float/int8 scale and zero-point constants live in each `code/firmware/<bench>/src/submitter_implemented.cpp`, sourced directly from the bench's `schema.json`.

## Availability evidence (Bitweaver)

DeepGate's submission claims `Status: Available` for the only proprietary piece of its inference stack: **Bitweaver**, our hosted model compiler. Everything else (Zephyr RTOS v4.4.0, picolibc, Zephyr SDK 1.0.1 / `arm-zephyr-eabi-gcc` 14.3.0) is open source.

Bitweaver runs as a production SaaS at <https://bitweaver.deepgate.ai/>. The landing page is public, names the product, and describes what it does; tier options are listed at the pricing page (<https://bitweaver.deepgate.ai/pricing>). New customers can engage today via direct sales contact for onboarding and final terms.

Bitweaver is in active use by external customers. We don't disclose customer identities publicly without their consent; if the review committee would like to discuss customer usage further, please get in touch.

Mapped to the four standard availability clauses: (1) pricing is publicly listed and final terms are by request, (2) the product has shipped to external customers, (3) the landing page itself is public evidence, and (4) the product is reasonably purchasable today via the contact path on those pages.

The exact Bitweaver version that produced every `libmodel.a` shipped under `code/firmware/<bench>/model/<board>/lib/` is pinned in each `systems/<board>.json` under `ML Model Compiler(s)`. DeepGate will keep that version reachable for as long as these results are actively used.

If anything above raises follow-up questions, please reach the registered submitter POC.
