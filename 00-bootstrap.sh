#!/bin/bash
# Levanta el toolchain iOS entero en una maquina smolvm nueva.
#
#   smolvm machine create --net --net-backend virtio-net --dns 192.168.1.1 \
#     --name hatch --image ubuntu:24.04 --cpus 8 --mem 6144 --overlay 24 \
#     --volume "C:\ruta\a\este\repo:/out"
#   smolvm machine start --name hatch
#   smolvm machine exec --name hatch -- bash /out/00-bootstrap.sh
#
# Idempotente: cada paso se salta si ya esta hecho. Necesita en /out/vendor los
# dos tarballs y los dos plist sacados de la macVM (ver ARQUITECTURA.md).
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
log() { echo; echo "=== $* ==="; }

cd /out || { echo "falta el volumen /out"; exit 1; }
for f in iPhoneOS26.2.sdk.tar.gz xcode-darwin-roots.tar.gz xcode-version.plist macos-SystemVersion.plist; do
  [ -f "/out/vendor/$f" ] || { echo "FALTA /out/vendor/$f (sacarlo de la macVM)"; exit 1; }
done

log "1/10 paquetes base + Flutter"
bash /out/01-base.sh || exit 1
# clon superficial: sin este tag, flutter --version se baja 1,1 M objetos
git -C /opt/flutter tag -f "$(cat /opt/flutter/version)" HEAD >/dev/null 2>&1

log "2/10 hatch + plugin hatch-ios (MinimumOSVersion a MIN_OS)"
bash /out/02-hatch.sh

log "3/10 SDK de la macVM + cctools/ld64 + rcodesign"
bash /out/03-toolchain.sh || exit 1

log "4/10 parches al SDK (modulemap C obsoleto + SubFrameworks)"
python3 /out/04-patchsdk.py
python3 /out/05-availability.py
S=/root/iospoc/iossdk/iPhoneOS26.2.sdk
( cd "$S/System/Library/Frameworks" && for f in ../SubFrameworks/*.framework; do
    n=$(basename "$f"); [ -e "$n" ] || ln -s "$f" "$n"; done )

log "5/10 Swift 6.2.3 (la version con la que se construyo el SDK)"
bash /out/06-swift.sh

log "6/10 resource dirs de Xcode"
if [ ! -d /root/iospoc/xc ]; then
  mkdir -p /root/iospoc/xc && tar xzf /out/vendor/xcode-darwin-roots.tar.gz -C /root/iospoc/xc
fi

log "7/10 cctools sin prefijo + Swift SDK para SwiftPM"
B=/root/iospoc/cctools-port/usage_examples/ios_toolchain/target/bin
mkdir -p /root/iospoc/darwin-bin
for t in libtool lipo install_name_tool otool nm strip ar ranlib; do
  [ -x "$B/arm-apple-darwin11-$t" ] && ln -sfn "$B/arm-apple-darwin11-$t" "/root/iospoc/darwin-bin/$t"
done
python3 /out/07-swiftsdk.py

log "8/10 CocoaPods (resuelve las dependencias nativas de los plugins)"
bash /out/08-cocoapods.sh || exit 1

log "9/10 shim de python: hatch -> nuestro compilador de pods"
bash /out/09-shim.sh

log "10/10 engine artifacts de Flutter"
V=$(cat /opt/flutter/version)
mkdir -p /root/fvm/versions && ln -sfn /opt/flutter "/root/fvm/versions/$V"
hatch-ios setup --flutter "$V"

log "doctor"
hatch-ios doctor

cat <<'TXT'

Toolchain listo. Para una app:
  1. copiar el proyecto a /root/<App> (no compilar sobre /out: el I/O es lento)
  2. echo '{"flutter":"<version>"}' > /root/<App>/.fvmrc
  3. APP=/root/<App> NAME=<App> BUNDLE=<id> bash /out/30-build.sh

Las dependencias nativas no hay que declararlas: 20-podgraph.rb las resuelve
con CocoaPods y 21-podbuild.py las compila.
TXT
