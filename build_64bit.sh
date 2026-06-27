#!/bin/bash

################################################################################
#
# Build Script
#
# Copyright Samsung Electronics(C), 2015
#
################################################################################

################################################################################
# Useage
#   : ./build.sh
#
################################################################################

# Watermark variables for compile user/host (visible in settings)
export KBUILD_BUILD_USER="ThePanelsHub"
export KBUILD_BUILD_HOST="Galax1eo"

CPU_JOB_NUM=$(grep processor /proc/cpuinfo | awk '{field=$NF};END{print field+1}')
echo "make -j$CPU_JOB_NUM"

echo
echo 'Build android platform'
echo

echo "source build/envsetup.sh"
source build/envsetup.sh
lunch aosp_arm64-user

echo
make update-api
make -j$CPU_JOB_NUM
