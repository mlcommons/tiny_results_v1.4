#*****************************************************************************************
# Copyright (c) 2026 ASYGN.
# This design is the confidential and proprietary property of ASYGN and
# the possession or use of this file requires a written license from Asygn.
#****************************************************************************************

from pyftdi.ftdi import Ftdi
from pyftdi.jtag import JtagEngine, JtagTool
from pyftdi.bits import BitSequence
from collections.abc import Iterable
import numpy as np
import time
import io, re


class Colibry_jtag_api:
    "API to access Colibry JTAG peripheral through JTAG-FTDI USB bridge"

    JTAG_INSTR = {
        'IDCODE'  : BitSequence('00001', msb=True, length=5),
        'DTMCSR'  : BitSequence('10000', msb=True, length=5),
        'DMI'     : BitSequence('10001', msb=True, length=5),
        'BYPASS'  : BitSequence('11111', msb=True, length=5)}

    DMI_CMD = {
        'NOP'   : 0x0,
        'READ'  : 0x1,
        'WRITE' : 0x2}
    
    BURST_BYTE_LEN = 256         # Must be multiple of 4
    BURST_DATA_LEN = 64          # In words of 32 bits

    def __init__(self, **opts):
        """Initialize the object."""
        self.jtag = JtagEngine(trst=False, frequency=opts["freq"])
        self.connect(opts["freq"], opts["channel"], opts["p"])
        self.self_curr_mmap_waddr = 0
            
    def show_devices(self):
        """Show FTDI devices."""
        f = Ftdi()
        f.show_devices()

    def get_device(self, channel):
        """Get an available JTAG device."""
        f = Ftdi()
        devices = f.list_devices()
        for decriptor, device in devices:
            if ("Serial Converter" in decriptor.description or "Quad RS232-HS" in decriptor.description or
                "FT4232H MiniModule" in decriptor.description):
                for key, val in f.PRODUCT_IDS[f.FTDI_VENDOR].items():
                    if decriptor.pid == val:
                        return f"ftdi://ftdi:%s:{hex(decriptor.bus)[2:]}:{hex(decriptor.address)[2:]}/%d" % (key, channel)
        return None

    def connect(self, freq, channel, port=None):
        """Connect the FTDI device in JTAG."""
        self.show_devices()
        if port is None:
            self.sn = self.get_device(channel)
            if self.sn is None:
                print("No FTDI SPI device found. Exiting.")
                exit()
            port = self.sn
        print("Connecting to %s ..." % port)
        self.jtag.configure(port)
        self.jtag.reset()
        self.read_idcode()

        ## Enable register access through APB
        self.jtag_init()
        
        """For the protocol, see https://riscv.org/wp-content/uploads/2024/12/riscv-debug-release.pdf
        IR=instruction register, DR=data register
        See Table 6.1 for instructions implemented in the RISC-V
        See Table 3.8 for DMI/DM registers allowing indirect accesses"""

    def append_field(self, field, field_size):
        """Append a field to current transaction."""
        for i in range(field_size):
            bit_idx = 7 - (self.transaction_idx % 8)
            byte_idx = self.transaction_idx // 8

            if (self.transaction_idx % 8 == 0):
                self.transaction += [0]

            self.transaction[byte_idx] |= ((field >> (field_size - 1 - i)) & 1)  << bit_idx
            self.transaction
        
    def append_bytes(self, byte_array, reverse_bytes=False):
        """Append bytes to current transaction."""
        if self.transaction_idx % 8 != 0:
            print("Error: transaction must be byte-aligned to call append_bytes")
            return

        if reverse_bytes:  # Bytes endianness reversed by groups of 4 bytes
            for k in range(len(byte_array) // 4):
                self.transaction += [byte_array[k * 4 + 3]]
                self.transaction += [byte_array[k * 4 + 2]]
                self.transaction += [byte_array[k * 4 + 1]]
                self.transaction += [byte_array[k * 4 + 0]]
                self.transaction_idx += 32
            pass
        else:
            for k in byte_array:
                self.transaction += [k]
                self.transaction_idx += 8
        
    def extract_field(self, read_buffer, start, field_size):
        """Extract a field from read_buffer."""
        field_idx = start
        out_field = 0
        for i in range(field_size):
            bit_idx  = 7 - (field_idx % 8)
            byte_idx = field_idx // 8

            curr_bit = (read_buffer[byte_idx] >> bit_idx) & 1
            out_field |= curr_bit << (field_size - i - 1)
            field_idx += 1

        return out_field

    def read_idcode(self):
        """Read JTAG ID code."""
        self.jtag.reset()
        instr = self.JTAG_INSTR['IDCODE']
        self.jtag.reset()
        self.jtag.write_ir(instr)
        idcode = self.jtag.read_dr(32)
        self.jtag.go_idle()
        print("  JTAG IDCODE: 0x%08x" % int(idcode))
        if int(idcode) != 0x249511c3:
            print("ERROR: Unable to connect to Colibry target.")
            exit()

    def read_dmi(self, addr):
        """JTAG DMI read."""
        self.jtag.write_ir(self.JTAG_INSTR['DMI'])
        seq = self.DMI_CMD['READ'] + (0x0 << 2) + (int(addr) << 34)
        self.jtag.write_dr(BitSequence(seq, msb=False, length=41))
        seq = self.DMI_CMD['NOP'] + (0x0 << 2) + (int(addr) << 34)
        self.jtag.write_dr(BitSequence(seq, msb=False, length=41))
        read_seq = self.jtag.read_dr(41)
        return (int(read_seq) >> 2) & 0xFFFFFFFF

    def write_dmi(self, addr, data):
        """JTAG DMI write."""
        self.jtag.write_ir(self.JTAG_INSTR['DMI'])
        seq = self.DMI_CMD['WRITE'] + (int(data) << 2) + (int(addr) << 34)
        self.jtag.write_dr(BitSequence(seq, msb=False, length=41))

    def jtag_init(self):
        """Enables system bus access."""
        self.jtag.reset()
        val = self.read_dmi(0x10)   # Read DMControl
        val = val | 1
        self.jtag.reset()
        self.write_dmi(0x10, val)  # Write to DMControl
        self.jtag.read_dr(41)      # Apply write by shifting register
        val = self.read_dmi(0x38)  # Read SBCS
        val = val | (1 << 20)
        self.jtag.reset()
        self.write_dmi(0x38, val)  # Write to SBCS
        self.jtag.read_dr(41)      # Apply write by shifting register

    def cpu_halt(self):
        """Halt the CPU."""
        self.jtag.reset()
        self.write_dmi(0x10, 0x80000001)  # Write to DMControl
        self.jtag.read_dr(41)             # Apply write by shifting register
        print("CPU halted")

    def cpu_restart(self, boot_address=0x10000000):
        """Restart/resume the CPU."""
        self.jtag.reset()
        self.write_dmi(0x04, boot_address)  # Write the BOOT address to data0
        self.write_dmi(0x17, 0x002307B1)  # Abstract command: write DPC CSR
        self.write_dmi(0x10, 0x60000001)  # Write to DMControl -> resume + reset
        self.jtag.read_dr(41)             # Apply write by shifting register
        
    def mmap_read(self, addr):
        """Colibry JTAG read access."""
        self.jtag.reset()
        self.write_dmi(0x39, addr)  # Write to sbaddress0 (0x39)
        val = self.read_dmi(0x3C)   # Read sbdata0
        return val

    def mmap_write(self, addr, data, push=True):
        """Colibry JTAG write access. push=False saves time but write access is effective on next access."""
        self.jtag.reset()
        if self.self_curr_mmap_waddr != addr:
            self.write_dmi(0x39, addr)  # Write to sbaddress0 (0x39)
            self.self_curr_mmap_waddr = addr
        
        if isinstance(data, Iterable):
            for d in data:
                self.write_dmi(0x3C, d)  # Write to sbdata0 (0x3C)
                self.jtag.sync()         # Ensure write is done
        else:
            self.write_dmi(0x3C, data)  # Write to sbdata0 (0x3C)
            self.jtag.sync()            # Ensure write is done
        if push:
            self.jtag._ctrl._read_bytes(4)

    def mmap_writeburst(self, addr, data):
        """Colibry JTAG write access in burst."""
        self.jtag.reset()
        sbcs_curr = self.read_dmi(0x38)   # Read SBCS
        sbcs_new = sbcs_curr | (1 << 16)  # Enable sbautoincrement
        self.jtag.reset()
        self.write_dmi(0x38, sbcs_new)    # Write to SBCS
        self.write_dmi(0x39, addr - 4)    # Write to sbaddress0 (0x39)
        for d in data:
            self.write_dmi(0x3C, d)       # Write to sbdata0 (0x3C)
        self.jtag.reset()
        self.write_dmi(0x38, sbcs_curr)   # Write to SBCS
        self.jtag.sync()                  # Ensure write is done
        self.jtag._ctrl._read_bytes(4)
    
    def mmap_readburst(self, addr, ndata):
        """Colibry JTAG burst read access by data of 32 bits."""
        returned_data = []
        self.jtag.reset()
        for k in range(ndata):
            returned_data += [self.mmap_read(addr + k * 4)]
        return returned_data

    def bin_copy(self, f_in, addr):
        """Colibry JTAG copy of bin content."""
        data = f_in.read()
        # Ensure a multiple of 4 bytes is provided for a full burst 
        while len(data) % 4 != 0:
            data += bytes([0])

        tx_data = []
        for k in range(len(data) // 4):
            tx_data += [(data[k*4 + 3] << 24) + (data[k*4 + 2] << 16) + (data[k*4 + 1] << 8) + data[k*4]]

        self.mmap_writeburst(addr, tx_data) # Write in burst mode
