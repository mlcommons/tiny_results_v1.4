"""
Runner wrapper for the VCK190 DUT (or its host simulator).

The upstream main.py auto-discovers DUTs by USB VID/PID. For our setup the
DUT is either:
  - a Linux process on the VCK190 connected over /dev/ttyUSB1 (FT4232HL ch B)
  - a host PTY produced by simulator/dut_simulator.py

In either case we want to bypass the auto-discovery and point the DUT
directly at a serial device path. This wrapper does that, then re-uses
the upstream Script / Dataset / DUT classes verbatim.

Outputs match the upstream runner exactly:
  sessions/<timestamp>/log.txt
  sessions/<timestamp>/results.txt
  sessions/<timestamp>/results.json
"""
import argparse, os, sys, time, json, importlib.util
from datetime import datetime

# Re-use the upstream runner code as a library.
RUNNER_DIR = '/home/yunyi/DPUCVDX8G_VAI_v3.0/mlperf_tiny_submission/tiny/benchmark/runner'
sys.path.insert(0, RUNNER_DIR)

import yaml
from datasets import DataSet
from device_under_test import DUT
from script import Script
from main import summarize_result, parse_test_script
from script import log_filename  # this gets created at import time

ap = argparse.ArgumentParser()
ap.add_argument('-p', '--port', required=True, help="Serial device path (e.g. /dev/pts/3 or /dev/ttyUSB1)")
ap.add_argument('-b', '--baud', type=int, default=115200)
ap.add_argument('-s', '--dataset_path', default='/home/yunyi/DPUCVDX8G_VAI_v3.0/mlperf_tiny_submission/datasets')
ap.add_argument('-t', '--test_script', default=None)
ap.add_argument('-m', '--mode', choices=['a', 'p'], default='a')
ap.add_argument('--model_id', default='ic01')
args = ap.parse_args()

if args.test_script is None:
    args.test_script = (f'{RUNNER_DIR}/tests_accuracy.yaml' if args.mode == 'a'
                        else f'{RUNNER_DIR}/tests_performance.yaml')

print(f"Wrapper: port={args.port} baud={args.baud} mode={args.mode}")
print(f"         dataset={args.dataset_path}")
print(f"         test_script={args.test_script}")

# Construct DUT directly with the manual port (bypasses DeviceManager USB scan)
dut = DUT(args.port, baud_rate=args.baud)
test_scripts = parse_test_script(args.test_script)

# Identify the model the DUT advertises
with dut as d:
    time.sleep(2)  # give DUT a moment to flush boot banner
    d.get_name()
    d.get_model()
    d.get_profile()

print(f"Identified DUT model: {dut._model}")
script_def = test_scripts.get(dut._model)
if script_def is None:
    raise SystemExit(f"No script for model {dut._model} in {args.test_script}")

script = Script(script_def)
ds = DataSet(os.path.join(args.dataset_path, dut._model), script.truth)
result = script.run(None, dut, ds, args.mode)

if isinstance(result, dict):
    result = [result]
for r in result:
    r["mode"] = args.mode

session_dir = os.path.dirname(log_filename)
results_file = os.path.join(session_dir, "results.txt")
summarize_result(result, power=None, mode=args.mode, results_file=results_file)
with open(os.path.join(session_dir, "results.json"), 'w') as f:
    json.dump(result, f)

print(f"\nSession written to: {session_dir}")
print(f"  results.txt    -> {results_file}")
print(f"  results.json   -> {session_dir}/results.json")
print(f"  log.txt        -> {log_filename}")
