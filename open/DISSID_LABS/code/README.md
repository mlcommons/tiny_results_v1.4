# AetherOS MLPerf Tiny v1.4 Open Division Implementation

- **Submitter**: DISSID LABS INC.
- **Repository**: [https://github.com/sidhunt/dissid-home](https://github.com/sidhunt/dissid-home)
- **Architecture**: Neural-Native Deterministic Microkernel on ARM Cortex-R52 & STM32H7
- **Verification Harness**: Headless Renode cycle-accurate simulation and Jenkins CI/CD on sovereign hardware.

### Reproducibility Commands
```bash
cargo build --target thumbv8r-none-eabihf --release -p aether-kernel
cargo test --all
python3 simulation/benchmarks/mlperf_tiny/validate_mlperf_submission.py
```
