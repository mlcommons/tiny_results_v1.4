# VART (Vitis-AI Runtime) — Image Classification (`ic01`)

Open-division image-classification submission for the **VCK190 ACAP**
(Xilinx Versal XCVC1902 + DPUCVDX8G_ISA3_C32B3).

## Problem

CIFAR-10 image classification (10 classes, 32 × 32 RGB). Reference
benchmark `ic01`; 200-image curated perf set (`tiny/benchmark/evaluation/datasets/ic01/y_labels.csv`).

## Model

CIFAR-style ResNet-18 — torchvision `resnet18(num_classes=10)` with the
ImageNet stem replaced for 32 × 32 inputs:

| Stage          | Spec                                                                |
| -------------- | ------------------------------------------------------------------- |
| Input          | 1 × 3 × 32 × 32 (NCHW), uint8 [0, 255] → CIFAR-10 normalisation     |
| `conv1`        | Conv 3×3, stride 1, padding 1, 64 ch (replaces upstream 7×7 stride 2) |
| `bn1`+ReLU     | BatchNorm + ReLU                                                    |
| `maxpool`      | **Identity** (replaces upstream 3×3 max-pool)                       |
| `layer1`       | 2 × BasicBlock(64 → 64)                                             |
| `layer2`       | 2 × BasicBlock(64 → 128, first block stride 2)                      |
| `layer3`       | 2 × BasicBlock(128 → 256, first block stride 2)                     |
| `layer4`       | 2 × BasicBlock(256 → 512, first block stride 2)                     |
| `avgpool`+FC   | Adaptive avg-pool → Linear(512, 10)                                 |

After Vitis-AI NNDCT quantisation every `BatchNorm2d` is folded into the
preceding `Conv2d`, so the deployed xmodel contains **zero BN ops** —
inference runs entirely on the DPU.

Parameter count: ~11 M (FP32 .pth = 44 MB, INT8 xmodel = 11 MB).

## Calibration data

200 batches × 1 image of the CIFAR-10 **train** split, sampled uniformly
with `torchvision.datasets.CIFAR10(train=True)`. Same normalisation as
training: `mean=(0.4914, 0.4822, 0.4465)`, `std=(0.2470, 0.2435, 0.2616)`.

## Quality target

Open division has no fixed target. We report the achieved numbers:

| Metric                   | Value         |
| ------------------------ | ------------- |
| Top-1 accuracy           | 85.0 %        |
| AUC                      | 0.984         |
| Median throughput        | 1849.722 inf./sec. |
| Per-image latency        | 0.541 ms      |

## Files

| File                                         | Role                                                                 |
| -------------------------------------------- | -------------------------------------------------------------------- |
| `dut_main.cpp`                               | C++17 DUT firmware (built and run on the board)                       |
| `run_vck190.py`                              | Thin wrapper around the upstream MLCommons runner (`tiny/benchmark/runner/main.py`); bypasses USB auto-discovery and points the upstream `DUT` class at `/dev/ttyUSB1` |
| `tests_performance_vck190.yaml`              | Performance test script (5 windows × 20 000 inferences ≥10 s/window) |
| `devices_vck190.yaml`                        | Device manifest                                                       |
| `train_resnet18_cifar10.py`                  | Open-division training recipe (PyTorch SGD + OneCycleLR, 4 epochs)   |
| `quantize_pipeline/quantize_resnet18_trained.py` | Vitis-AI NNDCT quantiser (folds BN into Conv, calibrates on real CIFAR-10) |
| `quantize_pipeline/compile_xmodel.sh`        | `vai_c_xir` compile to xmodel for DPUCVDX8G_ISA3_C32B3                |
| `trained_models/resnet18_cifar10_trained.pth`| FP32 PyTorch weights (44 MB) — open-division reference                |
| `compiled_models/resnet18_cifar10_fused.xmodel` | INT8 DPU model used on board (11 MB; zero BN ops)                  |

## "Same code in accuracy and performance modes"

The MLPerf Tiny rule "the same code must be run for both modes" applies to
the **DUT firmware**: both runs are driven against the same
`vck190_mlperf_dut` binary built from `dut_main.cpp`. The only difference
is the host-side runner script (`tests_accuracy.yaml` vs.
`tests_performance_vck190.yaml`), which sets the iteration count — that is
explicitly supported by the upstream runner and required to satisfy the
performance-mode 10 s minimum-runtime rule on fast hardware.

## Reproducing the results

```bash
# 1. Train (host, ~40 min CPU)
python3 train_resnet18_cifar10.py    # produces trained_models/resnet18_cifar10_trained.pth

# 2. Quantise + compile (Vitis-AI Docker)
docker run --rm -v <repo>:/workspace --user $(id -u):$(id -g) -e HOME=/tmp \
    -w /workspace/.../code/image_classification/vart/quantize_pipeline \
    xilinx/vitis-ai-pytorch-cpu:latest bash -c "
        source /opt/vitis_ai/conda/etc/profile.d/conda.sh && conda activate vitis-ai-pytorch
        python quantize_resnet18_trained.py --quant_mode calib --batch_size 1
        python quantize_resnet18_trained.py --quant_mode test --deploy --batch_size 1
        bash compile_xmodel.sh
    "
# -> compiled_models/resnet18_cifar10_fused.xmodel

# 3. Build the DUT firmware on the board
ssh root@<vck190>
cd /run/media/mmcblk0p1
g++ -O2 -std=c++17 dut_main.cpp -I/tmp/glog_shim \
    -lvart-runner -lvart-util -lxir -l:libglog.so.0 -lpthread \
    -o /tmp/vck190_mlperf_dut

# 4. Free the console UART and start the firmware
dmesg -n 1 ; echo 0 > /proc/sys/kernel/printk
nohup /tmp/vck190_mlperf_dut --uart /dev/ttyAMA0 \
    --xclbin /run/media/mmcblk0p1/dpu.xclbin \
    --xmodel /run/media/mmcblk0p1/resnet18_cifar10_fused.xmodel &

# 5. From the host, drive the runner over /dev/ttyUSB1
python3 run_vck190.py -p /dev/ttyUSB1 -m a                                   # accuracy
python3 run_vck190.py -p /dev/ttyUSB1 -m p -t tests_performance_vck190.yaml  # performance
```

## Runner provenance

Upstream MLCommons runner from
[mlcommons/tiny](https://github.com/mlcommons/tiny) at master, commit
`5dae329`. Reused verbatim — the wrapper at `run_vck190.py` only replaces
the `DeviceManager.scan()` USB auto-discovery (which expects
ST-Link/Arduino VID/PIDs of the reference DUTs). All upstream logic for
`Script`, `DataSet`, `DUT`, and `summarize_result` runs unchanged.
