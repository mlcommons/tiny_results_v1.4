Image classification 2 for MLCommons MLPerf Tiny benchmark

The boot-up takes more than 2 seconds.

Line 67 of the benchmark runner’s main.py file should be `time.sleep(2)` instead of `time.sleep(1)`.