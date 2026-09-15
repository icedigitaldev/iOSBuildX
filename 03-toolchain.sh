#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
export PATH=/opt/flutter/bin:/usr/local/bin:$PATH
ROOT=$HOME/iospoc
mkdir -p "$ROOT/iossdk"
apt-get install -y --no-install-recommends libxml2-dev uuid-dev zlib1g-dev libbz2-dev liblzma-dev
# 1. iPhoneOS SDK copiado de la macVM (Xcode 26.3 -> iPhoneOS26.2.sdk)
if [ ! -d "$ROOT/iossdk/iPhoneOS26.2.sdk" ]; then
  rm -rf /tmp/sdkx && mkdir -p /tmp/sdkx
  tar xzf /out/vendor/iPhoneOS26.2.sdk.tar.gz -C /tmp/sdkx
  mv /tmp/sdkx/iPhoneOS.sdk "$ROOT/iossdk/iPhoneOS26.2.sdk"
fi
ls "$ROOT/iossdk/iPhoneOS26.2.sdk"
# 2. cctools-port + ld64 (build.sh saca la version del nombre del tar)
cp -n /out/vendor/iPhoneOS26.2.sdk.tar.gz /tmp/iPhoneOS26.2.sdk.tar.gz || true
[ -d "$ROOT/cctools-port" ] || git clone --depth 1 https://github.com/tpoechtrager/cctools-port "$ROOT/cctools-port"
cd "$ROOT/cctools-port/usage_examples/ios_toolchain"
JOBS=8 ./build.sh /tmp/iPhoneOS26.2.sdk.tar.gz arm64
# 3. rcodesign
mkdir -p "$ROOT/rcodesign"
cd /tmp
curl -fsSL -o rc.tar.gz "https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign/0.29.0/apple-codesign-0.29.0-x86_64-unknown-linux-musl.tar.gz"
tar xzf rc.tar.gz
find /tmp -name rcodesign -type f -perm -u+x | head -1 | xargs -I{} cp {} "$ROOT/rcodesign/rcodesign"
chmod +x "$ROOT/rcodesign/rcodesign"
"$ROOT/rcodesign/rcodesign" --version
# hatch lo busca en <root>/rcodesign029 y con el nombre de Windows
mkdir -p "$ROOT/rcodesign029"
ln -sfn "$ROOT/rcodesign/rcodesign" "$ROOT/rcodesign029/rcodesign"
ln -sfn "$ROOT/rcodesign/rcodesign" "$ROOT/rcodesign029/rcodesign.exe"
echo "toolchain installed"
