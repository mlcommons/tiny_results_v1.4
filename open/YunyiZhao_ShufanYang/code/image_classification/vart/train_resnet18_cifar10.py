"""Fast CIFAR-10 ResNet-18 training at native 32x32 (no resize)."""
import os, time
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torchvision
from torchvision import datasets, transforms

torch.set_num_threads(int(os.environ.get('TORCH_THREADS', 12)))

OUT = '/home/yunyi/DPUCVDX8G_VAI_v3.0/mlperf_tiny_submission/training/resnet18_cifar10_trained.pth'
DATA_DIR = '/home/yunyi/DPUCVDX8G_VAI_v3.0/mlperf_tiny_submission/cifar10'
EPOCHS = int(os.environ.get('EPOCHS', 8))
BATCH = int(os.environ.get('BATCH', 256))
INPUT_SIZE = int(os.environ.get('INPUT_SIZE', 32))   # native CIFAR-10 size

mean = (0.4914, 0.4822, 0.4465)
std  = (0.2470, 0.2435, 0.2616)

train_tf = transforms.Compose([
    transforms.RandomCrop(32, padding=4),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize(mean, std),
])
test_tf = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean, std),
])

train_set = datasets.CIFAR10(DATA_DIR, train=True, download=False, transform=train_tf)
test_set  = datasets.CIFAR10(DATA_DIR, train=False, download=False, transform=test_tf)

train_loader = torch.utils.data.DataLoader(train_set, batch_size=BATCH, shuffle=True, num_workers=4, persistent_workers=True)
test_loader  = torch.utils.data.DataLoader(test_set, batch_size=BATCH, shuffle=False, num_workers=2, persistent_workers=True)

print(f"Training ResNet-18 CIFAR-10 at {INPUT_SIZE}x{INPUT_SIZE}, batch={BATCH}, epochs={EPOCHS}", flush=True)

# Use a CIFAR-style ResNet-18: replace conv1 (7x7 s=2) with 3x3 s=1 and drop maxpool
# This is the standard CIFAR ResNet-18 modification — it preserves spatial resolution
# at the inputs and is the de-facto baseline for CIFAR-10 image classification.
model = torchvision.models.resnet18(num_classes=10)
model.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
model.maxpool = nn.Identity()

opt = optim.SGD(model.parameters(), lr=0.1, momentum=0.9, weight_decay=5e-4, nesterov=True)
sched = optim.lr_scheduler.OneCycleLR(opt, max_lr=0.1, epochs=EPOCHS, steps_per_epoch=len(train_loader))
loss_fn = nn.CrossEntropyLoss()
print(f"Steps per epoch: {len(train_loader)}", flush=True)

best_acc = 0.0
def eval_acc():
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for x, y in test_loader:
            out = model(x)
            correct += (out.argmax(1) == y).sum().item()
            total += y.size(0)
    return 100 * correct / total

for epoch in range(EPOCHS):
    t0 = time.time()
    model.train()
    running = 0.0
    nb = 0
    t_batch = time.time()
    for i, (x, y) in enumerate(train_loader):
        opt.zero_grad()
        out = model(x)
        loss = loss_fn(out, y)
        loss.backward()
        opt.step()
        sched.step()
        running += loss.item()
        nb += 1
        if (i + 1) % 20 == 0:
            now = time.time()
            print(f"epoch {epoch+1} batch {i+1}/{len(train_loader)} loss={running/nb:.3f} batch_t={(now-t_batch)/20:.2f}s lr={opt.param_groups[0]['lr']:.4f}", flush=True)
            t_batch = now
    acc = eval_acc()
    elapsed = time.time() - t0
    print(f"=== epoch {epoch+1}/{EPOCHS}: train_loss={running/nb:.3f} test_acc={acc:.2f}% time={elapsed:.1f}s ===", flush=True)
    if acc > best_acc:
        best_acc = acc
        torch.save({'state_dict': model.state_dict(), 'input_size': INPUT_SIZE, 'mean': mean, 'std': std,
                   'arch': 'resnet18-cifar (conv1=3x3-s1, maxpool=Identity)'}, OUT)
        print(f"  >> saved best (acc={best_acc:.2f}%) to {OUT}", flush=True)

print(f"DONE. Best accuracy: {best_acc:.2f}%")
