#*****************************************************************************************
# Copyright (c) 2026 ASYGN.
# This design is the confidential and proprietary property of ASYGN and
# the possession or use of this file requires a written license from Asygn.
#****************************************************************************************

from pyftdi.ftdi import Ftdi
from pyftdi.spi import SpiController, SpiIOError
import numpy as np
import io, re, time

class Colibry_spis_api:
    """API to drive the SPI from an FTDI chip, relying on pyftdi package. The Colibry boards can use this API
    to drive the SPI toward the external flash memory or the Colibry SPIS interface."""

    SPI_MODE          = 0    # Mode0 = CPOL(0), CPHA(0). Mode2 = CPOL(1), CPHA(0)
    CSN_COLIBRY       = 0
    CSN_FLASH         = 1

    INTERFACE_SPI     = 0
    INTERFACE_FLASH   = 1
    EVALBOARD         = 0x01
    EVALBOARD_TINY    = 0x02

    GPIO_CONFIG_MAP_EVALBOARD     = 0x60
    GPIO_CONFIG_SPIS_EVALBOARD    = 0x20
    GPIO_CONFIG_FLASH_EVALBOARD   = 0x40
    CSN_SPIS_INDEX_EVALBOARD      = 0
    CSN_FLASH_INDEX_EVALBOARD     = 1
    
    GPIO_CONFIG_MAP_EVBTINY       = 0x60
    GPIO_CONFIG_SPIS_EVBTINY      = 0x20
    GPIO_CONFIG_FLASH_EVBTINY     = 0x40
    CSN_SPIS_INDEX_EVBTINY        = 0
    CSN_FLASH_INDEX_EVBTINY       = 0
    
    GPIO_CONFIG_MAP_OTHERS        = 0x60
    GPIO_CONFIG_SPIS_OTHERS       = 0x20
    GPIO_CONFIG_FLASH_OTHERS      = 0x40
    CSN_SPIS_INDEX_OTHERS         = 0
    CSN_FLASH_INDEX_OTHERS        = 1
    
    SPIS_NOP_OPCODE           = 0xF8000000
    SPIS_READ_MMAP_OPCODE     = 0xA1B2C301
    SPIS_WRITE_MMAP_OPCODE    = 0xA1B2C324
    SPIS_BURST_RD_INIT_OPCODE = 0xA1B2C335
    SPIS_BURST_WR_INIT_OPCODE = 0xA1B2C336
    SPIS_READ_HM0360_OPCODE   = 0xA1B2C364
    SPIS_WRITE_HM0360_OPCODE  = 0xA1B2C365
    SPIS_MMAP_VAL_RSP         = 0x87FED101
    SPIS_BURST_DATA_RSP       = 0x87FED120
    
    SCU_CORE_MSG0_ADDR        = 0x20010050

    BURST_WORD_LEN = 8                  # In words of 32 bits, SPIS max 256 bits
    BURST_BYTE_LEN = BURST_WORD_LEN * 4

    
    def __init__(self, **opts):
        """Initialize the object."""
        self.spictrl = SpiController(cs_count=2)   # -> Control 2 SPI slaves
        self.board_model = self.EVALBOARD
        self.connect(opts["freq"], opts["channel"], opts["p"])
    
    def __del__(self, **opts):
        try:
            #if self.board_model == EVALBOARD:
            #    self.gpio_spi.write(self.GPIO_CONFIG_DEFAULT_EVALBOARD)
            #elif self.board_model == EVALBOARD_TINY:
            #    self.gpio_spi.write(self.GPIO_CONFIG_DEFAULT_EVBTINY)
            #else:
            #    self.gpio_spi.write(self.GPIO_CONFIG_DEFAULT_OTHERS)

            # Set back GPIOs as inputs
            if self.board_model == self.EVALBOARD:
                self.gpio_spi.set_direction(self.GPIO_CONFIG_MAP_EVALBOARD, 0)
            elif self.board_model == self.EVALBOARD_TINY:
                self.gpio_spi.set_direction(self.GPIO_CONFIG_MAP_EVBTINY, 0)
            else:
                self.gpio_spi.set_direction(self.GPIO_CONFIG_MAP_OTHERS, 0)
        except:
            pass
            
    def show_devices(self):
        """Show FTDI devices."""
        f = Ftdi()
        f.show_devices()

    def get_device(self, channel):
        """Get an available device."""
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
        """Connect the FTDI device in SPI."""
        self.show_devices()
        if port is None:
            self.sn = self.get_device(channel)
            if self.sn is None:
                print("No FTDI SPI device found. Exiting.")
                exit()
            # Board model detection
            if "4232hp" in self.sn:
                self.board_model = self.EVALBOARD_TINY
            else:
                self.board_model = self.EVALBOARD
            port = self.sn
        self.spictrl.configure(port)
        self.gpio_spi = self.spictrl.get_gpio() # Set GPIO port to manage extra pins
         # Set GPIOs to outputs
        if self.board_model == self.EVALBOARD:
            self.gpio_spi.set_direction(self.GPIO_CONFIG_MAP_EVALBOARD, self.GPIO_CONFIG_MAP_EVALBOARD)
        elif self.board_model == self.EVALBOARD_TINY:
            self.gpio_spi.set_direction(self.GPIO_CONFIG_MAP_EVBTINY, self.GPIO_CONFIG_MAP_EVBTINY)
        else:
            self.gpio_spi.set_direction(self.GPIO_CONFIG_MAP_OTHERS, self.GPIO_CONFIG_MAP_OTHERS)
        self.FREQUENCY = freq
        self.select_phy_interface(self.INTERFACE_SPI)
        print("Connected to %s." % port)
    
    def select_phy_interface(self, interface):
        """Configure the board GPIOs to select the SPI (interface=INTERFACE_SPI or INTERFACE_FLASH)."""
        if interface == self.INTERFACE_SPI:
            if self.board_model == self.EVALBOARD:
                self.gpio_spi.write(self.GPIO_CONFIG_SPIS_EVALBOARD)
                self.spi_ctrl = self.spictrl.get_port(cs=self.CSN_SPIS_INDEX_EVALBOARD, freq=self.FREQUENCY, mode=self.SPI_MODE)
            elif self.board_model == self.EVALBOARD_TINY:
                self.gpio_spi.write(self.GPIO_CONFIG_SPIS_EVBTINY)
                self.spi_ctrl = self.spictrl.get_port(cs=self.CSN_SPIS_INDEX_EVBTINY, freq=self.FREQUENCY, mode=self.SPI_MODE)
            else:
                self.gpio_spi.write(self.GPIO_CONFIG_SPIS_OTHERS)
                self.spi_ctrl = self.spictrl.get_port(cs=self.CSN_SPIS_INDEX_OTHERS, freq=self.FREQUENCY, mode=self.SPI_MODE)
        else:
            if self.board_model == self.EVALBOARD:
                self.gpio_spi.write(self.GPIO_CONFIG_FLASH_EVALBOARD)
                self.spi_ctrl = self.spictrl.get_port(cs=self.CSN_FLASH_INDEX_EVALBOARD, freq=self.FREQUENCY, mode=self.SPI_MODE)
            elif self.board_model == self.EVALBOARD_TINY:
                self.gpio_spi.write(self.GPIO_CONFIG_FLASH_EVBTINY)
                self.spi_ctrl = self.spictrl.get_port(cs=self.CSN_FLASH_INDEX_EVBTINY, freq=self.FREQUENCY, mode=self.SPI_MODE)
            else:
                self.gpio_spi.write(self.GPIO_CONFIG_FLASH_OTHERS)
                self.spi_ctrl = self.spictrl.get_port(cs=self.CSN_FLASH_INDEX_OTHERS, freq=self.FREQUENCY, mode=self.SPI_MODE)
        
    def append_field(self, field, field_size):
        """Append a field to current transaction."""
        for i in range(field_size):
            bit_idx = 7 - (self.transaction_idx % 8)
            byte_idx = self.transaction_idx // 8

            if (self.transaction_idx % 8 == 0):
                self.transaction += [0]

            self.transaction[byte_idx] |= ((field >> (field_size - 1 - i)) & 1)  << bit_idx
            self.transaction_idx += 1
    
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

    def mmap_read(self, addr):
        """Read a 32-bit word in the memory map"""
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_READ_MMAP_OPCODE, 32)
        self.append_field(addr, 32)

        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)
        
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_NOP_OPCODE, 32)
        self.append_field(self.SPIS_NOP_OPCODE, 32)

        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)

        returned_data = self.extract_field(read_buf, 32, 32)

        return returned_data

    def mmap_write(self, addr, data):
        """Write a 32-bit word in the memory map"""
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_WRITE_MMAP_OPCODE, 32)
        self.append_field(addr, 32)
        self.append_field(data, 32)

        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)

    def mmap_readburst(self, addr, ndata, byte_array=False):
        """Burst read access by data of 32 bits"""
        returned_data = []
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_BURST_RD_INIT_OPCODE, 32)
        self.append_field(addr, 32)
        self.append_field(ndata * 4, 32)
        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_NOP_OPCODE, 32)
        self.append_field(0, self.BURST_WORD_LEN*32 - 32)

        for k in range(int(np.ceil(ndata / self.BURST_WORD_LEN))):
            remaining_data_words = min(self.BURST_WORD_LEN, ndata - k*self.BURST_WORD_LEN)

            if remaining_data_words != self.BURST_WORD_LEN:
                self.transaction = self.transaction[:remaining_data_words*4]
                
            read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True, droptail=0)

            for l in range(len(read_buf) // 4):
                if byte_array:
                    returned_data += [read_buf[l*4+3], read_buf[l*4+2], read_buf[l*4+1], read_buf[l*4]]
                else:
                    returned_data += [(read_buf[l*4] << 24) + (read_buf[l*4+1] << 16) +
                                      (read_buf[l*4+2] << 8) + read_buf[l*4+3]]
        return returned_data

    def bin_copy(self, f_in, addr):
        """Burst write access"""
        data = f_in.read()
        data_idx = 0

        # Ensure a multiple of 4 bytes is provided for a full burst 
        while len(data) % 4 != 0:
            data += bytes([0])
        nword = len(data) // 4
            
        # Initialize burst write
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_BURST_WR_INIT_OPCODE, 32)
        self.append_field(addr, 32)
        self.append_field(len(data), 32)
        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)

        for k in range(int(np.ceil(nword / self.BURST_WORD_LEN))):
            self.transaction = []

            for l in range(min(self.BURST_WORD_LEN, nword - k*self.BURST_WORD_LEN)):
                self.transaction += [data[data_idx + 3], data[data_idx + 2], data[data_idx + 1], data[data_idx]]
                data_idx += 4

            read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True, droptail=0)

    def hm0360_read(self, addr):
        """Read a register to the HM0360 through I2CM"""
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_READ_HM0360_OPCODE, 32)
        self.append_field(addr, 32)

        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)

        time.sleep(0.01)
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_NOP_OPCODE, 32)
        self.append_field(self.SPIS_NOP_OPCODE, 32)

        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)

        returned_data = self.extract_field(read_buf, 32, 32)

        return returned_data

    def hm0360_write(self, addr, data):
        """Write a register to the HM0360 through I2CM"""
        self.transaction = []
        self.transaction_idx = 0
        self.append_field(self.SPIS_WRITE_HM0360_OPCODE, 32)
        self.append_field(addr, 16)
        self.append_field(data, 16)

        read_buf = self.spi_ctrl.exchange(self.transaction, duplex=True,
                                           droptail=(8-(self.transaction_idx % 8)) % 8)
        
    def descramble_spi_img_dma(self, img_spi, height, width, depth):
        """Reorder the pixels from the image received (img_spi) and moved in memory from DMA.
           'img_spi' is a list of bytes. Caution: only depth=1 supported in this version."""
        img = np.empty((height,width), dtype='uint8')
        w = 0
        h = 0
        for val in img_spi: 
            img[h,w] = val
            if (w < width - 1):
                w += 1
            else:
                w = 0
                h += 1
        return img

    def descramble_spi_img_nnpa(self, img_spi, height, width, depth, yuyv=0):
        """Reorder the pixels from the image received (img_spi) and moved in memory from NNPA.
           'img_spi' is a list of bytes. Caution: only depth=1 supported in this version."""
        img = np.empty((height,width), dtype='uint8')
        row_addr_incr = ((width*(2**yuyv) + 1) // 2)
        if depth == 1:
            pack_lvl = 3
        elif depth == 3:
            pack_lvl = 1
        else:
            print("Error: only depth 1 or 3 supported")
            
        subaddr_mask = 2**pack_lvl - 1
        for h in range(height):
            for w in range(width):
                mem_row = h * row_addr_incr + (w*(2**yuyv) // 2)
                mem_bank = (h + w*(2**yuyv)) % 2 # Banks data shifted on successive rows
                mem_col = mem_bank * 8
                # Compute real address with packing
                mem_col = mem_col + (mem_row & subaddr_mask) * (8 >> pack_lvl)
                mem_row = mem_row >> pack_lvl
                img[h,w] = img_spi[mem_row * 16 + mem_col]
        
        return img
