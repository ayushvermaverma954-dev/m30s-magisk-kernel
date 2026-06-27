#!/usr/bin/env python3
import os
import sys
import zipfile
import lzma
import gzip
import re

def parse_hex(val):
    return int(val.decode('ascii'), 16)

def read_old_config(cpio_path):
    """
    Attempts to read .backup/.magisk from the existing cpio.gz file
    to preserve existing configuration (KEEPVERITY, PREINITDEVICE, etc.).
    """
    config_content = None
    if not os.path.exists(cpio_path):
        return None
    
    try:
        with gzip.open(cpio_path, 'rb') as f:
            data = f.read()
        
        offset = 0
        while offset < len(data):
            if offset + 110 > len(data):
                break
            header = data[offset:offset+110]
            magic = header[0:6]
            if magic != b"070701" and magic != b"070702":
                break
            
            namesize = parse_hex(header[94:102])
            filesize = parse_hex(header[54:62])
            
            offset += 110
            name = data[offset:offset+namesize].rstrip(b'\x00').decode('utf-8', errors='ignore')
            
            name_pad = (4 - ((110 + namesize) % 4)) % 4
            offset += namesize + name_pad
            
            if name == "TRAILER!!!":
                break
                
            content = data[offset:offset+filesize]
            file_pad = (4 - (filesize % 4)) % 4
            offset += filesize + file_pad
            
            if name == ".backup/.magisk":
                config_content = content.decode('utf-8', errors='ignore')
                break
    except Exception as e:
        print(f"[*] Warning: Could not parse old config: {e}")
        
    return config_content

def make_cpio_header(ino, mode, uid, gid, nlink, mtime, filesize, devmajor, devminor, rdevmajor, rdevminor, namesize):
    return f"070701{ino:08x}{mode:08x}{uid:08x}{gid:08x}{nlink:08x}{mtime:08x}{filesize:08x}{devmajor:08x}{devminor:08x}{rdevmajor:08x}{rdevminor:08x}{namesize:08x}00000000".encode('ascii')

def add_cpio_entry(cpio_data, path, content, mode, ino=1, mtime=0):
    path = path.lstrip('/')
    path_bytes = path.encode('utf-8') + b'\x00'
    namesize = len(path_bytes)
    filesize = len(content)
    
    # 0o100000 for regular file, 0o040000 for directory
    is_dir = (mode & 0o170000) == 0o040000
    nlink = 2 if is_dir else 1
    
    header = make_cpio_header(
        ino=ino, mode=mode, uid=0, gid=0, nlink=nlink, mtime=mtime,
        filesize=filesize, devmajor=3, devminor=1, rdevmajor=0, rdevminor=0,
        namesize=namesize
    )
    
    cpio_data.extend(header)
    cpio_data.extend(path_bytes)
    
    name_pad = (4 - ((110 + namesize) % 4)) % 4
    cpio_data.extend(b'\x00' * name_pad)
    
    cpio_data.extend(content)
    
    content_pad = (4 - (filesize % 4)) % 4
    cpio_data.extend(b'\x00' * content_pad)

