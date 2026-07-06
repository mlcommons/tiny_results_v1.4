"""
Quantise the TRAINED ResNet-18 CIFAR-10 model for DPUCVDX8G deployment.

Differences from bn_kernel_v6_dev/.../quantize_resnet18.py:
 - Uses CIFAR-style ResNet-18 architecture (3x3 conv1 stride 1, no maxpool)
   to match the trained .pth weights.
 - Input size 32x32x3 (native CIFAR-10), no upsampling.
 - Calibration uses real CIFAR-10 train data (not random) for better
   quantisation scale selection.
 - NNDCT folds BN into Conv during graph optimisation, so the resulting
   xmodel has zero BN layers — DPU does the entire forward pass.

Run inside Vitis AI Docker:
    cd /workspace/mlperf_tiny_submission/quantize_pipeline
    conda activate vitis-ai-pytorch
    python quantize_resnet18_trained.py --quant_mode calib
    python quantize_resnet18_trained.py --quant_mode test --deploy
"""
import os, argparse, sys
import torch
import torch.nn as nn
import torchvision
from torchvision import datasets, transforms
from pytorch_nndct.apis import torch_quantizer

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = '/workspace/mlperf_tiny_submission/training/resnet18_cifar10_trained.pth'
DATA_DIR    = '/workspace/mlperf_tiny_submission/cifar10'
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, 'quantize_output')

parser = argparse.ArgumentParser()
parser.add_argument('--quant_mode', default='calib', choices=['calib', 'test'])
parser.add_argument('--deploy', action='store_true')
parser.add_argument("--batch_size", type=int, default=1)
parser.add_argument('--calib_steps', type=int, default=20)
args = parser.parse_args()

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Build CIFAR-style ResNet-18 — same as training
def build_cifar_resnet18():
    m = torchvision.models.resnet18(num_classes=10)
    m.conv1   = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
    m.maxpool = nn.Identity()
    return m

print(f"Loading trained model from {MODEL_PATH}", flush=True)
ckpt = torch.load(MODEL_PATH, map_location='cpu')
sd = ckpt['state_dict'] if isinstance(ckpt, dict) and 'state_dict' in ckpt else ckpt
mean_rgb = ckpt.get('mean', (0.4914, 0.4822, 0.4465)) if isinstance(ckpt, dict) else (0.4914, 0.4822, 0.4465)
std_rgb  = ckpt.get('std',  (0.2470, 0.2435, 0.2616)) if isinstance(ckpt, dict) else (0.2470, 0.2435, 0.2616)

model = build_cifar_resnet18()
model.load_state_dict(sd, strict=True)
model.eval()
print(f"Model loaded. Architecture: CIFAR ResNet-18 (3x3 conv1, no maxpool)", flush=True)

# Input spec: native 32x32 CIFAR-10
input_spec = torch.randn(args.batch_size, 3, 32, 32)

quantizer = torch_quantizer(
    quant_mode=args.quant_mode,
    module=model,
    input_args=(input_spec,),
    output_dir=OUTPUT_DIR,
    device=torch.device('cpu')
)
quant_model = quantizer.quant_model

if args.quant_mode == 'calib':
    # Calibrate with real CIFAR-10 train images for accurate quantisation scales
    print(f"Calibrating with real CIFAR-10 train data, {args.calib_steps} batches of {args.batch_size}", flush=True)
    tf = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean_rgb, std_rgb),
    ])
    ds = datasets.CIFAR10(DATA_DIR, train=True, download=False, transform=tf)
    loader = torch.utils.data.DataLoader(ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    quant_model.eval()
    with torch.no_grad():
        for i, (x, _) in enumerate(loader):
            quant_model(x)
            if (i + 1) % 5 == 0:
                print(f"  calib batch {i+1}/{args.calib_steps}", flush=True)
            if i + 1 >= args.calib_steps:
                break
    quantizer.export_quant_config()
    print(f"Calibration done. Config saved to {OUTPUT_DIR}", flush=True)

elif args.quant_mode == 'test':
    # Sanity test on a real CIFAR-10 sample
    print("Test inference on real CIFAR-10 sample", flush=True)
    tf = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean_rgb, std_rgb),
    ])
    ds = datasets.CIFAR10(DATA_DIR, train=False, download=False, transform=tf)
    quant_model.eval()
    correct = total = 0
    with torch.no_grad():
        loader = torch.utils.data.DataLoader(ds, batch_size=args.batch_size, shuffle=False, num_workers=0)
        for i, (x, y) in enumerate(loader):
            out = quant_model(x)
            correct += (out.argmax(1) == y).sum().item()
            total += y.size(0)
            if i + 1 >= 10:  # test on 320 samples for quick feedback
                break
    print(f"Quick INT8 test accuracy ({total} samples): {100*correct/total:.2f}%", flush=True)

    if args.deploy:
        print("Exporting quantised xmodel for deployment", flush=True)
        quantizer.export_xmodel(deploy_check=False, output_dir=OUTPUT_DIR)
        print(f"Done. Files in {OUTPUT_DIR}/", flush=True)
