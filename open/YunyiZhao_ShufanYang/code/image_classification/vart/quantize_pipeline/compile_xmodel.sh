#!/bin/bash
# Compile quantised xmodel for DPUCVDX8G — run inside Vitis-AI Docker.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUANT_OUTPUT="$SCRIPT_DIR/quantize_output"
COMPILE_OUTPUT="$SCRIPT_DIR/compiled_output"
ARCH_JSON="/workspace/arch.json"   # same fingerprint as deployed dpu.xclbin

mkdir -p "$COMPILE_OUTPUT"
QUANT_XMODEL=$(find "$QUANT_OUTPUT" -name "*_int.xmodel" | head -1)
[ -z "$QUANT_XMODEL" ] && { echo "No int xmodel"; exit 1; }

echo "=== Compiling for DPUCVDX8G ==="
cat "$ARCH_JSON"
vai_c_xir -x "$QUANT_XMODEL" -a "$ARCH_JSON" -o "$COMPILE_OUTPUT" -n resnet18_cifar10_fused
echo "=== Done ==="
ls -la "$COMPILE_OUTPUT/"
