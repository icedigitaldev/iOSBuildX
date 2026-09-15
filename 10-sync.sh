#!/bin/bash
# Mete en la VM el código de la app y adapta lo que solo vale en Windows.
# Espera en /out/out un app.tar.gz con: lib assets ios pubspec.yaml pubspec.lock
# y, si la app usa un paquete local, un <paquete>.tar.gz.
set -uo pipefail
source /out/env.sh

[ -f /out/out/app.tar.gz ] || { echo "error: missing /out/out/app.tar.gz"; exit 1; }
mkdir -p "$APP"

# lib y assets se reemplazan enteros para no arrastrar ficheros ya borrados;
# ios/ se superpone, que ahí vive el sandbox de CocoaPods ya descargado
rm -rf "$APP/lib" "$APP/assets"
tar xzf /out/out/app.tar.gz -C "$APP"

for t in /out/out/*.tar.gz; do
  case "$(basename "$t")" in app.tar.gz) continue;; esac
  name=$(tar tzf "$t" | head -1 | cut -d/ -f1)
  rm -rf "/root/$name"
  tar xzf "$t" -C /root
done

python3 - "$APP" <<'PY'
import os, re, sys
p = os.path.join(sys.argv[1], "pubspec.yaml")
s = open(p, encoding="utf-8").read()
# los paquetes locales vienen con ruta de Windows
out = re.sub(r"path:\s*[A-Za-z]:/\S*/(\w+)\s*$", r"path: /root/\1", s, flags=re.M)
# image_background_remover arrastra un flutter_onnxruntime que no cruza a iOS
if "dependency_overrides:" not in out:
    out += "\ndependency_overrides:\n  flutter_onnxruntime: ^1.8.5\n"
if out != s:
    open(p, "w", encoding="utf-8", newline="\n").write(out)
PY

echo "{\"flutter\":\"$FLUTTER\"}" > "$APP/.fvmrc"
cd "$APP" || exit 1
out=$(flutter pub get 2>&1) || { echo "$out"; exit 1; }
