#!/usr/bin/env python3
"""Estampa en el .app la versión real del SDK y de Xcode con la que se compiló.

hatch escribe en el Info.plist unos DT* fijos (iOS 26.0 RC, Xcode 17A324) que no
corresponden a ningún Xcode público, y App Store Connect rechaza el build en revisión
como compilado con beta. Los valores correctos están en los ficheros que Apple mismo
consulta: el SystemVersion.plist y SDKSettings.json del SDK, el version.plist de Xcode
y el SystemVersion.plist del macOS que lo tenía instalado. Además alinea el campo sdk
de LC_BUILD_VERSION de cada Mach-O con esa misma versión.

    python3 41-stamp.py <Runner.app> <iPhoneOS.sdk> <xcode-version.plist> <macos-SystemVersion.plist>
"""
import json, os, plistlib, struct, sys

if len(sys.argv) != 5:
    sys.exit(__doc__)
app, sdk, xcode_plist, macos_plist = sys.argv[1:]

for p in (os.path.join(app, "Info.plist"),
          os.path.join(sdk, "SDKSettings.json"),
          os.path.join(sdk, "System/Library/CoreServices/SystemVersion.plist"),
          xcode_plist, macos_plist):
    if not os.path.isfile(p):
        sys.exit("falta %s" % p)

settings = json.load(open(os.path.join(sdk, "SDKSettings.json")))
sdk_sys = plistlib.load(open(os.path.join(sdk, "System/Library/CoreServices/SystemVersion.plist"), "rb"))
xcode = plistlib.load(open(xcode_plist, "rb"))
macos = plistlib.load(open(macos_plist, "rb"))

sdk_version = settings["Version"]
sdk_name = settings["CanonicalName"]
sdk_build = sdk_sys["ProductBuildVersion"]
xcode_version = xcode["CFBundleShortVersionString"]
xcode_build = xcode["ProductBuildVersion"]
machine_build = macos["ProductBuildVersion"]

parts = [int(x) for x in xcode_version.split(".")] + [0, 0]
dt_xcode = "%02d%d%d" % (parts[0], parts[1], parts[2])

info_path = os.path.join(app, "Info.plist")
info = plistlib.load(open(info_path, "rb"))
info.update({
    "DTPlatformName": "iphoneos",
    "DTPlatformVersion": sdk_version,
    "DTSDKName": sdk_name,
    "DTSDKBuild": sdk_build,
    "DTPlatformBuild": sdk_build,
    "DTXcode": dt_xcode,
    "DTXcodeBuild": xcode_build,
    "DTCompiler": "com.apple.compilers.llvm.clang.1_0",
    "BuildMachineOSBuild": machine_build,
})
plistlib.dump(info, open(info_path, "wb"))

parts = [int(x) for x in sdk_version.split(".")] + [0, 0]
sdk_packed = (parts[0] << 16) | (parts[1] << 8) | parts[2]

MH_MAGIC_64 = 0xFEEDFACF
FAT_MAGIC = 0xCAFEBABE
LC_BUILD_VERSION = 0x32
PLATFORM_IOS = 2


def stamp_macho(data, base):
    magic, _, _, _, ncmds = struct.unpack_from("<IIIII", data, base)
    if magic != MH_MAGIC_64:
        return False
    off = base + 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == LC_BUILD_VERSION:
            platform = struct.unpack_from("<I", data, off + 8)[0]
            if platform == PLATFORM_IOS:
                struct.pack_into("<I", data, off + 16, sdk_packed)
                return True
        off += size
    return False


def stamp_file(path):
    with open(path, "rb") as f:
        head = f.read(4)
    if head not in (struct.pack(">I", FAT_MAGIC), struct.pack("<I", MH_MAGIC_64)):
        return
    data = bytearray(open(path, "rb").read())
    magic = struct.unpack_from(">I", data, 0)[0]
    changed = False
    if magic == FAT_MAGIC:
        nfat = struct.unpack_from(">I", data, 4)[0]
        for i in range(nfat):
            offset = struct.unpack_from(">I", data, 8 + i * 20 + 8)[0]
            changed |= stamp_macho(data, offset)
    elif struct.unpack_from("<I", data, 0)[0] == MH_MAGIC_64:
        changed = stamp_macho(data, 0)
    if changed:
        open(path, "wb").write(data)


for root, dirs, files in os.walk(app):
    for name in files:
        stamp_file(os.path.join(root, name))

print("SDK %s (%s), Xcode %s (%s), macOS %s" % (sdk_version, sdk_build, xcode_version, xcode_build, machine_build))
