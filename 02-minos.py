#!/usr/bin/env python3
"""Ajusta el MinimumOSVersion que estampa hatch.

hatch lo lleva fijo en 13.4 dentro del binario: no mira el `AppFrameworkInfo.plist`
del proyecto, ni el `.xcodeproj`, ni el engine de Flutter, y tampoco es
configurable (el esquema de ~/.hatch/ios.json solo tiene asc, signing, team_id,
bundle_id, wsl_distro y toolchain_root). App Store Connect lo acepta pero avisa
con ITMS-90068, y desde la primavera de 2027 exigirá 15.0 o superior.

El valor viaja como un inmediato de 4 bytes en el código, así que se cambia en
sitio por otro de la misma longitud. Idempotente: si ya está puesto, no toca nada.

    python3 02-minos.py 15.0 [/usr/local/bin/hatch-ios]
"""
import os, re, sys

TARGET = (sys.argv[1] if len(sys.argv) > 1 else "15.0").encode()
BINARY = sys.argv[2] if len(sys.argv) > 2 else "/usr/local/bin/hatch-ios"

if not re.fullmatch(rb"[0-9]{2}\.[0-9]", TARGET):
    sys.exit("el mínimo tiene que ser de la forma NN.N (15.0, 16.0, 17.0)")

data = open(BINARY, "rb").read()
# mov dword ptr [rax], "NN.N" — el inmediato con el que hatch construye el valor
hits = list(re.finditer(rb"\xc7\x00([0-9]{2}\.[0-9])", data))
if not hits:
    sys.exit("no se encontró el valor en %s: ¿cambió la versión de hatch?" % BINARY)
if len(hits) > 1:
    sys.exit("se encontró más de un candidato en %s; no se toca nada" % BINARY)

current = hits[0].group(1)
if current == TARGET:
    print("MinimumOSVersion ya es %s" % TARGET.decode())
    sys.exit(0)

start = hits[0].start(1)
patched = data[:start] + TARGET + data[start + 4:]
mode = os.stat(BINARY).st_mode
tmp = BINARY + ".new"
open(tmp, "wb").write(patched)
os.chmod(tmp, mode)
os.replace(tmp, BINARY)
print("MinimumOSVersion %s -> %s" % (current.decode(), TARGET.decode()))
