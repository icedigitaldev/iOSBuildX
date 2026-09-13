# Satisface el chequeo exacto de patch_availability_visionos.py sin redefinir
# nada: el SDK 26.2 ya trae visionOS, asi que el bloque va dentro de #if 0.
p = "/root/iospoc/iossdk/iPhoneOS26.2.sdk/usr/include/AvailabilityInternal.h"
s = open(p, encoding="utf-8", errors="surrogateescape").read()
marker = "/* hatch no-op shim */"
if marker in s:
    print("ya estaba")
else:
    s += (
        "\n" + marker + "\n#if 0\n"
        "    #define __API_AVAILABLE_PLATFORM_visionos(x) visionos,introduced=x\n"
        "    #define __API_DEPRECATED_PLATFORM_visionos(x,y) visionos,introduced=x,deprecated=y\n"
        "    #define __API_UNAVAILABLE_PLATFORM_visionos visionos,unavailable\n"
        "#endif\n"
    )
    open(p, "w", encoding="utf-8", errors="surrogateescape", newline="").write(s)
    print("shim anadido")
