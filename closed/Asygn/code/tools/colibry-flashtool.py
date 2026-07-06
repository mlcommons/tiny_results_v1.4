#*****************************************************************************************
# Copyright (c) 2026 ASYGN.
# This design is the confidential and proprietary property of ASYGN and
# the possession or use of this file requires a written license from Asygn.
#*****************************************************************************************

## This script can be used to write some binary data into the flash component
## available on the Colibry IOTboard and evaluation kit.

import numpy as np
import argparse, time, sys
from pyftdi.ftdi import Ftdi
from pyftdi.spi import SpiController, SpiIOError
from pyftdi.bits import BitSequence

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))  # Add path <current_script/../>
from colibry_interfaces.colibry_jtag_api import Colibry_jtag_api
from colibry_interfaces.colibry_spis_api import Colibry_spis_api



############################################################################################################
class JtagSpimfInterface:
    """A class to access a flash component through JTAG-FTDI USB bridge and SPIMF peripheral of Colibry."""

    COLIBRY_SPIMF_CTRL_ADDR      = 0x20015004
    COLIBRY_SPIMF_LEN_ADDR       = 0x20015008
    COLIBRY_SPIMF_STATUS_ADDR    = 0x20015010
    COLIBRY_SPIMF_TRIG_CTRL_ADDR = 0x2001500C
    COLIBRY_SPIMF_TX_PUSH_ADDR   = 0x20015018
    COLIBRY_SPIMF_RX_POP_ADDR    = 0x2001501C
    COLIBRY_PLL_CONTROL_ADDR     = 0x200100C0
    COLIBRY_CAL_BYPASS_ADDR      = 0x200100C8
    COLIBRY_SPIMF_DIO_START_ADDR = 0x200110A0
    
    SPIMF_FIFO_NBYTES            = 16
    
    def __init__(self, **opts):
        """Initialize the object."""
        self.jtag_api = Colibry_jtag_api(**opts)
        self.spimf_init()
            
    def byte_to_word(self, bytes_list):
        """Converts a list of bytes into an array of 32-bit words.
            First bytes are on the MSB sof the 32-bit words."""
        bytes_array = np.array(bytes_list).astype('uint8')
        pad_length = (4 - (bytes_array.size % 4)) % 4
        bytes_array = np.pad(bytes_array, (0, pad_length), mode='constant')
        return bytes_array.view(dtype=np.dtype('>u4'))

    def word_to_byte(self, words_list, nbyte):
        """Converts a list of 32-bit words into an array of bytes.
            First bytes are on the MSB sof the 32-bit words."""

        bytes_array = words_list.astype(np.dtype('>u4')).view(np.uint8)
        return bytes_array[:nbyte]
        
    def spimf_init(self):
        """Initializes the SPIMF peripheral of Colibry."""
        self.jtag_api.cpu_halt()
        self.jtag_api.mmap_write(self.COLIBRY_PLL_CONTROL_ADDR, 0x10E1)
        self.jtag_api.mmap_write(self.COLIBRY_CAL_BYPASS_ADDR, 0x001)
        time.sleep(0.1)
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_DIO_START_ADDR, 1)
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_DIO_START_ADDR + 4, 1)
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_DIO_START_ADDR + 8, 1)
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_DIO_START_ADDR + 12, 1)
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_LEN_ADDR, 31)
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_CTRL_ADDR, (3 << 8) + (1 << 14) + (1 << 15) + (1 << 16) + (1 << 31))
    
    def exchange(self, tx_bytes, readlen=0):
        """Exchanges (TX and RX) bytes over the SPIMF peripheral of Colibry."""
        """DMA not used."""
        nbyte = len(tx_bytes) + readlen
        tx_words = self.byte_to_word(tx_bytes + [0]*readlen)
        rx_words = np.empty(len(tx_words), dtype='uint32')
        
        rx_words_cnt = 0
        tx_bytes_cnt = 0
        
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_TRIG_CTRL_ADDR, (1 << 2), push=False) # Set CSN low
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_TRIG_CTRL_ADDR, (1 << 4), push=False)
        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_LEN_ADDR, self.SPIMF_FIFO_NBYTES * 8 - 1, push=False)
        while True:
            # Sends chunks of SPIMF_FIFO_NBYTES bytes to avoid timing issues with the SPIMF peripheral
            if nbyte - tx_bytes_cnt < self.SPIMF_FIFO_NBYTES:
                nbyte_tx_next = nbyte - tx_bytes_cnt
                self.jtag_api.mmap_write(self.COLIBRY_SPIMF_LEN_ADDR, nbyte_tx_next * 8 - 1, push=False)
            else:
                nbyte_tx_next = self.SPIMF_FIFO_NBYTES
                
            nword_tx_next = (nbyte_tx_next + 3) // 4

            if nbyte_tx_next <= 0:
                break
            else:
                self.jtag_api.mmap_write(self.COLIBRY_SPIMF_TX_PUSH_ADDR,
                                         tx_words[tx_bytes_cnt // 4 : tx_bytes_cnt // 4 + nword_tx_next], push=False)
                tx_bytes_cnt += 4 * nword_tx_next
                    
            if readlen > 0:
                for i in range(nword_tx_next):
                    rx_words[rx_words_cnt] = self.jtag_api.mmap_read(self.COLIBRY_SPIMF_RX_POP_ADDR)
                    rx_words_cnt += 1

        self.jtag_api.mmap_write(self.COLIBRY_SPIMF_TRIG_CTRL_ADDR, (1 << 3), push=False)  # Clear CSN low

        # Converts RX words to bytes
        if readlen > 0:
            rx_bytes = self.word_to_byte(rx_words, nbyte)
            return rx_bytes[len(tx_bytes):]  # Remove first bytes before read part
        else:
            return None
        

############################################################################################################
class SpiFlashInterface:
    """A class to access a flash component directly with the SPI interface."""
    def __init__(self, **opts):
        self.spi_flash = Colibry_spis_api(**opts)
        self.spi_flash.select_phy_interface(Colibry_spis_api.INTERFACE_FLASH)
            
    def exchange(self, tx_bytes, readlen=0):
        """Exchanges (TX and RX) bytes over the SPI-FTDI."""
        return self.spi_flash.spi_ctrl.exchange(tx_bytes, readlen)
        

############################################################################################################
class FlashAccess:
    """A class to access a flash component in read and write through JTAG-FTDI USB bridge"""

    FLASH_CMD_RDID      = 0x9F  # Read ID (JEDEC Manufacturer ID)
    FLASH_CMD_WREN      = 0x06  # Write Enable for Non-volatile data change
    FLASH_CMD_WRDI      = 0x04  # Write Disable
    FLASH_CMD_SE        = 0xD8  # 64kB Sector Erase
    FLASH_CMD_RDAR      = 0x65  # Read any register
    FLASH_CMD_WRAR      = 0x71  # Write any register
    FLASH_CMD_PP        = 0x02  # Page Program
    FLASH_CMD_READ      = 0x03  # Read

    FLASH_ADDR_CR1NV    = 0x02
    FLASH_ADDR_CR2NV    = 0x03
    FLASH_ADDR_CR3NV    = 0x04
    FLASH_ADDR_CR4NV    = 0x05
    FLASH_ADDR_SR1V     = 0x800000
    FLASH_ADDR_SR2V     = 0x800001
    FLASH_ADDR_CR1V     = 0x800002
    FLASH_ADDR_CR2V     = 0x800003
    FLASH_ADDR_CR3V     = 0x800004
    FLASH_ADDR_CR4V     = 0x800005

    def __init__(self, ll_interface):
        self.ll_intf = ll_interface

    def check_flash_id(self):
        """Check the flash ID can be correctly read"""
        res = list(self.ll_intf.exchange([self.FLASH_CMD_RDID], 4))  # Read ID
        if res != [0x1, 0x2, 0x19, 0x4D] and res != [0x1, 0x2, 0x17, 0x4D]:
            print("ERROR: Flash has incorrect manufacturer ID")
            print(res)
            return 1
        else:
            print('Flash component recognized')
            return 0
        
    def check_flash_access(self):
        """Check the flash registers and array can be correctly read or written"""
        print('Checking flash register access...')
        
        cr3v_register = self.read_flash_reg(self.FLASH_ADDR_CR3V)
        if (cr3v_register != 0):
            print("ERROR: cr3v_register incorrect reset value")
            return 1

        self.write_flash_reg(self.FLASH_ADDR_CR3V, 0x1)
        cr3v_register = self.read_flash_reg(self.FLASH_ADDR_CR3V)
        if (cr3v_register != 1):
            print("ERROR: cr3v_register incorrect written value")
            return 2

        print("Flash register access OK")
        self.write_flash_reg(self.FLASH_ADDR_CR3V, 0x0)

        print('Checking flash array access...')
        self.write_to_flash(0x200, [(x+10) % 256 for x in range (20000)])
        first_rdata = self.read_flash_array(0x200, 8)
        last_rdata  = self.read_flash_array(0x501C, 8)
        
        if first_rdata != [x for x in range(10,18)] or last_rdata != [38, 39, 40, 41, 255, 255, 255, 255]:
            print("ERROR: incorrect flash read data")
            print(first_rdata, last_rdata)
            return 3

        print('Flash access successful')
        return 0

    def read_flash_reg(self, addr):
        """Read a flash internal register"""
        bytes = self.ll_intf.exchange([self.FLASH_CMD_RDAR, (addr >> 16) & 0xff,
                                         (addr >> 8) & 0xff, addr & 0xff], 4)
        return bytes[3]  # Take into account the read latency
        
    def write_flash_reg(self, addr, value):
        """Write a flash internal register"""
        self.flash_write_enable(True)
        self.ll_intf.exchange([self.FLASH_CMD_WRAR, (addr >> 16) & 0xff,
                                 (addr >> 8) & 0xff, addr & 0xff, value], 0)
        self.wait_flash_write()
        return

    def read_flash_array(self, addr, nbyte):  # 24-bit address
        """Read nbyte bytes from the flash array, starting at addr."""
        bytes = self.ll_intf.exchange([self.FLASH_CMD_READ, (addr >> 16) & 0xff,
                                         (addr >> 8) & 0xff, addr & 0xff], nbyte)
        return list(bytes)
    
    def flash_write_enable(self, enable):
        """Enable of disable writing/erasing the flash array."""
        if enable:
            self.ll_intf.exchange([self.FLASH_CMD_WREN], 0)
        else:
            self.ll_intf.exchange([self.FLASH_CMD_WRDI], 0)
            
    def wait_flash_write(self, time_ms=0):
        """Ensure flash write has finished. If time_ms is specified, use a fixed delay."""
        if time_ms == 0:
            while True:  # Wait until job is finished
                time.sleep(0.001)
                wip_bit = self.read_flash_reg(self.FLASH_ADDR_SR1V) & 1  # WIP = SR1V[0]
                if (wip_bit == 0):
                    break
        else:
            time.sleep(time_ms / 1000)
            
    def sectors_erase(self, list_of_sectors):
        """Erase the sectors given in the list. Each sector is assumed to be 64kB, up to 511 sectors."""
        for k in list_of_sectors:
            addr = k * 2**16
            self.flash_write_enable(True)
            bytes = self.ll_intf.exchange([self.FLASH_CMD_SE, (addr >> 16) & 0xff,
                                             (addr >> 8) & 0xff, addr & 0xff], 0)
            self.wait_flash_write()
            if self.read_flash_reg(self.FLASH_ADDR_SR1V) & (1 << 5) != 0:
                print("Error: Sector erase error detected")
            
    def write_to_flash(self, addr, byte_list, erase=True):
        """Writes all byte_list bytes consecutively into the flash array, starting at addr.
           If erase is True, the corresponding pages are erased beforehand.
           It is assumed that written sectors are 64kB with other sectors (4kB) mapped to high addresses.
           addr should preferably be 256-byte aligned (page start)."""
        if erase:
            if self.read_flash_reg(self.FLASH_ADDR_CR1V) & (1 << 2) == 0:
                print("Configuring the flash in 64kB sectors at bottom")
                self.write_flash_reg(self.FLASH_ADDR_CR1NV, 1 << 2) # Set TBPARM_O=1
            sector_low = addr // 2**16
            sector_high = (addr + len(byte_list)) // 2**16
            sector_list = [x for x in range(sector_low, sector_high+1)]
            
            print("Erasing sectors (64kB size)", sector_list)
            self.sectors_erase(sector_list)
            
        print("Writing to flash...")
        t = time.time()

        byte_idx = 0
        while byte_idx < len(byte_list):
            curr_addr = addr + byte_idx
            page_byte_left = 256 - (curr_addr % 256)
            transaction = [self.FLASH_CMD_PP, (curr_addr >> 16) & 0xff, (curr_addr >> 8) & 0xff, curr_addr & 0xff]
            transaction += [byte_list[byte_idx + x] for x in range(page_byte_left) if byte_idx + x < len(byte_list)]
            self.flash_write_enable(True)
            self.ll_intf.exchange(transaction)
            self.wait_flash_write(1)
            if byte_idx >= 10*1024 and byte_idx % (10 * 1024) < 256:
                print("%d/%d kB written" % (byte_idx // 1024, len(byte_list) // 1024))
            byte_idx += page_byte_left
            
        if self.read_flash_reg(self.FLASH_ADDR_SR1V) & (1 << 6) != 0:
            print("Error: Page programming error detected")

        elapsed = time.time() - t
        print("Time elapsed: %.2fs" % elapsed)
        
############################################################################################################

def str2int(valstr):
    """Convert string to integer, handling hex format."""
    res = 0
    if valstr[0] == '0' and len(valstr) == 1:
        return int(valstr)
    elif valstr[0] == '0' and valstr[1] == 'x':
        return int(valstr, base=16)
    else:
        try:
            res = int(valstr)
            return res
        except ValueError as e:
            print("[ERROR] str2int(): input format not a number: %s" % e)
            return None

        
def main():
    # Parsing arguments
    #
    parser = argparse.ArgumentParser(description='Colibry Binary Flash Tool.')
    parser.add_argument('--check_only', action='store_true', help='Only checks access to the flash.')

    parser.add_argument('binary', type=str, nargs="?", default=None, help='Binary file to be flashed in memory.')
    parser.add_argument('address', type=str, nargs="?", default=None, help='First byte address in flash memory.')
    parser.add_argument('-p', default=None, type=str, help='USB Port for FTDI component (eg. ftdi://ftdi:232h:x/1)')
    parser.add_argument('-i', default='jtag', type=str, choices=["jtag", "spi"], help='Low-level flash interface used')

    args = parser.parse_args()
        
    # Selects interface
    #
    if args.i == 'jtag':
        flash_ll_interface = JtagSpimfInterface(freq=2E6, channel=1, p=args.p)
        print("------------------------------------------------------------")
        print("Using JTAG interface")
        print("------------------------------------------------------------")
    else:
        flash_ll_interface = SpiFlashInterface(freq=10E6, channel=2, p=args.p)
        print("------------------------------------------------------------")
        print("Using Flash SPI interface")
        print("------------------------------------------------------------")
        
    flash_access = FlashAccess(flash_ll_interface)
    
    # Checks the flash
    #
    print('Reading Flash ID...')
    if flash_access.check_flash_id():
        exit(1)

    if args.check_only:
        flash_access.check_flash_access()
        return 0
    
    # Program the binary file
    #
    if args.binary is None or args.address is None:
        print("<binary> and <address> arguments should be provided")
        print("Nothing done")
        return 0

    address_int = str2int(args.address)
    with open(args.binary, "rb") as file:
        byte_data = file.read()
        byte_array = list(byte_data)

        flash_access.write_to_flash(address_int, byte_array, erase=True)
    
if __name__ == "__main__":
    main()