def patch_magisk(apk_path, out_cpio_path):
    if not os.path.exists(apk_path):
        print(f"[-] Error: APK file not found at '{apk_path}'")
        sys.exit(1)
        
    print(f"[*] Reading Magisk APK: {apk_path}...")
    z = zipfile.ZipFile(apk_path)
    namelist = z.namelist()
    
    # Check what files are inside
    lib_magiskinit = None
    lib_magisk64 = None
    lib_magisk32 = None
    lib_init_ld = None
    stub_apk = None
    
    # 1. Detect magiskinit (ARM64 preferred, fallback to ARM)
    for name in ['lib/arm64-v8a/libmagiskinit.so', 'lib/armeabi-v7a/libmagiskinit.so']:
        if name in namelist:
            lib_magiskinit = z.read(name)
            print(f"[*] Found magiskinit in APK: {name}")
            break
            
    if lib_magiskinit is None:
        print("[-] Error: libmagiskinit.so not found in APK!")
        sys.exit(1)
        
    # 2. Detect magisk64 (64-bit daemon)
    for name in ['lib/arm64-v8a/libmagisk64.so', 'lib/arm64-v8a/libmagisk.so', 'lib/armeabi-v7a/libmagisk.so']:
        if name in namelist:
            lib_magisk64 = z.read(name)
            print(f"[*] Found magisk64/magisk in APK: {name}")
            break

    # 3. Detect magisk32 (32-bit daemon)
    for name in ['lib/armeabi-v7a/libmagisk32.so', 'lib/armeabi-v7a/libmagisk.so']:
        if name in namelist and z.read(name) != lib_magisk64:
            lib_magisk32 = z.read(name)
            print(f"[*] Found magisk32 in APK: {name}")
            break

    # 4. Detect init-ld helper
    for name in ['lib/arm64-v8a/libinit-ld.so', 'lib/armeabi-v7a/libinit-ld.so']:
        if name in namelist:
            lib_init_ld = z.read(name)
            print(f"[*] Found init-ld in APK: {name}")
            break
            
    # 5. Detect stub APK
    for name in ['assets/stub.apk', 'lib/arm64-v8a/libstub.so', 'lib/armeabi-v7a/libstub.so']:
        if name in namelist:
            stub_apk = z.read(name)
            print(f"[*] Found stub app/library in APK: {name}")
            break
            
    # Look for strings in magiskinit to determine what files it expects to load
    print("[*] Analyzing magiskinit binary strings...")
    magiskinit_strs = re.findall(b'[a-zA-Z0-9_./:-]{4,}', lib_magiskinit)
    magiskinit_strs_set = set(s.decode('ascii', errors='ignore') for s in magiskinit_strs)
    
    expects_magisk64 = "magisk64.xz" in magiskinit_strs_set
    expects_magisk32 = "magisk32.xz" in magiskinit_strs_set
    expects_magisk = "magisk.xz" in magiskinit_strs_set
    expects_stub = "stub.xz" in magiskinit_strs_set
    expects_init_ld = "init-ld.xz" in magiskinit_strs_set
    
    print(f"[*] magiskinit expectations:")
    print(f"    - magisk64.xz: {expects_magisk64}")
    print(f"    - magisk32.xz: {expects_magisk32}")
    print(f"    - magisk.xz:   {expects_magisk}")
    print(f"    - stub.xz:     {expects_stub}")
    print(f"    - init-ld.xz:  {expects_init_ld}")
    
    # Compress payloads with lzma (check=CRC32 is crucial for magiskinit decompression)
    def compress_payload(data):
        return lzma.compress(data, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC32)
        
    overlay_files = {}
    
    if (expects_magisk64 or expects_magisk) and lib_magisk64:
        comp = compress_payload(lib_magisk64)
        name = "magisk64.xz" if expects_magisk64 else "magisk.xz"
        overlay_files[f"overlay.d/sbin/{name}"] = comp
        print(f"[*] Compressed 64-bit magisk binary -> {name} ({len(comp)} bytes)")
        
    if expects_magisk32 and lib_magisk32:
        comp = compress_payload(lib_magisk32)
        overlay_files["overlay.d/sbin/magisk32.xz"] = comp
        print(f"[*] Compressed 32-bit magisk binary -> magisk32.xz ({len(comp)} bytes)")
        
    if expects_stub and stub_apk:
        comp = compress_payload(stub_apk)
        overlay_files["overlay.d/sbin/stub.xz"] = comp
        print(f"[*] Compressed stub APK -> stub.xz ({len(comp)} bytes)")
        
    if expects_init_ld and lib_init_ld:
        comp = compress_payload(lib_init_ld)
        overlay_files["overlay.d/sbin/init-ld.xz"] = comp
        print(f"[*] Compressed init-ld helper -> init-ld.xz ({len(comp)} bytes)")
    elif expects_init_ld:
        print("[!] Warning: magiskinit expects init-ld.xz but none was found in the APK.")
        
    # Prepare the config file
    old_config = read_old_config(out_cpio_path)
    if old_config:
        print("[*] Preserving existing config:")
        for line in old_config.strip().split('\n'):
            print(f"    {line}")
        config_data = old_config.encode('utf-8')
    else:
        print("[*] Creating default config:")
        default_config = (
            "KEEPVERITY=true\n"
            "KEEPFORCEENCRYPT=true\n"
            "RECOVERYMODE=false\n"
            "PREINITDEVICE=cache\n"
        )
        print(default_config)
        config_data = default_config.encode('utf-8')
        
    # Build CPIO in-memory
    cpio_data = bytearray()
    
    # 1. Add directories
    add_cpio_entry(cpio_data, "overlay.d", b"", mode=0o040750)
    add_cpio_entry(cpio_data, "overlay.d/sbin", b"", mode=0o040750)
    add_cpio_entry(cpio_data, ".backup", b"", mode=0o040000)
    
    # 2. Add files
    add_cpio_entry(cpio_data, "init", lib_magiskinit, mode=0o100750)
    add_cpio_entry(cpio_data, ".backup/.magisk", config_data, mode=0o100000)
    
    # Add compressed overlays
    for path, data in overlay_files.items():
        add_cpio_entry(cpio_data, path, data, mode=0o100644)
        
    # 3. Add TRAILER!!!
    add_cpio_entry(cpio_data, "TRAILER!!!", b"", mode=0, ino=0)
    
    # Gzip compress the whole CPIO archive
    print(f"[*] Packaging CPIO archive ({len(cpio_data)} bytes)...")
    compressed_cpio = gzip.compress(cpio_data, compresslevel=9)
    
    # Write to target path
    with open(out_cpio_path, 'wb') as f:
        f.write(compressed_cpio)
        
    print(f"[+] Successfully wrote patched initramfs to: {out_cpio_path} ({len(compressed_cpio)} bytes)")
    print("[*] You can now compile the kernel using your build script!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ./patch_magisk.py <path_to_magisk_apk> [output_cpio_path]")
        sys.exit(1)
        
    apk = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "initramfs.cpio.gz"
    patch_magisk(apk, out)
