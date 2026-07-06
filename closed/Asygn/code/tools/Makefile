# =============================================================================
# Supported configurations
# =============================================================================

BENCHMARKS := ad ic ic2 vww kws
SYSTEMS := 40mhz 300mhz
MODES := energy performance
TARGETS := toflash tosram

# =============================================================================
# Tools
# =============================================================================

PYTHON        := python3
SRAM_LOADER   := colibry-sramtool.py
FLASH_LOADER  := colibry-flashtool.py

# =============================================================================
# Parse command line arguments
#
# Usage:
# make <benchmark> <system> <mode> <toflash|tosram>
#
# Example:
# make ic 40mhz energy tosram
# make kws 300mhz performance toflash
# =============================================================================

SYSTEM     := $(filter $(SYSTEMS),$(MAKECMDGOALS))
BENCHMARK  := $(filter $(BENCHMARKS),$(MAKECMDGOALS))
MODE       := $(filter $(MODES),$(MAKECMDGOALS))
TARGET_OP  := $(filter $(TARGETS),$(MAKECMDGOALS))

# =============================================================================
# Skip argument validation for utility targets
# =============================================================================

UTILITY_TARGETS := help h

ifeq ($(MAKECMDGOALS),)
    SKIP_VALIDATION := 1
endif

ifneq ($(filter $(UTILITY_TARGETS),$(MAKECMDGOALS)),)
	SKIP_VALIDATION := 1
endif

# =============================================================================
# Validation
# =============================================================================

ifeq ($(SKIP_VALIDATION),)

ifndef SYSTEM
$(error Missing or invalid system. Supported: $(SYSTEMS))
endif

ifndef BENCHMARK
$(error Missing or invalid benchmark. Supported: $(BENCHMARKS))
endif

ifndef MODE
$(error Missing or invalid mode. Supported: $(MODES))
endif

ifndef TARGET_OP
$(error Missing or invalid target. Supported: $(TARGETS))
endif

endif

# =============================================================================
# Paths
# =============================================================================

ifeq ($(SYSTEM),40mhz)
    SYSTEM_DIR := ../colibryNPU_P1_40MHz
else ifeq ($(SYSTEM),300mhz)
    SYSTEM_DIR := ../colibryNPU_P1_300MHz
endif

BUILD_DIR := $(SYSTEM_DIR)/$(BENCHMARK)
BINARY_SRAM := $(BUILD_DIR)/$(BENCHMARK)_$(MODE).bin
BINARY_FLASH := $(BUILD_DIR)/$(BENCHMARK)_$(MODE)_flash_copy.bin
BITSTREAM := $(BUILD_DIR)/$(BENCHMARK)_bitstream.nnpa

# =============================================================================
# Memory map
# =============================================================================

SRAM_ADDR      := 0x10000000
FLASH_ADDR     := 0x0
BITSTREAM_ADDR := 0x100000

# =============================================================================
# Default target
# =============================================================================

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================

h: help

help:
	@echo "======================================================================="
	@echo " Benchmark flashing utility"
	@echo "======================================================================="
	@echo " Usage:"
	@echo "   make <benchmark> <system> <mode> <toflash|tosram>"
	@echo ""
	@echo " Benchmarks:"
	@echo "   $(BENCHMARKS)"
	@echo " Systems:"
	@echo "   $(SYSTEMS)"
	@echo " Modes:"
	@echo "   $(MODES)"
	@echo " Targets:"
	@echo "   $(TARGETS)"
	@echo ""
	@echo " Examples:"
	@echo "   make ic 40mhz energy tosram"
	@echo "   make kws 300mhz performance toflash"
	@echo ""

# =============================================================================
# Flash to SRAM and execute
# =============================================================================

tosram:
	@echo "======================================================================="
	@echo "Benchmark  : $(BENCHMARK)"
	@echo "System     : $(SYSTEM)"
	@echo "Mode       : $(MODE)"
	@echo "Operation  : SRAM boot"
	@echo "Binary     : $(BINARY_SRAM)"
	@echo "Bitstream  : $(BITSTREAM)"
	@echo "======================================================================="
	@echo ""
	@echo "Loading the bitstream..."
	@echo ""
	@OUTPUT=`$(PYTHON) $(FLASH_LOADER) $(BITSTREAM) $(BITSTREAM_ADDR) 2>&1`; \
	echo "$$OUTPUT"; \
	if echo "$$OUTPUT" | grep -q "ERROR: Unable to connect to Colibry target."; then \
		exit 1; \
	fi
	@echo ""
	@echo "Loading the program into flash memory..."
	@echo ""
	@OUTPUT=`$(PYTHON) $(SRAM_LOADER) $(BINARY_SRAM) $(SRAM_ADDR) --run 2>&1`; \
	echo "$$OUTPUT"; \
	if echo "$$OUTPUT" | grep -q "ERROR: Unable to connect to Colibry target."; then \
		exit 1; \
	fi

# =============================================================================
# Flash to external flash memory
# =============================================================================

toflash:
	@echo "======================================================================="
	@echo "Benchmark  : $(BENCHMARK)"
	@echo "System     : $(SYSTEM)"
	@echo "Mode       : $(MODE)"
	@echo "Operation  : External flash programming"
	@echo "Binary     : $(BINARY_FLASH)"
	@echo "Bitstream  : $(BITSTREAM)"
	@echo "======================================================================="
	@echo ""
	@echo "Loading the bitstream..."
	@echo ""
	@OUTPUT=`$(PYTHON) $(FLASH_LOADER) $(BITSTREAM) $(BITSTREAM_ADDR) 2>&1`; \
	echo "$$OUTPUT"; \
	if echo "$$OUTPUT" | grep -q "ERROR: Unable to connect to Colibry target."; then \
		exit 1; \
	fi
	@echo ""
	@echo "Loading the program into flash memory..."
	@echo ""
	@OUTPUT=`$(PYTHON) $(FLASH_LOADER) $(BINARY_FLASH) $(FLASH_ADDR) 2>&1`; \
	echo "$$OUTPUT"; \
	if echo "$$OUTPUT" | grep -q "ERROR: Unable to connect to Colibry target."; then \
		exit 1; \
	fi

# =============================================================================
# Prevent make from treating arguments as file targets
# =============================================================================

$(SYSTEMS):
	@:

$(BENCHMARKS):
	@:

$(MODES):
	@:

