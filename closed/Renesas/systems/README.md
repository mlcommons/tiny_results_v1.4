# Table of Contents
- [Overview](#overview)
- [General Operation](#general-operation)
- [Prerequisites](#prerequisites)
  - [Software](#software)
  - [Hardware (Renesas Products)](#hardware-renesas-products)
  - [Hardware (For Measurement)](#hardware-for-measurement)
- [Project Layout](#project-layout)
- [Getting Started](#getting-started)
  - [Import Projects in e2 studio](#import-projects-in-e2-studio)
  - [Build Projects](#build-projects)
  - [Flash Firmware](#flash-firmware)
- [Runner Environment and Configuration](#runner-environment-and-configuration)
  - [Install Runner Dependencies](#install-runner-dependencies) 
- [Measurement Workflows](#measurement-workflows)
  - [Accuracy and Performance Measurement](#accuracy-and-performance-measurement)
  - [Energy Measurement](#energy-measurement)
- [Benchmark Commands](#benchmark-commands)
  - [Anomaly Detection (ad)](#anomaly-detection-ad)
  - [Image Classification IC01 (ic)](#image-classification-ic01-ic)
  - [Image Classification IC02 (ic2)](#image-classification-ic02-ic2)
  - [Keyword Spotting (kws)](#keyword-spotting-kws)
  - [Visual Wake Words (vww)](#visual-wake-words-vww)
- [Submission Artifacts](#submission-artifacts)


# Overview

This directory contains the Renesas closed-division MLPerf Tiny v1.4 implementation for EK-RA8P1.

Target platform:

- Board: EK-RA8P1
- CPU: Arm Cortex-M85 @ 1000 MHz + Arm Cortex-M33 @ 250 MHz
- NPU: Arm Ethos-U55 @ 500 MHz
- Inference stack: Renesas MERA (AOT-compiled C inference)

Benchmarks:

- AD (Anomaly Detection)
- IC01 (Image Classification)
- IC02 (Image Classification)
- KWS (Keyword Spotting)
- VWW (Visual Wake Words)

Supported runner modes:

- Accuracy (`--mode=a`)
- Performance (`--mode=p`)
- Energy (`--mode=e`)

# General Operation

The MLCommons Tiny runner coordinates benchmark execution by communicating with:

- DUT (EK-RA8P1 firmware)
- Power monitor (for energy mode)

For each run, the runner writes session logs and results to:

```text
~tiny/benchmark/runner/sessions/<YYYYMMDD_HHMMSS>/
```

Standard outputs:

- `log.txt`
- `results.txt`
- `results.json`

# Prerequisites

## Software

- Renesas e2 studio IDE
- LLVM Embedded Toolchain for Arm (from e2 studio)
- Renesas FSP compatible with these projects
- Python 3.8+
- MLCommons Tiny runner: https://github.com/mlcommons/tiny/tree/master/benchmark/runner


## Hardware (Renesas Products)

- EK-RA8P1 evaluation kit

## Hardware (For Measurement)

- Joulescope JS220 with GPI0 support
- USB-A to USB-C cable: Host PC to JS220
- USB-A to USB-C cable: Host PC to EK-RA8P1 J10 (J-Link OB debugger)
- Board modifications required for isolated MCU measurement:
    - **R3 removed**: Breaks P3V3 to P3V3_MCU connection (insertion point for JS220 shunt)
    - **R2 removed**: Breaks P3V3 to P3V3_USB connection (USB subsystem excluded from measurement)
- Test leads:
    - JS220 Current− connected to TP3 (P3V3 side of R3 break)
    - JS220 Current+ connected to TP1 (P3V3_MCU side of R3 break)
    - JS220 Voltage− connected to TP3
    - JS220 Voltage+ connected to TP1
    - JS220 GPI0 connected to P413 (PMOD1 Pin 10) for energy window bracketing
    - JS220 GND connected to PMOD1 Pin 11
    - JS220 io_voltage set to 3.3V (MCU logic level)  
- UART access to EK-RA8P1 virtual COM port at 115200 baud for runner communication

# Project Layout

Each benchmark directory contains prebuilt binaries and a zipped e2 studio source project:

```text
closed/Renesas/code/ek-ra8p1/
  ad/
    Binary/
    Source_Code/Anomaly_Detection_CPU_NPU.zip
  ic/
    Binary/
    Source_Code/Image_Classification_01_CPU_NPU.zip
  ic2/
    Binary/
    Source_Code/Image_Classification_02_CPU_NPU.zip
  kws/
    Binary/
    Source_Code/Keyword_Spotting_CPU_NPU.zip
  vww/
    Binary/
    Source_Code/Visual_Wake_Words_CPU_NPU.zip
  README.md
```

# Getting Started

## Import Projects in e2 studio

1. Open e2 studio.
2. Go to `File -> Import -> General -> Rename & Import Existing C/C++ Project into Workspace`.
3. Unzip the benchmark source archive first.
   - IC01 example: `closed/Renesas/code/ek-ra8p1/ic/Source_Code/Image_Classification_01_CPU_NPU.zip`
4. In the import dialog, browse to the extracted project directory (not the `.zip` file).
5. Complete import.
6. Repeat the above steps for other benchmarks (`AD,IC02,KWS and VWW`)

## Build Projects

1. open the configuration xml file by double click create the libraries by generate rigth top buttom cliock
2. In Project Explorer, right-click the project.
3. Select `Build Project`.

## Flash Firmware

1. Connect EK-RA8P1 through onboard debugger USB.
2. Program/run using e2 studio launch configuration.
3. After flashing, firmware waits for runner commands over UART.

# Runner Environment and Configuration

## Install Runner Dependencies

### 1. Python and Environment Setup (Required: Python 3.8+ and <3.10) 

Create virtual environment and activate 
```bash
python -m venv .venv 
source .venv/bin/activate 
```

### 2. Clone MLCommons Tiny repository
```bash
git clone https://github.com/mlcommons/tiny.git
cd ~tiny/benchmark/runner
```

### 2.1 Modify file: device_under_test.py (Increase wait time to avoid fail)
change 30s to 600s in Line 97

    result = self._port.send_command(command, timeout=30.0)  
    -->  
    result = self._port.send_command(command, timeout=600.0)  

copy the tests_performance.yaml (systems folder) into the runner directory

### 3. Install dependencies
```bash
pip install -r ~tiny/benchmark/reference_submissions/requirements.txt 
```
### 4. Detect DUT USB VID:PID
Identify the connected board and confirm the serial path.

```bash
python3 -m serial.tools.list_ports -v
```

Expected output pattern:

```text
/dev/ttyACM0 ... VID:PID=1366:1024
```

### 5. Create device configuration YAML

Update runner device files for your host ports and attached devices:
>- `devices_ek_ra8p1.yaml` for the EK-RA8P1 + JS220 setup used for energy measurement
- `devices_ad.yaml` or `devices_kws_ic_vww.yaml` for non-energy runner setups, if used

Set these fields correctly:
>- DUT serial settings (baud/port)
- Power monitor identification (JS220)
- GPI0 trigger line mapping used by the measurement window


### 6. Generate IC01 dataset .bin files from CIFAR-10
Move to the training folder, link the dataset, generate files, and copy them into the evaluation dataset path.

```bash
cd ~/tiny/benchmark/training/image_classification

# Install dependencies
pip install -r requirements.txt

# Link downloaded CIFAR-10 to the expected path
ln -sf ~/.keras/datasets/cifar-10-batches-py-target/cifar-10-batches-py  cifar-10-batches-py

# Generate 200 .bin files and y_labels.csv
python3 perf_samples_loader.py

# Copy generated files to evaluation dataset directory
cp perf_samples/*.bin ~/tiny/benchmark/evaluation/datasets/ic01/

# Verify expected item count: 201 (200 .bin + y_labels.csv)
ls ~/tiny/benchmark/evaluation/datasets/ic01/ | wc -l
```

Prepare the other datasets under a common directory:

```text
<dataset_path>/
    ad01/
    ic01/
    ic02/
    kws01/
    vww01/
```

# Measurement Workflows

## Accuracy and Performance Measurement

Direct host-to-DUT connection is sufficient.

1. Flash benchmark firmware.
2. Connect host USB to EK-RA8P1 virtual COM/UART.
3. Confirm DUT serial settings in device YAML.
4. Run with `--mode=a` or `--mode=p`.

## Energy Measurement

Energy mode measures MCU and NPU core power only, with USB subsystem excluded.

**Board Modifications (Required):**

1. Remove **R3** resistor to isolate P3V3_MCU from P3V3, creating the P3V3/P3V3_MCU break point (TP3/TP1).
2. Remove **R2** resistor to isolate P3V3_USB from P3V3, ensuring USB subsystem power does not flow through the JS220 shunt.

**Hardware Connection:**

1. Connect Host PC USB-A to Joulescope JS220.
2. Connect Host PC USB-A to EK-RA8P1 J10 (J-Link OB on-board debugger, VID:PID 1366:1024).
3. Route inline current path through JS220 shunt:
   - JS220 Current− → TP3 (P3V3 side, after R3 removal)
   - JS220 Current+ → TP1 (P3V3_MCU side, after R3 removal)
4. Route voltage sense:
   - JS220 Voltage− → TP3
   - JS220 Voltage+ → TP1
5. Route trigger signal:
   - JS220 GPI0 → P413 pin (PMOD1 Pin 10)
   - JS220 GND → PMOD1 Pin 11
6. Configure JS220 io_voltage to 3.3V (MCU GPIO logic level).
7. Confirm stable 3.3V supply and common ground.

**Power Flow:**

- J10 USB-C → onboard regulator → P3V3 → TP3 (R3 break)
- JS220 shunt at TP3/TP1 measures MCU core + NPU current
- TP1 → P3V3_MCU → RA8P1 MCU + Ethos-U55 NPU (measured)
- P3V3_USB isolated by R2 removal (not measured, USB subsystem excluded)

**Execution Workflow:**

1. **Flash firmware** for target benchmark onto EK-RA8P1.  
2. **Verify power telemetry in Joulescope UI:**  

    - Current reading: typically 100-300 mA (MCU + NPU compute)  
    - Voltage reading: 3.3V (stable supply)  
    - GPI0 signal visible on P413 (P413 idle = HIGH, active batch = LOW, done = HIGH)  

3. **Verify UART communication with DUT:**  

    ```bash  
       python3 -m serial.tools.list_ports -v  
       python3 -c " 
       import serial, time  
       s = serial.Serial('/dev/ttyACM0', 115200, timeout=2)  
       s.write(b'name%')  
       time.sleep(0.5)  
       print(s.read_all().decode())  
       s.close()  
       "  
    ```

    Confirm DUT responds with valid model ID.  

4. **Test GPI0 trigger mechanism:** Start a benchmark run and observe P413 transitions:

    - Falling edge when batch starts (event 00)
    - Rising edge when batch completes (event 01)


5. **Close Joulescope UI** before running MLCommons runner to prevent device-access conflicts.

6. **Run with** `--mode=e`


# Benchmark Commands

**Run from `~tiny/benchmark/runner`.**


## Anomaly Detection (ad)

```bash
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_accuracy.yaml --device_list=devices_ad.yaml --mode=a
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_performance.yaml --device_list=devices_ad.yaml --mode=p
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_energy.yaml --device_list=devices_ek_ra8p1.yaml --mode=e
```

## Image Classification IC01 (ic)

```bash
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_accuracy.yaml --device_list=devices_kws_ic_vww.yaml --mode=a
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_performance.yaml --device_list=devices_kws_ic_vww.yaml --mode=p
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_energy.yaml --device_list=devices_ek_ra8p1.yaml --mode=e
```

## Image Classification IC02 (ic2)

```bash
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_accuracy.yaml --device_list=devices_kws_ic_vww.yaml --mode=a
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_performance.yaml --device_list=devices_kws_ic_vww.yaml --mode=p
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_energy.yaml --device_list=devices_ek_ra8p1.yaml --mode=e
```

## Keyword Spotting (kws)

```bash
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_accuracy.yaml --device_list=devices_kws_ic_vww.yaml --mode=a
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_performance.yaml --device_list=devices_kws_ic_vww.yaml --mode=p
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_energy.yaml --device_list=devices_ek_ra8p1.yaml --mode=e
```

## Visual Wake Words (vww)

```bash
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_accuracy.yaml --device_list=devices_kws_ic_vww.yaml --mode=a
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_performance.yaml --device_list=devices_kws_ic_vww.yaml --mode=p
python3 main.py --dataset_path=/path/to/datasets --test_script=tests_energy.yaml --device_list=devices_ek_ra8p1.yaml --mode=e
```

# Submission artifacts

Collect runner outputs from each session directory:

```text
~tiny/benchmark/runner/sessions/<timestamp>/

   ↓  AUTO-GENERATED → sessions/<timestamp>/ 

           ├── log.txt    
           ├── results.json   
           └── results.txt  
```
 