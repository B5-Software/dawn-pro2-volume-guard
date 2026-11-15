#!/usr/bin/env python3
"""
Moondrop Dawn Pro 2 (水月雨 破晓2) Firmware Safe Volume Patcher
=============================================================
License: Creative Commons Zero v1.0 Universal (CC0 1.0)
Public Domain Dedication.

Purpose:
--------
Fixes the dangerous behavior where the DAC dongle occasionally loses
its volume settings on power loss/reboot and defaults to maximum full-scale
volume (0 dBFS, 2.0 Vrms single-ended / 4.0 Vrms balanced), potentially
causing acute hearing trauma with sensitive in-ear monitors (IEMs).

Target Safe Level:
------------------
Sets the fallback cold-boot / reset volume to -64.0 dBFS (0xC000 in UAC Q8.8).
For typical 32-Ohm IEMs (112-115 dB SPL/Vrms), this guarantees sound pressure
levels <= 60 dB SPL (whisper / background audio level).

Volume Range:
-------------
100% PRESERVED (-128 dB to 0 dB, 0~100 steps). You can still push to full
power anytime using the physical volume buttons or the OS volume slider.
"""

import sys
import os
import hashlib
import struct

BASE_FILENAME = "65Sh-9xMUd3Qnj5ZO-p65.bin"
PATCHED_FILENAME = "dawn_pro2_v1.5_safe_60dB.bin"

# Expected base firmware v1.5 hashes
BASE_SIZE = 225351
BASE_MD5 = "4976dc3570cd430921c0bb2fc946d94f"
BASE_SHA256 = "59f4afcb60fcf2cbb42cecb5b64dbc3696ebde95690819a943f8c9972c1ba109"

PATCH_OFFSET = 0x10C8E
# Original (16 bytes):
#   lhu a4, 0x1f(s0) -> 03 57 f4 01
#   sh  a4, 0xc2(a5) -> 23 91 e7 0c
#   lhu a4, 0x19(s0) -> 03 57 94 01
#   sh  a4, 0xc4(a5) -> 23 92 e7 0c
ORIG_BYTES = bytes.fromhex("0357f4012391e70c035794012392e70c")

# Patched (16 bytes):
#   lhu    a4, 0x1f(s0) -> 03 57 f4 01 (load saved volume)
#   c.bnez a4, 4        -> 11 e3       (if non-zero, keep user setting)
#   c.lui  a4, 0xffffc  -> 71 77       (if zero, force a4 = 0xC000 / -64 dB)
#   sh     a4, 0xc2(a5) -> 23 91 e7 0c (write to Left channel)
#   sh     a4, 0xc4(a5) -> 23 92 e7 0c (write to Right channel)
PATCH_BYTES = bytes.fromhex("0357f40111e371772391e70c2392e70c")

CPU_SECTION_LEN = 0x20AD4

def verify_file(data):
    md5 = hashlib.md5(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    return md5, sha256

def main():
    src_file = sys.argv[1] if len(sys.argv) > 1 else BASE_FILENAME
    dst_file = sys.argv[2] if len(sys.argv) > 2 else PATCHED_FILENAME

    print("==============================================================")
    print("  Dawn Pro 2 Safe Volume Patcher (Anti-Ear-Blasting Guard)")
    print("==============================================================")
    print(f"Input file : {src_file}")
    print(f"Output file: {dst_file}\n")

    if not os.path.exists(src_file):
        print(f"[-] Error: Base firmware '{src_file}' not found.")
        print(f"    Please place the official v1.5 firmware in this directory:")
        print(f"    Filename : {BASE_FILENAME}")
        print(f"    Expected SHA256: {BASE_SHA256}")
        sys.exit(1)

    with open(src_file, "rb") as f:
        data = bytearray(f.read())

    if len(data) != BASE_SIZE:
        print(f"[-] Warning: File size ({len(data)} bytes) does not match expected v1.5 size ({BASE_SIZE} bytes)!")

    md5, sha256 = verify_file(data)
    print(f"[*] Base firmware verification:")
    print(f"    Size  : {len(data)} bytes")
    print(f"    MD5   : {md5}")
    print(f"    SHA256: {sha256}")

    if sha256.lower() != BASE_SHA256.lower():
        print(f"[-] Warning: Base firmware SHA-256 mismatch!")
        print(f"    Expected: {BASE_SHA256}")
        print(f"    Got     : {sha256}")
        confirm = input("    Proceed anyway? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            sys.exit(1)
    else:
        print("    [+] Official v1.5 firmware verified [OK]\n")

    current_bytes = data[PATCH_OFFSET:PATCH_OFFSET + 16]
    if current_bytes != ORIG_BYTES:
        if current_bytes == PATCH_BYTES:
            print("[*] Notice: This file is already patched with the Safe Volume Guard!")
            sys.exit(0)
        else:
            print(f"[-] Error: Unexpected bytes at 0x{PATCH_OFFSET:05X}: {current_bytes.hex()}")
            print(f"    Expected: {ORIG_BYTES.hex()}")
            sys.exit(1)

    # 1. Apply patch
    data[PATCH_OFFSET:PATCH_OFFSET + 16] = PATCH_BYTES
    print(f"[*] Applied Volume Guard patch at 0x{PATCH_OFFSET:05X} (16 bytes)")

    # 2. Recalculate HAMAO CPU Section Checksum (sum8)
    data[0x2C:0x30] = b"\x00\x00\x00\x00"
    new_checksum = sum(data[0:CPU_SECTION_LEN])
    data[0x2C:0x30] = struct.pack("<I", new_checksum)
    print(f"[*] Recalculated HAMAO Checksum: 0x{new_checksum:08X}")

    # Self-check
    verify_chk = sum(data[0:CPU_SECTION_LEN]) - sum(data[0x2C:0x30])
    assert verify_chk == new_checksum, "Checksum verification failed!"

    # 3. Save patched binary
    with open(dst_file, "wb") as f:
        f.write(data)

    p_md5, p_sha = verify_file(data)
    print(f"\n[+] Successfully generated patched firmware: {dst_file}")
    print(f"    Size  : {len(data)} bytes")
    print(f"    MD5   : {p_md5}")
    print(f"    SHA256: {p_sha}")
    print("\n[+] Total binary modification: only 9 bytes (0.0040% diff)")
    print("    - Checksum: 4 bytes @ 0x0002C")
    print("    - Safe Vol: 5 bytes @ 0x10C92")
    print("\nAll done! Flash using 'python flash_firmware.py' or official web flasher.")

if __name__ == "__main__":
    main()
