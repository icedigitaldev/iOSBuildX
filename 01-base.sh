#!/bin/bash
set -euxo pipefail
cat /etc/resolv.conf
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  curl wget git unzip zip xz-utils file ca-certificates build-essential \
  python3 python3-pip pkg-config libssl-dev cmake ninja-build clang lld llvm \
  libarchive-tools rsync jq sudo
# Flutter stable (linux x64)
if [ ! -d /opt/flutter ]; then
  git clone --depth 1 -b stable https://github.com/flutter/flutter.git /opt/flutter
fi
echo 'export PATH=/opt/flutter/bin:/root/.cargo/bin:/usr/local/bin:$PATH' > /etc/profile.d/99-hatch.sh
chmod +x /etc/profile.d/99-hatch.sh
export PATH=/opt/flutter/bin:$PATH
git config --global --add safe.directory /opt/flutter
flutter --version
flutter config --no-analytics || true
flutter precache --no-android --no-ios --no-web --no-linux --no-windows --no-macos --no-fuchsia || true
echo "base packages installed"
