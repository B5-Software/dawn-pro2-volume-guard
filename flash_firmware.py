#!/usr/bin/env python3
"""
Automated Bluetrum SPV4040 DFU Flasher for Moondrop Dawn Pro 2
=============================================================
License: Creative Commons Zero v1.0 Universal (CC0 1.0)
Public Domain Dedication.

Communicates over standard USB HID with the Bluetrum on-chip BootROM.
Protocol reversed from official Moondrop Hub (hub_index.js).
"""

import time
import struct
import zlib
import sys
import os

try:
    import hid
except ImportError:
    print("Error: 'hidapi' is required for USB communication.")
    print("Please install it via: pip install hidapi")
    sys.exit(1)

MAGIC = 0x58585542  # "BUXX"
SPV_TAG_MAGIC = 0x40565053  # "SPV@"

DAWN_PRO2_VID = 0x35D8
DAWN_PRO2_PID = 0x011D

BLUETRUM_DFU_VID = 0x0666
BLUETRUM_DFU_PID = 0x0888

class BluetrumProtocol:
    def __init__(self):
        self.seq = 0

    def reset_seq(self):
        self.seq = 0

    def create_header(self, cmd, p_type, flag=0, length=0):
        cmd_word = (cmd & 0xFF) | ((p_type & 0xFF) << 8)
        hdr10 = struct.pack('<IHBBH', MAGIC, cmd_word, self.seq & 0xFF, flag & 0xFF, length & 0xFFFF)
        self.seq += 1
        crc = zlib.crc32(hdr10) & 0xFFFFFFFF
        return hdr10 + struct.pack('<I', crc)

    def serialize(self, cmd, p_type, flag=0, content=b''):
        hdr = self.create_header(cmd, p_type, flag, len(content))
        if not content:
            return hdr
        body_crc = zlib.crc32(content) & 0xFFFFFFFF
        return hdr + content + struct.pack('<I', body_crc)

    def parse_message(self, raw):
        raw = bytes(raw)
        if len(raw) < 14:
            return None
        magic, cmd_word, seq, flag, length, hdr_crc = struct.unpack_from('<IHBBHI', raw)
        if magic != MAGIC:
            raise ValueError(f"Invalid magic: 0x{magic:08X} (expected 0x{MAGIC:08X})")
        calc_hdr_crc = zlib.crc32(raw[:10]) & 0xFFFFFFFF
        if calc_hdr_crc != hdr_crc:
            raise ValueError(f"Header CRC mismatch: 0x{calc_hdr_crc:08X} != 0x{hdr_crc:08X}")
        content = None
        if length > 0:
            if len(raw) < 14 + length + 4:
                raise ValueError(f"Incomplete payload: {len(raw)} < {14 + length + 4}")
            content = raw[14:14+length]
            body_crc = struct.unpack_from('<I', raw, 14 + length)[0]
            calc_body_crc = zlib.crc32(content) & 0xFFFFFFFF
            if calc_body_crc != body_crc:
                raise ValueError(f"Body CRC mismatch: 0x{calc_body_crc:08X} != 0x{body_crc:08X}")
        return {
            'cmd': cmd_word & 0xFF,
            'type': cmd_word >> 8,
            'seq': seq,
            'flag': flag,
            'content': content
        }

def parse_firmware(bin_path):
    with open(bin_path, 'rb') as f:
        buf = f.read()

    if len(buf) < 4096:
        raise ValueError("Firmware file too small")

    tag_magic = struct.unpack_from('<I', buf, 4)[0]
    if tag_magic != SPV_TAG_MAGIC:
        raise ValueError(f"Invalid tag magic: 0x{tag_magic:08X} (expected 'SPV@')")

    user_flag = struct.unpack_from('<I', buf, 12)[0]
    if (user_flag & 0xFFFFFF00) != 0x4F414D00:
        num_files = struct.unpack_from('<I', buf, 44)[0]
        base = 64
        stride = 32
    else:
        num_files = struct.unpack_from('<I', buf, 28)[0]
        base = 32
        stride = 16

    bin_files = []
    for r in range(num_files):
        i = base + r * stride
        name = buf[i:i+4].decode('latin1', errors='ignore').strip('\x00').strip()
        addr, size, chk = struct.unpack_from('<III', buf, i+4)
        real_offset = addr & 0x00FFFFFF
        data = b''
        if real_offset + size <= len(buf):
            data = buf[real_offset:real_offset+size]
        bin_files.append({
            'name': name,
            'address': addr,
            'size': size,
            'checksum': chk,
            'data': data
        })

    return bin_files

