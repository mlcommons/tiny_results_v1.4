# Flashing Benchmarks

This directory provides a simple `Makefile` interface to program benchmark applications on the Colibry platform.

## Usage

```
make <benchmark> <system> <mode> <toflash|tosram>
```

## Parameters

### Benchmark

Available benchmarks:

* `ad`
* `ic`
* `ic2`
* `vww`
* `kws`

### System

Select the target system frequency:

* `40mhz`
* `300mhz`

### Mode

Execution mode:

* `energy`
* `performance`

### Target

Programming destination:

* `tosram` → load into SRAM and immediately run
* `toflash` → program external flash memory

---

# Examples

## Run benchmark from SRAM

```
make ic 40mhz energy tosram
```

## Program benchmark into external flash

```
make kws 300mhz performance toflash
```

---

# Help

Display available options:

```
make help
```

---

# Notes

* `tosram` automatically starts execution after loading.
* `toflash` requires a board reset or power cycle after programming.
* Python 3 is required.
* The following Python modules are required:
    - `pyftdi`
    - `numpy`
