#!/usr/bin/env python3
import os
import sys
import shutil
import zipfile

def package():
    workspace = os.path.dirname(os.path.abspath(__file__))
    boot_dir = os.path.join(workspace, "arch", "arm64", "boot")
    anykernel_dir = os.path.join(workspace, "AnyKernel3")
    
    # 1. Detect compiled kernel binary
    possible_kernels = ["Image.gz-dtb", "Image.gz", "Image"]
    kernel_source = None
    kernel_name = None
    
    if os.path.exists(boot_dir):
        for name in possible_kernels:
            path = os.path.join(boot_dir, name)
            if os.path.exists(path):
                kernel_source = path
                kernel_name = name
                break
                
    if not kernel_source:
        print("[-] Error: Compiled kernel image not found under arch/arm64/boot/")
        print("    Please build your kernel first by running: ./build_kernel.sh")
        sys.exit(1)
        
    print(f"[*] Found compiled kernel: {kernel_name} ({os.path.getsize(kernel_source)} bytes)")
    
    # 2. Clean up any existing kernel images in AnyKernel3 directory
    for name in possible_kernels:
        dest = os.path.join(anykernel_dir, name)
        if os.path.exists(dest):
            os.remove(dest)
            
    # 3. Copy the compiled kernel to AnyKernel3 directory
    kernel_dest = os.path.join(anykernel_dir, kernel_name)
    shutil.copy2(kernel_source, kernel_dest)
    print(f"[*] Copied {kernel_name} to AnyKernel3 directory.")
    
    # 4. Generate the zip file name
    zip_name = "M30s-Kernel-ThePanelsHub-Galax1eo.zip"
    zip_path = os.path.join(workspace, zip_name)
    
    if os.path.exists(zip_path):
        os.remove(zip_path)
        
    print(f"[*] Creating flashable zip: {zip_name}...")
    
    # 5. Pack AnyKernel3 directory (excluding git / github files)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(anykernel_dir):
            # Skip git & github directories
            if '.git' in root or '.github' in root:
                continue
            for file in files:
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, anykernel_dir)
                zipf.write(filepath, relpath)
                
    print(f"[+] Successfully created flashable zip: {zip_name} ({os.path.getsize(zip_path)} bytes)")
    print("    You can now transfer this zip to your phone and flash it in TWRP!")

if __name__ == "__main__":
    package()
