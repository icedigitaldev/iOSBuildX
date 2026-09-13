#!/bin/bash
set -uxo pipefail
V=6.2.3
if [ ! -x /opt/swift-${V}-RELEASE-ubuntu24.04/usr/bin/swiftc ]; then
  curl -fL -C - -o /tmp/swift623.tar.gz "https://download.swift.org/swift-${V}-release/ubuntu2404/swift-${V}-RELEASE/swift-${V}-RELEASE-ubuntu24.04.tar.gz"
  tar xzf /tmp/swift623.tar.gz -C /opt
  rm -f /tmp/swift623.tar.gz
fi
ln -sfn /opt/swift-${V}-RELEASE-ubuntu24.04 /opt/swift
rm -rf /opt/swift-6.2.4-RELEASE-ubuntu24.04
/opt/swift/usr/bin/swift --version
XC=/root/iospoc/xc/Toolchains/XcodeDefault.xctoolchain
time /opt/swift/usr/bin/swiftc -target arm64-apple-ios15.0 \
  -sdk /root/iospoc/iossdk/iPhoneOS26.2.sdk \
  -resource-dir $XC/usr/lib/swift \
  -Xcc -resource-dir -Xcc $XC/usr/lib/clang/17 \
  -F /root/iospoc/engine/ios-release/Flutter.xcframework/ios-arm64 \
  -emit-object -o /tmp/hola.o /tmp/hola.swift > /out/swifttest2.log 2>&1
echo "rc=$?"
file /tmp/hola.o 2>/dev/null || tail -6 /out/swifttest2.log
