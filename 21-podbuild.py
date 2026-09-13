#!/usr/bin/env python3
"""Compila a objetos arm64-apple-ios todos los pods de un proyecto Flutter.

Sustituye a build_plugins.py de hatch-ios: mismos argumentos y mismo layout de
salida (obj/, inc/, mod/), asi que hatch enlaza igual. La diferencia es de donde
salen los flags: no se deduce nada por nombre de pod, se lee el xcconfig que
CocoaPods calcula para cada PodTarget (20-podgraph.rb) y se compila por
extension.

Cada pod se materializa como un <Modulo>.framework, que es lo mismo que produce
`use_frameworks!` en Xcode y lo que ya espera hatch. No es cosmetico:

  - un framework es UN modulo con las dos caras dentro (Modules/*.swiftmodule y
    Modules/module.modulemap), asi que `import X` da a la vez la API Swift y la
    ObjC. Con los dos arboles separados, un pod Swift consumido desde otro pod
    acaba viendo dos tipos distintos con el mismo nombre;
  - los headers solo son alcanzables por una ruta (Headers/), y un header
    visible por dos rutas se declara dos veces ("duplicate interface");
  - se descubren con -F, sin listas de -fmodule-map-file.

Dos fases: primero se monta el framework de TODOS los pods, luego se compila, y
toda compilacion ve el mismo contexto (-F, -I, -target). Un contexto distinto
por pod hace que clang reconstruya los modulos con otro hash y los tipos dejen
de unificar.

    python3 21-podbuild.py <proyecto> <out> [solo_estos...]
"""
import glob, json, os, plistlib, shlex, shutil, subprocess, sys

PROJECT = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2])
ONLY = set(sys.argv[3:]) or None

XC = "/root/iospoc/xc/Toolchains/XcodeDefault.xctoolchain"
TC = os.environ.get("HATCH_IOS_TC", "/opt/swift/usr/bin")
SDK = os.environ.get("HATCH_IOS_SDK_DIR", "/root/iospoc/iossdk/iPhoneOS26.2.sdk")
FFW = os.environ.get("HATCH_IOS_FFW",
                     "/root/iospoc/engine/ios-release/Flutter.xcframework/ios-arm64")
RESCLANG = os.environ.get("HATCH_IOS_RESCLANG", XC + "/usr/lib/clang/17")
SWLIB = os.environ.get("HATCH_IOS_SWLIB", XC + "/usr/lib/swift")
FBFW = os.environ.get("HATCH_IOS_FB_DIR", "/root/iospoc/dl/fbframeworks")
GRAPH = os.environ.get("HATCH_IOS_PODGRAPH", os.path.join(OUT, "podgraph.json"))
ANALYZER = os.environ.get("HATCH_IOS_ANALYZER", "/out/20-podgraph.rb")
DARWIN_BIN = os.environ.get("HATCH_IOS_DARWIN_BIN", "/root/iospoc/darwin-bin")

SWIFTC, CLANG = os.path.join(TC, "swiftc"), os.path.join(TC, "clang")
INC = os.path.join(OUT, "inc")      # inc/<Modulo> -> Headers del framework (lo usa hatch)
PRIV = os.path.join(OUT, "priv")    # headers privados: priv/<pod>/*.h
MOD = os.path.join(OUT, "mod")      # lo espera hatch; los modulos viven en los frameworks
OBJ = os.path.join(OUT, "obj")      # objetos: lo que enlaza hatch
BLD = os.path.join(OUT, "podbuild")
BUND = os.path.join(OUT, "bundles")

CXX_EXT = (".cpp", ".cc", ".cxx")
OBJCXX_EXT = (".mm",)
C_EXT = (".m", ".c")

# un header con C++ dentro no puede entrar en el umbrella de un modulo ObjC
CPP_MARKERS = ("include <vector>", "include <string>", "include <memory>",
               "include <cmath>", "include <optional>", "include <cstdint>",
               "namespace ")


def sh(cmd, log):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with open(log, "ab") as f:
        f.write(("\n=== rc=%d: %s\n" % (p.returncode, " ".join(cmd))).encode())
        f.write(p.stdout or b"")
    return p.returncode == 0


