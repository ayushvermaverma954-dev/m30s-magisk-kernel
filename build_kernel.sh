#!/bin/bash

export ARCH=arm64
export PLATFORM_VERSION=11
export ANDROID_MAJOR_VERSION=r
export CONFIG_SECTION_MISMATCH_WARN_ONLY=y

# Watermark variables for compile user/host (visible in settings)
export KBUILD_BUILD_USER="ThePanelsHub"
export KBUILD_BUILD_HOST="Galax1eo"

# Use magisk_defconfig to build with the baked-in Magisk initramfs
make ARCH=arm64 magisk_defconfig
# Alternately: make ARCH=arm64 exynos9610-m30sdd_defconfig

make ARCH=arm64 -j16