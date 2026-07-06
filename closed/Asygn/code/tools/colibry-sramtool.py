#*****************************************************************************************
# Copyright (c) 2026 ASYGN.
# This design is the confidential and proprietary property of ASYGN and
# the possession or use of this file requires a written license from Asygn.
#*****************************************************************************************

## This script can be used to write some binary data into Colibry SRAM or NNPA SRAM.

import numpy as np
import argparse, time, sys

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))  # Add path <current_script/../>


COLIBRY_SRAM_START    = 0x10000000
COLIBRY_SRAM_END      = COLIBRY_SRAM_START + 128*1024 - 1
COLIBRY_NNPAMEM_START = 0x30001000
COLIBRY_NNPAMEM_END   = COLIBRY_NNPAMEM_START + 640*1024 - 1
NNPA_CONTROL_REG      = 0x30000008
SCU_CORE_CTRL_REG     = 0x20010030
SCU_EXT_MSG_0_REG     = 0x20010070
PLL_CONTROL_REG       = 0x200100C0
SCU_HF_CLK_CFG_REG    = 0x20010000


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
    parser = argparse.ArgumentParser(description='Colibry Binary to SRAM Tool.')
    parser.add_argument('binary', type=str, nargs="?", default=None, help='Binary file to be stored in memory.')
    parser.add_argument('address', type=str, nargs="?", default=None, help='First byte address in SRAM.')
    parser.add_argument('-p', default=None, type=str, help='USB Port for FTDI component (eg. ftdi://ftdi:232h:x/1)')
    parser.add_argument('-i', default='jtag', type=str, choices=["jtag", "spis", "spid"], help='Low-level interface used')
    parser.add_argument('-msg', default=None, type=str, help='Message (number) to write into SCU_EXT_MSG_0')
    parser.add_argument('--run', action='store_true', help='Switch to reset and start the CPU after upload.')
    args = parser.parse_args()
        
    # Selects interface
    #
    if args.i == 'jtag':
        from colibry_interfaces.colibry_jtag_api import Colibry_jtag_api
        colibry_ll_interface = Colibry_jtag_api(freq=2E6, channel=1, p=args.p)
        print("------------------------------------------------------------")
        print("Using JTAG interface")
        print("------------------------------------------------------------")
    elif args.i == 'spid':
        from colibry_interfaces.colibry_spid_api import Colibry_spid_api
        colibry_ll_interface = Colibry_spid_api(freq=1E6, p=args.p)
        print("------------------------------------------------------------")
        print("Using SPID interface")
        print("------------------------------------------------------------")
    else:
        from colibry_interfaces.colibry_spis_api import Colibry_spis_api
        colibry_ll_interface = Colibry_spis_api(freq=1E6, channel=2, p=args.p)
        print("------------------------------------------------------------")
        print("Using SPIS interface")
        print("------------------------------------------------------------")
        
        
    # Check parameters
    #
    if args.binary is None or args.address is None:
        print("<binary> and <address> arguments should be provided")
        print("Nothing written in memory")

    else:
        if args.i == 'jtag':  # Running JTAG halt the CPU
            colibry_ll_interface.cpu_halt()
        else:
            colibry_ll_interface.mmap_write(SCU_CORE_CTRL_REG, 2)
            
        address_int = str2int(args.address)
        
        if (address_int >= COLIBRY_SRAM_START and address_int <= COLIBRY_SRAM_END) or \
           (address_int >= COLIBRY_NNPAMEM_START and address_int <= COLIBRY_NNPAMEM_END):
            if address_int >= COLIBRY_NNPAMEM_START:
                # Ensure the NNPAMEM is available for the system
                colibry_ll_interface.mmap_write(NNPA_CONTROL_REG, 1 << 3)
            # Upload the binary file
            #
            print("Writing to SRAM... ", end="")
            with open(args.binary, 'rb') as f:
                colibry_ll_interface.bin_copy(f, address_int)
            print("Done")
        else:
            print("ERROR: address is outside Colibry SRAM or NNPAMEM area")
            print("Nothing written in memory")
            return 2
    
    if args.msg is not None:
        print("Writing message in SCU_EXT_MSG_0 register")
        colibry_ll_interface.mmap_write(SCU_EXT_MSG_0_REG, str2int(args.msg))
        if  args.i == 'jtag':
            colibry_ll_interface.cpu_restart()

    if args.run:
        print("Starting CPU")
        colibry_ll_interface.mmap_write(PLL_CONTROL_REG, 0x10E1)  # Ensure the system has a clock
        colibry_ll_interface.mmap_write(SCU_HF_CLK_CFG_REG, 2)
        if  args.i == 'jtag':
            colibry_ll_interface.cpu_restart()
            colibry_ll_interface.mmap_write(SCU_CORE_CTRL_REG, 1)
        else:
            colibry_ll_interface.mmap_write(SCU_CORE_CTRL_REG, 2)
            colibry_ll_interface.mmap_write(SCU_CORE_CTRL_REG, 1)

        
if __name__ == "__main__":
    main()