def load_graph():
    """El grafo se rehace solo si cambio la lista de plugins: si no, una app con
    una dependencia nueva se compilaria contra el grafo viejo sin avisar."""
    stamp = os.path.join(PROJECT, ".flutter-plugins-dependencies")
    fresh = (os.path.exists(GRAPH) and os.path.exists(stamp)
             and os.path.getmtime(GRAPH) >= os.path.getmtime(stamp))
    if not fresh or os.environ.get("HATCH_IOS_REANALYZE"):
        subprocess.run(["ruby", ANALYZER, PROJECT, GRAPH], check=True)
        # cambio el grafo: lo construido antes ya no corresponde. Dejarlo seria
        # enlazar objetos y frameworks de dependencias que ya no estan.
        for d in (FBFW, OBJ, INC, MOD, PRIV, BLD):
            shutil.rmtree(d, ignore_errors=True)
    return json.load(open(GRAPH))


def toposort(targets):
    by = {t["name"]: t for t in targets}
    seen, order = set(), []

    def visit(n, stack=()):
        if n in seen or n not in by or n in stack:
            return
        for d in by[n]["dependencies"]:
            visit(d, stack + (n,))
        seen.add(n)
        order.append(by[n])

    for t in targets:
        visit(t["name"])
    return order


def expand(value, vars_):
    """Resuelve ${PODS_ROOT} / $(PODS_TARGET_SRCROOT) y descarta $(inherited)."""
    if not value:
        return []
    value = value.replace("$(inherited)", " ").replace("${inherited}", " ")
    out = []
    for tok in shlex.split(value):
        for k, v in vars_.items():
            tok = tok.replace("${%s}" % k, v).replace("$(%s)" % k, v)
        if tok:
            out.append(tok)
    return out


def link(src, dst):
    if os.path.lexists(dst):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.symlink(os.path.realpath(src), dst)
    return True


def device_slice(xcfw):
    """Slice ios-arm64 de device (ni simulador ni catalyst) de un .xcframework."""
    info = os.path.join(xcfw, "Info.plist")
    if not os.path.exists(info):
        return None
    with open(info, "rb") as f:
        d = plistlib.load(f)
    for lib in d.get("AvailableLibraries", []):
        if (lib.get("SupportedPlatform") == "ios"
                and "arm64" in lib.get("SupportedArchitectures", [])
                and not lib.get("SupportedPlatformVariant")):
            return os.path.join(xcfw, lib["LibraryIdentifier"], lib.get("LibraryPath", ""))
    return None


# --------------------------------------------------------- fase 1: los frameworks