def main():
    bin_path = sys.argv[1] if len(sys.argv) > 1 else "dawn_pro2_v1.5_safe_60dB.bin"
    if not os.path.exists(bin_path):
        print(f"Error: Target firmware '{bin_path}' not found!")
        print("Please run 'python patch_firmware.py' first to generate it.")
        sys.exit(1)

    print("==============================================================")
    print("  Dawn Pro 2 Automated DFU Flasher")
    print("==============================================================")
    print(f"Firmware: {bin_path} ({os.path.getsize(bin_path)} bytes)")

    bin_files = parse_firmware(bin_path)
    valid_bins = [b for b in bin_files if b['size'] > 0]
    print(f"Parsed {len(bin_files)} sections ({len(valid_bins)} active):")
    for b in valid_bins:
        print(f"  - [{b['name']}] Addr: 0x{b['address']:08X}, Size: {b['size']} bytes, Chk: 0x{b['checksum']:08X}")

    # Check for DFU device or normal device
    dfu_devs = [d for d in hid.enumerate() if d['vendor_id'] == BLUETRUM_DFU_VID and d['product_id'] == BLUETRUM_DFU_PID]

    if not dfu_devs:
        dawn_devs = [d for d in hid.enumerate() if d['vendor_id'] == DAWN_PRO2_VID and d['product_id'] == DAWN_PRO2_PID]
        if not dawn_devs:
            print("\n[-] Error: Neither Dawn Pro 2 nor USB20 DFU device found.")
            print("    Please connect your Dawn Pro 2 via USB.")
            sys.exit(1)

        print("\n[1/4] Found Dawn Pro 2 in Audio Mode. Connecting...")
        dev = hid.device()
        dev.open(DAWN_PRO2_VID, DAWN_PRO2_PID)

        # Read current version
        dev.write(bytes([0x4B, 0x80, 0x0C, 0x00]))
        resp = dev.read(64, timeout_ms=500)
        if resp and len(resp) >= 8:
            ver = bytes(resp[4:]).decode('latin1', errors='ignore').strip('\x00')
            print(f"      Current firmware version: {ver}")

        # Send UPGRADE_ENTER
        print("[*] Sending UPGRADE_ENTER command...")
        dev.write(bytes([0x4B, 0x01, 0xFF, 0x00]))
        dev.close()
        print("[*] Waiting for device re-enumeration as USB20 (0x0666:0x0888)...")

        start_wait = time.time()
        while time.time() - start_wait < 6.0:
            time.sleep(0.3)
            dfu_devs = [d for d in hid.enumerate() if d['vendor_id'] == BLUETRUM_DFU_VID and d['product_id'] == BLUETRUM_DFU_PID]
            if dfu_devs:
                break

    if not dfu_devs:
        print("[-] Error: Device did not re-enumerate as USB20 in time.")
        sys.exit(1)

    print(f"\n[2/4] Connected to Bluetrum Bootloader (USB20)")
    dfu = hid.device()
    dfu.open_path(dfu_devs[0]['path'])

    proto = BluetrumProtocol()
    proto.reset_seq()

    def dfu_transceive(req, timeout_ms=2000):
        buf513 = (bytes([0x00]) + req).ljust(513, b'\x00')
        dfu.write(buf513)
        res = dfu.read(512, timeout_ms=timeout_ms)
        if not res:
            raise TimeoutError("DFU response timeout")
        return proto.parse_message(res)

    # Handshake
    print("\n[3/4] Performing Handshake...")
    hs_req = proto.serialize(16, 1, flag=1)
    hs_resp = dfu_transceive(hs_req)
    if not hs_resp or not hs_resp.get('content'):
        raise ValueError("Invalid handshake response")

    content = hs_resp['content']
    uart_div, b_ver = struct.unpack_from('<II', content, 0)
    print(f"      Bootloader ready! Version: 0x{b_ver:08X}")

    # Write sections
    print("\n[4/4] Writing firmware sections...")
    SLICE_SIZE = 256
    total_bytes = sum(b['size'] for b in valid_bins)
    written_bytes = 0

    for b in valid_bins:
        name = b['name']
        addr = b['address']
        data = b['data']
        size = len(data)
        print(f"\n[*] Writing [{name}] (Address: 0x{addr:08X}, Size: {size} bytes)...")

        area_payload = struct.pack('<IIII', addr, size, SLICE_SIZE, 0)
        set_area_req = proto.serialize(32, 1, flag=0, content=area_payload)
        dfu_transceive(set_area_req)

        num_slices = (size + SLICE_SIZE - 1) // SLICE_SIZE
        for s_idx in range(num_slices):
            s_start = s_idx * SLICE_SIZE
            s_end = min(s_start + SLICE_SIZE, size)
            slice_data = data[s_start:s_end]

            write_req = proto.serialize(33, 1, flag=0, content=slice_data)
            dfu_transceive(write_req)

            written_bytes += len(slice_data)
            pct = (written_bytes / total_bytes) * 100
            print(f"\r    Progress: {written_bytes}/{total_bytes} bytes ({pct:.1f}%)", end='', flush=True)

    print("\n\n[*] All sections written. Sending Reset command...")
    reset_req = proto.serialize(36, 1, flag=0)
    try:
        dfu_transceive(reset_req, timeout_ms=500)
    except Exception:
        pass
    dfu.close()

    print("[*] Device rebooting (2.5s)...")
    time.sleep(2.5)

    # Verification
    start_v = time.time()
    rebooted = False
    while time.time() - start_v < 8.0:
        dawn_devs = [d for d in hid.enumerate() if d['vendor_id'] == DAWN_PRO2_VID and d['product_id'] == DAWN_PRO2_PID]
        if dawn_devs:
            rebooted = True
            break
        time.sleep(0.3)

    if rebooted:
        print("[+] SUCCESS: Dawn Pro 2 re-enumerated!")
        time.sleep(1.0)
        try:
            dev = hid.device()
            dev.open(DAWN_PRO2_VID, DAWN_PRO2_PID)
            dev.write(bytes([0x4B, 0x80, 0x0C, 0x00]))
            resp = dev.read(64, timeout_ms=800)
            if resp and len(resp) >= 8:
                ver = bytes(resp[4:]).decode('latin1', errors='ignore').strip('\x00')
                print(f"    Reported Version: {ver}")
            dev.close()
        except Exception:
            pass
        print("\n==============================================================")
        print("  Flash Complete! Safe Volume Guard is now permanently active.")
        print("==============================================================")
    else:
        print("[-] Notice: Re-enumeration took longer than expected. Please replug the device.")

if __name__ == '__main__':
    main()