def stage(target):
    """Monta <Modulo>.framework con los headers publicos, deja los privados en
    priv/ y copia los binarios de terceros. Devuelve (framework, n, archivos .a).
    Un pod que solo trae un .xcframework ya viene hecho: no se toca."""
    mod = target["module_name"]
    fw = os.path.join(FBFW, mod + ".framework")
    priv = os.path.join(PRIV, target["pod_name"])
    n, archives, vendored = 0, [], False

    for acc in target["file_accessors"]:
        for vf in acc["vendored_frameworks"]:
            src = device_slice(vf) if vf.endswith(".xcframework") else vf
            if not src or not os.path.exists(src):
                continue
            vendored = True
            dst = os.path.join(FBFW, os.path.basename(src))
            if os.path.exists(dst):
                continue
            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True)
            else:
                shutil.copy2(src, dst)
        for vl in acc["vendored_libraries"]:
            src = device_slice(vl) if vl.endswith(".xcframework") else vl
            if src and os.path.exists(src):
                archives.append(src)

        for bname, files in acc["resource_bundles"].items():
            bdir = os.path.join(BUND, bname + ".bundle")
            os.makedirs(bdir, exist_ok=True)
            for f in files:
                if not os.path.exists(f):
                    continue
                dst = os.path.join(bdir, os.path.basename(f))
                if os.path.isdir(f):
                    shutil.copytree(f, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(f, dst)

    if vendored:
        return os.path.join(FBFW, mod + ".framework"), 0, archives

    os.makedirs(os.path.join(fw, "Headers"), exist_ok=True)
    os.makedirs(os.path.join(fw, "Modules"), exist_ok=True)
    for acc in target["file_accessors"]:
        mapdir = acc["header_mappings_dir"]
        public = set(acc["public_headers"])
        for h in acc["headers"]:
            if not os.path.exists(h):
                continue
            if h in public:
                rel = (os.path.relpath(h, mapdir) if mapdir and h.startswith(mapdir)
                       else os.path.basename(h))
                n += link(h, os.path.join(fw, "Headers", rel))
            else:
                link(h, os.path.join(priv, os.path.basename(h)))
    # hatch resuelve <plugin/Plugin.h> del GeneratedPluginRegistrant contra inc/
    link(os.path.join(fw, "Headers"), os.path.join(INC, mod))
    return fw, n, archives


def write_modulemap(target, fw):
    """Umbrella + module map del framework. El umbrella recoge los headers
    publicos y, si existe ya, el <Modulo>-Swift.h: eso es lo que hace que un
    consumidor ObjC vea la parte Swift del pod y que las dos caras sean un
    unico modulo."""
    mod = target["module_name"]
    hdir = os.path.join(fw, "Headers")
    heads = [os.path.relpath(h, hdir)
             for h in sorted(glob.glob(os.path.join(hdir, "**", "*.h"), recursive=True))]
    heads = [h for h in heads if not h.endswith("-umbrella.h")]
    if not heads:
        return None
    umbrella, excluded = mod + "-umbrella.h", []
    generated = mod + "-Swift.h"
    texts = {h: open(os.path.join(hdir, h), encoding="utf-8", errors="replace").read()
             for h in heads}
    # Foundation/UIKit solo si el pod es ObjC: muchos dan por hecho el prefix
    # header precompilado de Xcode y no importan nada. Ponerselos a un pod de C
    # puro (nanopb) rompe su modulo en cuanto se construye desde un .c.
    objc = any(m in t for t in texts.values() for m in ("@interface", "@protocol", "#import"))
    with open(os.path.join(hdir, umbrella), "w") as f:
        if objc:
            f.write("#import <Foundation/Foundation.h>\n#import <UIKit/UIKit.h>\n")
        for h in heads:
            # el -Swift.h generado trae un bloque C++ detras de #if __cplusplus,
            # pero es la cara ObjC del propio modulo: nunca se excluye
            if h != generated and any(c in texts[h] for c in CPP_MARKERS):
                excluded.append(h)
                continue
            f.write('#import "%s"\n' % h)
    mm = os.path.join(fw, "Modules", "module.modulemap")
    with open(mm, "w") as f:
        f.write('framework module %s {\n  umbrella header "%s"\n' % (mod, umbrella))
        for h in excluded:
            f.write('  exclude header "%s"\n' % h)
        f.write("  export *\n  module * { export * }\n}\n")
    return mm


def stub_object(triple):
    """Objeto sin simbolos, para dar cuerpo a los frameworks sin codigo propio."""
    c, o = os.path.join(BLD, "stub.c"), os.path.join(BLD, "stub.o")
    if not os.path.exists(o):
        open(c, "w").write("static const char stub_marker;" + chr(10))
        subprocess.run([CLANG, "-c", "-target", triple, "-isysroot", SDK, "-w", c, "-o", o],
                       capture_output=True)
    return o


def empty_binary(fw, mod, stub):
    """El framework de un pod compilado de fuente no lleva codigo (sus objetos van
    a obj/, que es lo que enlaza hatch), pero hatch pasa -framework para todo lo
    que encuentra en el directorio: sin binario dentro, el enlazador no lo halla.
    Un archivo estatico con un objeto vacio satisface la busqueda sin aportar
    simbolos ni duplicar nada."""
    p = os.path.join(fw, mod)
    if not os.path.exists(p):
        subprocess.run([os.path.join(DARWIN_BIN, "libtool"), "-static", "-o", p, stub],
                       capture_output=True)
    return p


def write_prefix():
    """Muchos pods dan por hecho el prefix header precompilado de Xcode y no
    importan Foundation en sus .h (sqflite: 'cannot find interface declaration
    for NSObject')."""
    p = os.path.join(OUT, "objc_prefix.h")   # hatch lo pasa con -include al Runner
    with open(p, "w") as f:
        f.write("#ifdef __OBJC__\n#import <Foundation/Foundation.h>\n"
                "#import <UIKit/UIKit.h>\n#endif\n")
    return p


# ------------------------------------------------------------ fase 2: compilar

def sources(target):
    swift, objc, cxx = [], [], []
    for acc in target["file_accessors"]:
        for f in acc["arc_source_files"] + acc["non_arc_source_files"]:
            e = os.path.splitext(f)[1]
            if e == ".swift":
                swift.append(f)
            elif e in OBJCXX_EXT + CXX_EXT:
                cxx.append(f)
            elif e in C_EXT:
                objc.append(f)
    return swift, objc, cxx


def explode_archive(a, mod, objs):
    """Un .a de terceros hatch no lo enlaza: se desarma en objetos sueltos."""
    d = os.path.join(BLD, "ar", mod)
    os.makedirs(d, exist_ok=True)
    if subprocess.run([os.path.join(DARWIN_BIN, "ar"), "x", os.path.abspath(a)],
                      cwd=d, capture_output=True).returncode:
        return
    for m in glob.glob(os.path.join(d, "*.o")):
        dst = os.path.join(OBJ, "%s.%s" % (mod, os.path.basename(m)))
        shutil.move(m, dst)
        objs.append(dst)


def main():
    g = load_graph()   # borra lo construido si el grafo cambio: va antes de crear
    for d in (INC, PRIV, MOD, OBJ, BLD, BUND, FBFW):
        os.makedirs(d, exist_ok=True)
    order = [t for t in toposort(g["targets"]) if t["pod_name"] != "Flutter"]
    prefix = write_prefix()

    base_vars = {
        "PODS_ROOT": g["pods_root"],
        "PODS_CONFIGURATION_BUILD_DIR": os.path.join(BLD, "products"),
        "PODS_BUILD_DIR": BLD,
        "PODS_XCFRAMEWORKS_BUILD_DIR": os.path.join(BLD, "XCFrameworks"),
        "PODS_PODFILE_DIR_PATH": os.path.join(PROJECT, "ios"),
        "SRCROOT": os.path.join(PROJECT, "ios"),
        "SDKROOT": SDK,
        "PLATFORM_DIR": SDK,
        "DEVELOPER_FRAMEWORKS_DIR": os.path.join(SDK, "System", "Library", "Frameworks"),
        "PODS_DEVELOPMENT_LANGUAGE": "en",
    }

    staged, archives_of, roots = {}, {}, []
    for t in order:
        fw, n, archives = stage(t)
        staged[t["name"]] = (fw, n)
        archives_of[t["name"]] = archives
        # la raiz del pod: sus fuentes se importan entre si por rutas relativas
        # al pod ("GoogleUtilities/Environment/Public/..."). Va al contexto
        # global: un -I distinto por pod rehace los modulos con otro hash.
        roots += expand(t["xcconfig"].get("HEADER_SEARCH_PATHS"),
                        dict(base_vars, PODS_TARGET_SRCROOT=t["srcroot"]))
    # el minimo de iOS es uno solo para todo, como el post_install del Podfile de
    # Flutter; con un -target por pod los modulos se reconstruyen distintos
    dep = max((tuple(int(x) for x in v.split(".")), v)
              for v in [g["ios_deployment"]] + [t["deployment_target"] for t in order])[1]
    triple = "arm64-apple-ios" + dep
    stub = stub_object(triple)
    for t in order:
        fw = staged[t["name"]][0]
        if write_modulemap(t, fw):
            empty_binary(fw, t["module_name"], stub)

    # Orden importante. Primero los Headers de cada framework, porque un pod
    # importa los suyos por nombre a secas ("FBLPromise+All.h"); luego la raiz de
    # cada pod, que cubre las rutas relativas al pod; y al final el arbol plano de
    # headers privados, que es el ultimo recurso: aplanarlos hace que dos pods con
    # un header del mismo nombre se pisen (FIRHeartbeatLogger.h aparece en
    # FirebaseCore y, recortado, en FirebaseCoreExtension).
    ctx_inc = (sorted(glob.glob(os.path.join(FBFW, "*.framework", "Headers")))
               + sorted(set(roots))
               + [PRIV] + sorted(glob.glob(os.path.join(PRIV, "*"))))
    ctx_inc = [p for p in dict.fromkeys(ctx_inc) if os.path.isdir(p)]
    # una sola cache de modulos para swiftc y clang: si cada uno construye su
    # propia copia de un modulo, los tipos que salen de cada copia no unifican
    mcache = os.path.join(BLD, "mcache")
    results, warnings = {}, []
    for t in order:
        name, mod = t["name"], t["module_name"]
        if ONLY and name not in ONLY:
            continue
        if t["script_phases"]:
            warnings.append("%s: %d script_phases no ejecutadas" % (name, len(t["script_phases"])))

        log = os.path.join(OUT, "pod_%s.log" % name)
        open(log, "wb").close()
        cfg, fw = t["xcconfig"], staged[name][0]
        v = dict(base_vars, PODS_TARGET_SRCROOT=t["srcroot"])

        swift, objc, cxx = sources(t)
        arc = {f for acc in t["file_accessors"] for f in acc["arc_source_files"]}
        defs = expand(cfg.get("GCC_PREPROCESSOR_DEFINITIONS"), v)
        other_c = expand(cfg.get("OTHER_CFLAGS"), v)
        other_sw = expand(cfg.get("OTHER_SWIFT_FLAGS"), v)
        swver = (cfg.get("SWIFT_VERSION") or t["swift_version"] or "5").split(".")[0]

        common = (["-target", triple, "-isysroot", SDK, "-F", FFW, "-F", FBFW]
                  + ["-I" + p for p in ctx_inc] + ["-D" + d for d in defs] + other_c)
        objs, ok = [], True

        if swift:
            o = os.path.join(OBJ, mod + ".swift.o")
            swiftmodule = os.path.join(fw, "Modules", mod + ".swiftmodule")
            os.makedirs(swiftmodule, exist_ok=True)
            # -parse-as-library: sin esto, un pod de un solo fichero .swift se
            # compila en modo script y emite un `main` que choca con el del Runner
            cmd = [SWIFTC, "-emit-object", "-wmo", "-O", "-parse-as-library",
                   "-module-name", mod,
                   "-swift-version", swver, "-sdk", SDK, "-target", triple,
                   "-resource-dir", SWLIB, "-Xcc", "-resource-dir", "-Xcc", RESCLANG,
                   "-Xcc", "-fmodules-cache-path=" + mcache,
                   "-emit-module-path", os.path.join(swiftmodule, "arm64-apple-ios.swiftmodule"),
                   "-emit-objc-header-path", os.path.join(fw, "Headers", mod + "-Swift.h"),
                   "-F", FFW, "-F", FBFW]
            for p in ctx_inc:
                cmd += ["-Xcc", "-I" + p]
            for d in defs:
                cmd += ["-Xcc", "-D" + d]
            if objc or cxx:
                cmd += ["-import-underlying-module"]
            cmd += other_sw + ["-o", o] + swift
            if sh(cmd, log):
                objs.append(o)
            else:
                ok = False
            if write_modulemap(t, fw):   # ya existe el -Swift.h: rehacer el umbrella
                empty_binary(fw, mod, stub)

        for f in objc + cxx:
            e = os.path.splitext(f)[1]
            o = os.path.join(OBJ, "%s.%s.o" % (mod, os.path.splitext(os.path.basename(f))[0]))
            cmd = [CLANG, "-c", "-O2", "-resource-dir", RESCLANG, "-fmodules",
                   "-fmodules-cache-path=" + mcache, "-w",
                   "-fobjc-arc" if f in arc else "-fno-objc-arc", "-include", prefix,
                   # sus headers son parte de lo que se esta compilando, no de un
                   # modulo aparte: sin esto sale "duplicate interface definition"
                   "-fmodule-name=" + mod]
            if e in OBJCXX_EXT + CXX_EXT:
                cmd += ["-std=" + (cfg.get("CLANG_CXX_LANGUAGE_STANDARD") or "gnu++17"),
                        "-isystem", os.path.join(SDK, "usr", "include", "c++", "v1")]
            cmd += common + [f, "-o", o]
            if sh(cmd, log):
                objs.append(o)
            else:
                ok = False

        for a in archives_of[name]:
            explode_archive(a, mod, objs)

        results[name] = (ok, len(objs))
        print("[%s] %-32s objs=%-4d hdrs=%-4d (swift=%d objc=%d c++=%d)%s"
              % ("OK " if ok else "FAIL", name, len(objs), staged[name][1],
                 len(swift), len(objc), len(cxx), "" if ok else "  -> " + log))

    with open(os.path.join(OUT, "podbuild.json"), "w") as f:
        json.dump({"targets": {k: {"ok": v[0], "objects": v[1]} for k, v in results.items()},
                   "warnings": warnings, "bundles": BUND}, f, indent=2)
    good = sum(1 for v in results.values() if v[0])
    print("\n=== %d/%d pods compilados ===" % (good, len(results)))
    for w in warnings:
        print("WARN", w)
    bad = [k for k, v in results.items() if not v[0]]
    if bad:
        print("FALLARON:", bad)
    return 1 if bad else 0


sys.exit(main())
